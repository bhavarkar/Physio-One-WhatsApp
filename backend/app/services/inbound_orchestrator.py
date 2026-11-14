"""Inbound WhatsApp AI Conversation Orchestrator & Deepti Receptionist Engine.

Single Organization Edition: Physio One Clinic.
Coordinates incoming message processing, strict safety guards (opt-out, emergency,
takeover), RAG & memory retrieval, Deepti execution, and persistent response drafting/dispatch.
"""
import uuid
import re
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.models.inbound import (
    InboundProcessingJob,
    AIInboundSettings,
    ConversationHandoff,
    AIResponseDraft,
)
from app.models.whatsapp import Conversation, WhatsAppContact, WhatsAppMessage, WhatsAppAccount
from app.models.ai import AIAgent, AIAgentSession
from app.agents.runtime import AgentRuntime, AgentRunResult
from app.llm.schemas import ChatMessage, MessageRole
from app.services.inbound_queue import InboundQueueService
from app.services.outbound_dispatcher import OutboundDispatcher

logger = logging.getLogger("physio_one.inbound.orchestrator")


class InboundOrchestrator:
    """Orchestrates inbound conversation lifecycle, safety evaluation, and Deepti AI runtime."""

    @classmethod
    async def process_job(
        cls,
        db: AsyncSession,
        job: InboundProcessingJob,
        override_settings: Optional[AIInboundSettings] = None,
        override_http_client: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Process an aggregated inbound message job through safety, RAG, and AI runtime."""
        # 1. Fetch Inbound Settings (Strict Default: disabled)
        settings = override_settings or await InboundQueueService.get_or_create_settings(db)
        
        # Reload conversation and contact
        stmt_conv = (
            select(Conversation)
            .options(selectinload(Conversation.contact))
            .where(Conversation.id == job.conversation_id)
        )
        conversation = (await db.execute(stmt_conv)).scalar_one_or_none()
        if not conversation:
            await InboundQueueService.release_job_lock(
                db, job.id, new_status="failed", error_message="Conversation not found"
            )
            return {"status": "failed", "reason": "conversation_not_found"}

        contact = conversation.contact
        if not contact:
            stmt_c = select(WhatsAppContact).where(WhatsAppContact.id == job.contact_id)
            contact = (await db.execute(stmt_c)).scalar_one_or_none()

        aggregated_text = (job.aggregated_text or "").strip()

        # 2. Safety Check: Opt-Out Verification & Keyword Detection
        if contact and contact.opted_out_all:
            logger.info("Skipping processing: contact %s is opted out of all messages", contact.id)
            await InboundQueueService.release_job_lock(db, job.id, new_status="completed")
            return {"status": "suppressed", "reason": "contact_opted_out"}

        if cls._contains_keywords(aggregated_text, settings.opt_out_keywords):
            logger.info("Opt-out keyword detected in message for contact %s", contact.id if contact else "unknown")
            if contact:
                contact.opted_out_all = True
            
            # Record audit handoff
            handoff = ConversationHandoff(
                conversation_id=conversation.id,
                action="opt_out_triggered",
                from_state=conversation.status,
                to_state="opted_out",
                reason=f"Patient sent opt-out keyword in message: '{aggregated_text[:50]}'",
                actor_type="patient",
            )
            db.add(handoff)
            await db.commit()

            # If live, send polite confirmation
            if settings.ai_mode == "live" and contact:
                confirm_text = (
                    "You have been successfully unsubscribed from automated messages from Physio One Clinic. "
                    "Reply START to resubscribe or call our clinic directly if you need assistance."
                )
                await OutboundDispatcher.dispatch_ai_reply(
                    db=db,
                    conversation=conversation,
                    contact=contact,
                    provider=job.provider,
                    reply_text=confirm_text,
                    idempotency_key=f"optout_confirm_{job.id}",
                    settings=settings,
                )

            await InboundQueueService.release_job_lock(db, job.id, new_status="completed")
            return {"status": "opted_out", "reason": "keyword_detected"}

        # 3. Safety Check: Emergency Keyword Detection
        if cls._contains_keywords(aggregated_text, settings.emergency_keywords):
            logger.warning("Emergency keyword detected in message for conversation %s", conversation.id)
            conversation.is_human_takeover = True
            
            handoff = ConversationHandoff(
                conversation_id=conversation.id,
                action="emergency_detected",
                from_state="ai_active",
                to_state="human_takeover",
                reason=f"Emergency keyword detected in message: '{aggregated_text[:50]}'",
                actor_type="system",
            )
            db.add(handoff)

            emergency_text = (
                "If you are experiencing a medical emergency, severe acute trauma, or chest pain, "
                "please call 112 or visit the nearest hospital emergency department immediately. "
                "Our clinic staff has been alerted and will follow up with you as soon as possible."
            )

            # Persist draft
            draft = AIResponseDraft(
                conversation_id=conversation.id,
                inbound_job_id=job.id,
                aggregated_inbound_text=aggregated_text,
                draft_text=emergency_text,
                ai_mode=settings.ai_mode,
                dispatched=False,
            )
            db.add(draft)
            await db.commit()

            if settings.ai_mode == "live" and contact:
                dispatch_res = await OutboundDispatcher.dispatch_ai_reply(
                    db=db,
                    conversation=conversation,
                    contact=contact,
                    provider=job.provider,
                    reply_text=emergency_text,
                    idempotency_key=f"emergency_reply_{job.id}",
                    settings=settings,
                )
                if dispatch_res.get("dispatched"):
                    draft.dispatched = True
                    if dispatch_res.get("message_id"):
                        try:
                            draft.outbound_message_id = uuid.UUID(dispatch_res["message_id"])
                        except ValueError:
                            pass
                    await db.commit()

            await InboundQueueService.release_job_lock(db, job.id, new_status="completed")
            return {"status": "emergency_handled", "reason": "emergency_keyword"}

        # 4. Safety Check: Human Takeover or AI Paused
        if conversation.is_human_takeover:
            logger.info("AI processing suppressed: conversation %s is under human takeover", conversation.id)
            await InboundQueueService.release_job_lock(db, job.id, new_status="completed")
            return {"status": "suppressed", "reason": "human_takeover_active"}

        if conversation.ai_paused:
            logger.info("AI processing suppressed: AI is paused for conversation %s", conversation.id)
            await InboundQueueService.release_job_lock(db, job.id, new_status="completed")
            return {"status": "suppressed", "reason": "ai_paused"}

        # 5. Core Check: AI Mode Verification
        # MANDATORY CONSTRAINT: ai_mode defaults to 'disabled' and must skip AI execution
        if settings.ai_mode == "disabled":
            logger.info("AI processing skipped: ai_mode is 'disabled'")
            await InboundQueueService.release_job_lock(db, job.id, new_status="completed")
            return {"status": "skipped", "reason": "ai_mode_disabled"}

        # 6. Resolve Active AI Agent (Deepti Receptionist)
        agent = None
        if settings.active_agent_id:
            stmt_a = select(AIAgent).where(AIAgent.id == settings.active_agent_id)
            agent = (await db.execute(stmt_a)).scalar_one_or_none()

        if not agent:
            # Fallback to Deepti or first active agent
            stmt_deepti = select(AIAgent).where(
                AIAgent.is_active == True,  # noqa: E712
                AIAgent.name.ilike("%Deepti%"),
            )
            agent = (await db.execute(stmt_deepti)).scalars().first()

        if not agent:
            stmt_any = select(AIAgent).where(AIAgent.is_active == True).limit(1)  # noqa: E712
            agent = (await db.execute(stmt_any)).scalars().first()

        if not agent:
            err_msg = "No active AI Agent found for inbound processing."
            logger.error(err_msg)
            await InboundQueueService.release_job_lock(db, job.id, new_status="failed", error_message=err_msg)
            return {"status": "failed", "reason": "no_active_agent"}

        # 7. Build Conversation History Context
        stmt_hist = (
            select(WhatsAppMessage)
            .where(WhatsAppMessage.conversation_id == conversation.id)
            .order_by(WhatsAppMessage.created_at.desc())
            .limit(10)
        )
        recent_msgs = (await db.execute(stmt_hist)).scalars().all()
        history_chat_messages: List[ChatMessage] = []
        for m in reversed(recent_msgs):
            # Skip messages included in current inbound job
            if str(m.id) in (job.aggregated_message_ids or []):
                continue
            role = MessageRole.USER if m.direction == "inbound" else MessageRole.ASSISTANT
            history_chat_messages.append(ChatMessage(role=role, content=m.body or ""))

        # 8. Execute Deepti Agent Runtime Session
        session_meta = {
            "source": "whatsapp_inbound",
            "provider": job.provider,
            "job_id": str(job.id),
            "contact_id": str(contact.id) if contact else None,
            "rag_enabled": True,
            "knowledge_base_id": str(agent.knowledge_base_id) if agent.knowledge_base_id else None,
        }

        try:
            run_result: AgentRunResult = await AgentRuntime.run(
                db=db,
                agent_id=agent.id,
                user_message=aggregated_text,
                conversation_id=conversation.id,
                history_messages=history_chat_messages,
                session_metadata=session_meta,
                override_http_client=override_http_client,
            )
        except Exception as e:
            logger.exception("Agent runtime execution failure for job %s: %s", job.id, str(e))
            await InboundQueueService.release_job_lock(db, job.id, new_status="failed", error_message=str(e))
            return {"status": "failed", "reason": f"agent_runtime_error: {str(e)}"}

        if run_result.status != "completed" or not run_result.response_text:
            err_msg = run_result.error_message or "Agent run did not return response text"
            logger.error("Agent execution unsuccessful: %s", err_msg)
            await InboundQueueService.release_job_lock(db, job.id, new_status="failed", error_message=err_msg)
            return {"status": "failed", "reason": err_msg}

        # 9. Pre-Dispatch Verification & Draft Persistence
        # Re-verify latest conversation and contact state
        await db.refresh(conversation)
        if contact:
            await db.refresh(contact)

        sess_uuid = None
        if run_result.session_id:
            try:
                sess_uuid = uuid.UUID(run_result.session_id)
            except ValueError:
                pass

        draft = AIResponseDraft(
            conversation_id=conversation.id,
            session_id=sess_uuid,
            agent_id=agent.id,
            inbound_job_id=job.id,
            aggregated_inbound_text=aggregated_text,
            draft_text=run_result.response_text,
            ai_mode=settings.ai_mode,
            dispatched=False,
        )
        db.add(draft)
        await db.commit()
        await db.refresh(draft)

        # 10. Shadow vs Live Mode Handling
        if settings.ai_mode == "shadow":
            logger.info("AI draft %s created in shadow mode for conversation %s", draft.id, conversation.id)
            await InboundQueueService.release_job_lock(db, job.id, new_status="completed")
            return {
                "status": "shadow_drafted",
                "draft_id": str(draft.id),
                "draft_text": draft.draft_text,
                "session_id": run_result.session_id,
            }

        elif settings.ai_mode == "live":
            # Recheck live invariants
            if conversation.is_human_takeover or conversation.ai_paused or (contact and contact.opted_out_all):
                logger.info("State changed before dispatch; suppressing live outbound send")
                await InboundQueueService.release_job_lock(db, job.id, new_status="completed")
                return {"status": "aborted", "reason": "state_changed_before_dispatch", "draft_id": str(draft.id)}

            if not contact:
                logger.error("Cannot dispatch live reply: contact missing")
                await InboundQueueService.release_job_lock(db, job.id, new_status="failed", error_message="Contact missing")
                return {"status": "failed", "reason": "contact_missing"}

            dispatch_res = await OutboundDispatcher.dispatch_ai_reply(
                db=db,
                conversation=conversation,
                contact=contact,
                provider=job.provider,
                reply_text=draft.draft_text,
                idempotency_key=f"ai_reply_{conversation.id}_{job.id}",
                settings=settings,
            )

            if dispatch_res.get("dispatched"):
                draft.dispatched = True
                if dispatch_res.get("message_id"):
                    try:
                        draft.outbound_message_id = uuid.UUID(dispatch_res["message_id"])
                    except ValueError:
                        pass
                await db.commit()

            await InboundQueueService.release_job_lock(db, job.id, new_status="completed")
            return {
                "status": "live_dispatched" if dispatch_res.get("dispatched") else "dispatch_failed",
                "draft_id": str(draft.id),
                "dispatch_result": dispatch_res,
                "session_id": run_result.session_id,
            }

        await InboundQueueService.release_job_lock(db, job.id, new_status="completed")
        return {"status": "completed"}

    @staticmethod
    def _contains_keywords(text: str, keywords: Optional[List[str]]) -> bool:
        """Check case-insensitive word-boundary or substring match for safety keywords."""
        if not text or not keywords:
            return False
        cleaned = text.lower().strip()
        for kw in keywords:
            kw_clean = kw.lower().strip()
            if not kw_clean:
                continue
            # Regex pattern with word boundary or exact match
            pattern = rf"\b{re.escape(kw_clean)}\b"
            if re.search(pattern, cleaned):
                return True
        return False
