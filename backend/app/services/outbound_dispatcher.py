"""Outbound Reply Dispatcher with Persistent Idempotency & Delivery Guarantees.

Single Organization Edition: Physio One Clinic.
Enforces pre-dispatch invariants (live mode, opt-out, takeover check), once-and-only-once
idempotency, and safe handling of uncertain WhatsApp API delivery outcomes.
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.models.inbound import OutboundIdempotencyKey, AIInboundSettings
from app.models.whatsapp import Conversation, WhatsAppContact, WhatsAppAccount, WhatsAppMessage
from app.services.whatsapp_service import send_outbound_text_message, get_active_account_by_provider
from app.core.config import settings as core_settings

logger = logging.getLogger("physio_one.inbound.dispatcher")


class OutboundDispatcher:
    """Dispatches outbound AI replies with strict safety and idempotency gates."""

    @classmethod
    async def dispatch_ai_reply(
        cls,
        db: AsyncSession,
        conversation: Conversation,
        contact: WhatsAppContact,
        provider: str,
        reply_text: str,
        idempotency_key: str,
        settings: AIInboundSettings,
    ) -> Dict[str, Any]:
        """Dispatch an AI generated response to WhatsApp with rigorous pre-flight safety gates."""
        # 1. Mandatory Pre-Flight Invariants
        if not core_settings.AUTOMATION_OUTBOUND_ENABLED:
            logger.info("Outbound dispatch blocked: AUTOMATION_OUTBOUND_ENABLED is False (kill-switch active)")
            return {
                "dispatched": False,
                "reason": "Global automated outbound messaging is disabled by kill switch (AUTOMATION_OUTBOUND_ENABLED=false).",
            }

        if settings.ai_mode != "live":
            logger.info(
                "Outbound dispatch blocked: ai_mode is '%s' (not 'live') for conversation %s",
                settings.ai_mode,
                conversation.id,
            )
            return {
                "dispatched": False,
                "reason": f"AI mode is '{settings.ai_mode}'. Live messaging is not active.",
            }

        if contact.opted_out_all:
            logger.warning(
                "Outbound dispatch blocked: contact %s is opted out of all messages",
                contact.id,
            )
            return {
                "dispatched": False,
                "reason": "Contact has opted out of automated messaging.",
            }

        if conversation.is_human_takeover:
            logger.info(
                "Outbound dispatch blocked: conversation %s is under human takeover",
                conversation.id,
            )
            return {
                "dispatched": False,
                "reason": "Conversation is currently under human staff takeover.",
            }

        if conversation.ai_paused:
            logger.info(
                "Outbound dispatch blocked: AI is paused for conversation %s",
                conversation.id,
            )
            return {
                "dispatched": False,
                "reason": "AI replies are currently paused for this conversation.",
            }

        # 2. Idempotency Key Gate
        stmt = select(OutboundIdempotencyKey).where(
            OutboundIdempotencyKey.idempotency_key == idempotency_key
        )
        existing_key = (await db.execute(stmt)).scalar_one_or_none()
        if existing_key:
            if existing_key.status == "sent":
                logger.warning(
                    "Duplicate outbound dispatch prevented: idempotency key %s already sent",
                    idempotency_key,
                )
                return {
                    "dispatched": True,
                    "duplicate": True,
                    "message_id": str(existing_key.message_id) if existing_key.message_id else None,
                    "provider_message_id": existing_key.provider_message_id,
                }
            elif existing_key.status == "in_flight":
                logger.warning(
                    "Concurrent in-flight dispatch detected for idempotency key %s",
                    idempotency_key,
                )
                return {
                    "dispatched": False,
                    "reason": "Outbound message is currently in-flight.",
                }
        else:
            # Create in_flight idempotency record
            key_record = OutboundIdempotencyKey(
                idempotency_key=idempotency_key,
                conversation_id=conversation.id,
                status="in_flight",
                provider=provider,
            )
            db.add(key_record)
            await db.commit()

        # 3. Resolve Active WhatsApp Provider Account
        account = await get_active_account_by_provider(db, provider)
        if not account or not account.is_active:
            # If default provider not found, fallback to any active account
            stmt_acc = select(WhatsAppAccount).where(WhatsAppAccount.is_active == True).limit(1)  # noqa: E712
            account = (await db.execute(stmt_acc)).scalars().first()

        if not account:
            err_msg = f"No active WhatsApp account available for provider '{provider}'"
            logger.error(err_msg)
            await cls._update_idempotency_status(db, idempotency_key, "failed")
            return {"dispatched": False, "error": err_msg}

        # 4. Outbound API Transmission
        try:
            send_res = await send_outbound_text_message(
                db=db,
                account_id=account.id,
                to=contact.wa_id,
                text=reply_text,
            )

            if send_res.success:
                msg_uuid = uuid.UUID(send_res.message_id) if send_res.message_id else None
                await cls._update_idempotency_status(
                    db,
                    idempotency_key,
                    "sent",
                    message_id=msg_uuid,
                    provider_message_id=send_res.provider_message_id,
                )
                logger.info(
                    "Outbound message successfully dispatched for conversation %s: provider_msg_id=%s",
                    conversation.id,
                    send_res.provider_message_id,
                )
                return {
                    "dispatched": True,
                    "message_id": send_res.message_id,
                    "provider_message_id": send_res.provider_message_id,
                }
            else:
                logger.error("Provider rejected outbound message: %s", send_res.error)
                await cls._update_idempotency_status(db, idempotency_key, "failed")
                return {"dispatched": False, "error": send_res.error}

        except Exception as e:
            logger.exception("Unexpected error during outbound WhatsApp transmission: %s", str(e))
            # Mark uncertain/failed to prevent uncoordinated retries
            await cls._update_idempotency_status(db, idempotency_key, "uncertain")
            return {"dispatched": False, "error": f"Transmission outcome uncertain: {str(e)}"}

    @classmethod
    async def _update_idempotency_status(
        cls,
        db: AsyncSession,
        idempotency_key: str,
        status: str,
        message_id: Optional[uuid.UUID] = None,
        provider_message_id: Optional[str] = None,
    ) -> None:
        """Update status of idempotency key."""
        stmt = (
            update(OutboundIdempotencyKey)
            .where(OutboundIdempotencyKey.idempotency_key == idempotency_key)
            .values(
                status=status,
                message_id=message_id,
                provider_message_id=provider_message_id,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await db.execute(stmt)
        await db.commit()
