"""Conversations & Live Inbox Management API Endpoints.

Single Organization Edition: Physio One Clinic.
Allows clinic staff to view live WhatsApp conversations, read message history,
inspect AI generated drafts, send manual replies, and toggle human takeover or AI pause.
"""
import uuid
from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, or_
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.api.deps import require_role, get_current_user
from app.core.rbac import ROLE_OWNER, ROLE_ADMIN, ROLE_OPERATOR, ROLE_VIEWER
from app.models.user import User
from app.models.whatsapp import Conversation, WhatsAppContact, WhatsAppMessage, WhatsAppAccount
from app.models.inbound import InboundProcessingJob, ConversationHandoff, AIResponseDraft
from app.schemas.inbound import (
    ConversationListItemResponse,
    ConversationDetailResponse,
    ConversationMessageResponse,
    ConversationReplyRequest,
    ConversationActionRequest,
    ConversationHandoffResponse,
    AIResponseDraftResponse,
)
from app.services.whatsapp_service import send_outbound_text_message, get_active_account_by_provider

router = APIRouter(prefix="/conversations", tags=["Conversations & Live Inbox"])


@router.get("", response_model=List[ConversationListItemResponse])
async def list_conversations(
    status_filter: Optional[str] = Query(None, alias="status"),
    takeover_only: bool = Query(False),
    search: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN, ROLE_OPERATOR, ROLE_VIEWER)),
    db: AsyncSession = Depends(get_db),
):
    """List WhatsApp conversations with contact information and status for the Live Inbox."""
    stmt = (
        select(Conversation)
        .options(selectinload(Conversation.contact))
        .order_by(Conversation.last_message_at.desc().nullslast(), Conversation.created_at.desc())
    )

    if status_filter:
        stmt = stmt.where(Conversation.status == status_filter)
    if takeover_only:
        stmt = stmt.where(Conversation.is_human_takeover == True)  # noqa: E712
    if search:
        search_term = f"%{search.strip()}%"
        stmt = stmt.join(Conversation.contact).where(
            or_(
                WhatsAppContact.wa_id.ilike(search_term),
                WhatsAppContact.profile_name.ilike(search_term),
            )
        )

    stmt = stmt.offset(offset).limit(limit)
    conversations = (await db.execute(stmt)).scalars().all()

    result = []
    for conv in conversations:
        contact = conv.contact
        
        # Get latest message
        latest_msg_stmt = (
            select(WhatsAppMessage)
            .where(WhatsAppMessage.conversation_id == conv.id)
            .order_by(WhatsAppMessage.created_at.desc())
            .limit(1)
        )
        latest_msg = (await db.execute(latest_msg_stmt)).scalars().first()

        # Count pending drafts
        draft_count_stmt = (
            select(func.count(AIResponseDraft.id))
            .where(
                AIResponseDraft.conversation_id == conv.id,
                AIResponseDraft.dispatched == False,  # noqa: E712
            )
        )
        draft_count = (await db.execute(draft_count_stmt)).scalar() or 0

        # Unread count (inbound messages)
        unread_count_stmt = (
            select(func.count(WhatsAppMessage.id))
            .where(
                WhatsAppMessage.conversation_id == conv.id,
                WhatsAppMessage.direction == "inbound",
                WhatsAppMessage.status == "received",
            )
        )
        unread_count = (await db.execute(unread_count_stmt)).scalar() or 0

        result.append(
            ConversationListItemResponse(
                id=conv.id,
                contact_id=contact.id if contact else uuid.uuid4(),
                contact_name=contact.profile_name if contact else None,
                contact_phone=contact.wa_id if contact else "Unknown",
                status=conv.status,
                is_human_takeover=conv.is_human_takeover,
                ai_paused=conv.ai_paused,
                opted_out=contact.opted_out_all if contact else False,
                last_message_at=conv.last_message_at,
                last_message_body=latest_msg.body if latest_msg else None,
                last_message_direction=latest_msg.direction if latest_msg else None,
                unread_count=unread_count,
                pending_draft_count=draft_count,
                created_at=conv.created_at,
            )
        )
    return result


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation_detail(
    conversation_id: uuid.UUID,
    current_user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN, ROLE_OPERATOR, ROLE_VIEWER)),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve full conversation details, message timeline, AI drafts, and handoff audit trail."""
    stmt = (
        select(Conversation)
        .options(selectinload(Conversation.contact))
        .where(Conversation.id == conversation_id)
    )
    conv = (await db.execute(stmt)).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")

    contact = conv.contact

    # Load messages chronological
    stmt_msgs = (
        select(WhatsAppMessage)
        .where(WhatsAppMessage.conversation_id == conv.id)
        .order_by(WhatsAppMessage.created_at.asc())
    )
    messages = (await db.execute(stmt_msgs)).scalars().all()

    # Load drafts
    stmt_drafts = (
        select(AIResponseDraft)
        .where(AIResponseDraft.conversation_id == conv.id)
        .order_by(AIResponseDraft.created_at.desc())
    )
    drafts = (await db.execute(stmt_drafts)).scalars().all()

    # Load handoffs
    stmt_handoffs = (
        select(ConversationHandoff)
        .where(ConversationHandoff.conversation_id == conv.id)
        .order_by(ConversationHandoff.created_at.desc())
    )
    handoffs = (await db.execute(stmt_handoffs)).scalars().all()

    return ConversationDetailResponse(
        id=conv.id,
        contact_id=contact.id if contact else uuid.uuid4(),
        contact_name=contact.profile_name if contact else None,
        contact_phone=contact.wa_id if contact else "Unknown",
        status=conv.status,
        is_human_takeover=conv.is_human_takeover,
        ai_paused=conv.ai_paused,
        opted_out=contact.opted_out_all if contact else False,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=[ConversationMessageResponse.from_orm(m) for m in messages],
        drafts=[AIResponseDraftResponse.from_orm(d) for d in drafts],
        handoffs=[ConversationHandoffResponse.from_orm(h) for h in handoffs],
    )


@router.post("/{conversation_id}/reply", response_model=ConversationMessageResponse)
async def send_manual_reply(
    conversation_id: uuid.UUID,
    payload: ConversationReplyRequest,
    current_user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN, ROLE_OPERATOR)),
    db: AsyncSession = Depends(get_db),
):
    """Send an authorized manual staff reply to the patient on WhatsApp."""
    stmt = (
        select(Conversation)
        .options(selectinload(Conversation.contact))
        .where(Conversation.id == conversation_id)
    )
    conv = (await db.execute(stmt)).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")

    contact = conv.contact
    if not contact:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Conversation has no contact.")

    if contact.opted_out_all:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot message contact: patient has opted out of communications.",
        )

    # Resolve active account
    stmt_acc = select(WhatsAppAccount).where(WhatsAppAccount.is_active == True).limit(1)  # noqa: E712
    account = (await db.execute(stmt_acc)).scalars().first()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No active WhatsApp account configured.",
        )

    # Cancel pending inbound processing jobs to prevent AI colliding with human reply
    cancel_stmt = (
        update(InboundProcessingJob)
        .where(
            InboundProcessingJob.conversation_id == conv.id,
            InboundProcessingJob.status.in_(["pending", "debouncing"]),
        )
        .values(status="cancelled", error_message="Cancelled by manual staff reply")
    )
    await db.execute(cancel_stmt)

    if payload.takeover and not conv.is_human_takeover:
        conv.is_human_takeover = True
        handoff = ConversationHandoff(
            conversation_id=conv.id,
            action="human_takeover",
            from_state="ai_active",
            to_state="human_takeover",
            reason="Staff sent manual reply with takeover enabled",
            actor_type="staff",
            actor_id=current_user.id,
        )
        db.add(handoff)

    # Send outbound message
    send_res = await send_outbound_text_message(
        db=db,
        account_id=account.id,
        to=contact.wa_id,
        text=payload.message,
        requesting_user=current_user,
    )

    if not send_res.success:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to dispatch WhatsApp message: {send_res.error}",
        )

    # Return created message
    msg_uuid = uuid.UUID(send_res.message_id)
    stmt_m = select(WhatsAppMessage).where(WhatsAppMessage.id == msg_uuid)
    msg = (await db.execute(stmt_m)).scalar_one()

    return ConversationMessageResponse.from_orm(msg)


@router.post("/{conversation_id}/takeover")
async def takeover_conversation(
    conversation_id: uuid.UUID,
    payload: Optional[ConversationActionRequest] = None,
    current_user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN, ROLE_OPERATOR)),
    db: AsyncSession = Depends(get_db),
):
    """Enable human staff takeover, suppressing automated AI responses."""
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    conv = (await db.execute(stmt)).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")

    conv.is_human_takeover = True

    # Cancel any pending jobs
    cancel_stmt = (
        update(InboundProcessingJob)
        .where(
            InboundProcessingJob.conversation_id == conv.id,
            InboundProcessingJob.status.in_(["pending", "debouncing"]),
        )
        .values(status="cancelled", error_message="Cancelled by human staff takeover")
    )
    await db.execute(cancel_stmt)

    reason = payload.reason if payload and payload.reason else "Staff manually took over conversation"
    handoff = ConversationHandoff(
        conversation_id=conv.id,
        action="human_takeover",
        from_state="ai_active",
        to_state="human_takeover",
        reason=reason,
        actor_type="staff",
        actor_id=current_user.id,
    )
    db.add(handoff)
    await db.commit()

    return {"status": "success", "is_human_takeover": True, "message": "Human takeover enabled"}


@router.post("/{conversation_id}/pause-ai")
async def pause_ai(
    conversation_id: uuid.UUID,
    payload: Optional[ConversationActionRequest] = None,
    current_user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN, ROLE_OPERATOR)),
    db: AsyncSession = Depends(get_db),
):
    """Pause AI responses for this specific conversation without full takeover."""
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    conv = (await db.execute(stmt)).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")

    conv.ai_paused = True

    # Cancel any pending jobs
    cancel_stmt = (
        update(InboundProcessingJob)
        .where(
            InboundProcessingJob.conversation_id == conv.id,
            InboundProcessingJob.status.in_(["pending", "debouncing"]),
        )
        .values(status="cancelled", error_message="Cancelled because AI was paused")
    )
    await db.execute(cancel_stmt)

    reason = payload.reason if payload and payload.reason else "Staff paused AI responses"
    handoff = ConversationHandoff(
        conversation_id=conv.id,
        action="ai_paused",
        from_state="ai_active",
        to_state="ai_paused",
        reason=reason,
        actor_type="staff",
        actor_id=current_user.id,
    )
    db.add(handoff)
    await db.commit()

    return {"status": "success", "ai_paused": True, "message": "AI paused for this conversation"}


@router.post("/{conversation_id}/resume-ai")
async def resume_ai(
    conversation_id: uuid.UUID,
    current_user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN, ROLE_OPERATOR)),
    db: AsyncSession = Depends(get_db),
):
    """Resume automated AI responses for this conversation and release human takeover."""
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    conv = (await db.execute(stmt)).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")

    conv.is_human_takeover = False
    conv.ai_paused = False

    handoff = ConversationHandoff(
        conversation_id=conv.id,
        action="ai_resumed",
        from_state="paused_or_takeover",
        to_state="ai_active",
        reason="Staff resumed AI responses and cleared human takeover",
        actor_type="staff",
        actor_id=current_user.id,
    )
    db.add(handoff)
    await db.commit()

    return {
        "status": "success",
        "is_human_takeover": False,
        "ai_paused": False,
        "message": "AI responses resumed",
    }
