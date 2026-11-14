"""WhatsApp Integration and Messaging Service

Single Organization Edition: Physio One.
Coordinates provider adapters, message persistence, webhook verification, and status tracking.
"""
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Tuple, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status

from app.models.whatsapp import (
    WhatsAppAccount,
    WhatsAppContact,
    Conversation,
    WhatsAppMessage,
    WebhookEvent,
)
from app.models.user import User
from app.schemas.whatsapp import (
    WhatsAppAccountCreateRequest,
    WhatsAppAccountUpdateRequest,
    WhatsAppAccountResponse,
    ConnectionTestResponse,
    MessageSendResponse,
)
from app.providers.base import (
    WhatsAppProvider,
    ProviderType,
    MessageStatus,
    MessageDirection,
    MessageType,
    NormalizedInboundMessage,
    NormalizedStatusUpdate,
)
from app.providers.factory import get_provider_adapter
from app.providers.meta import clean_phone_number
from app.core.crypto import encrypt_secret
from app.services.auth_service import log_audit_event

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Account and Connection Management
# -----------------------------------------------------------------------------

async def list_whatsapp_accounts(
    db: AsyncSession, only_active: bool = False
) -> List[WhatsAppAccountResponse]:
    """List configured WhatsApp accounts with masked secret references."""
    stmt = select(WhatsAppAccount).order_by(WhatsAppAccount.created_at.asc())
    if only_active:
        stmt = stmt.where(WhatsAppAccount.is_active == True)  # noqa: E712

    accounts = (await db.execute(stmt)).scalars().all()
    
    result = []
    for acc in accounts:
        resp = WhatsAppAccountResponse(
            id=acc.id,
            provider=acc.provider,
            account_name=acc.account_name,
            phone_number_id=acc.phone_number_id,
            business_account_id=acc.business_account_id,
            display_phone_number=acc.display_phone_number,
            webhook_verify_token=acc.webhook_verify_token,
            has_access_token=bool(acc.access_token_encrypted),
            has_secret_key=bool(acc.secret_key_encrypted),
            is_active=acc.is_active,
            created_at=acc.created_at,
            updated_at=acc.updated_at,
        )
        result.append(resp)
    return result


async def get_whatsapp_account_by_id(
    db: AsyncSession, account_id: uuid.UUID
) -> Optional[WhatsAppAccount]:
    """Retrieve raw WhatsApp account record."""
    stmt = select(WhatsAppAccount).where(WhatsAppAccount.id == account_id)
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_active_account_by_provider(
    db: AsyncSession, provider_name: str
) -> Optional[WhatsAppAccount]:
    """Retrieve active account for a specific provider (e.g. 'meta' or 'ycloud')."""
    prov = "meta" if provider_name.lower().startswith("meta") else "ycloud"
    stmt = select(WhatsAppAccount).where(
        WhatsAppAccount.provider == prov,
        WhatsAppAccount.is_active == True,
    ).order_by(WhatsAppAccount.created_at.desc())
    return (await db.execute(stmt)).scalars().first()


async def create_whatsapp_account(
    db: AsyncSession,
    payload: WhatsAppAccountCreateRequest,
    requesting_user: User,
    ip_address: Optional[str] = None,
) -> WhatsAppAccountResponse:
    """Create a new WhatsApp provider connection with encrypted credential storage."""
    encrypted_token = encrypt_secret(payload.access_token)
    encrypted_secret = encrypt_secret(payload.secret_key) if payload.secret_key else None

    account = WhatsAppAccount(
        provider=payload.provider,
        account_name=payload.account_name,
        phone_number_id=payload.phone_number_id,
        business_account_id=payload.business_account_id,
        display_phone_number=payload.display_phone_number,
        webhook_verify_token=payload.webhook_verify_token,
        access_token_encrypted=encrypted_token,
        secret_key_encrypted=encrypted_secret,
        provider_config=payload.provider_config,
        is_active=payload.is_active,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)

    await log_audit_event(
        db,
        action="WHATSAPP_ACCOUNT_CREATED",
        resource_type="whatsapp_account",
        resource_id=str(account.id),
        user_id=requesting_user.id,
        ip_address=ip_address,
        payload={
            "provider": payload.provider,
            "account_name": payload.account_name,
            "display_phone_number": payload.display_phone_number,
        },
    )
    await db.commit()

    return WhatsAppAccountResponse(
        id=account.id,
        provider=account.provider,
        account_name=account.account_name,
        phone_number_id=account.phone_number_id,
        business_account_id=account.business_account_id,
        display_phone_number=account.display_phone_number,
        webhook_verify_token=account.webhook_verify_token,
        has_access_token=True,
        has_secret_key=bool(account.secret_key_encrypted),
        is_active=account.is_active,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


async def update_whatsapp_account(
    db: AsyncSession,
    account_id: uuid.UUID,
    payload: WhatsAppAccountUpdateRequest,
    requesting_user: User,
    ip_address: Optional[str] = None,
) -> WhatsAppAccountResponse:
    """Update WhatsApp connection metadata and optionally rotate credentials."""
    account = await get_whatsapp_account_by_id(db, account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="WhatsApp account not found.")

    if payload.account_name is not None:
        account.account_name = payload.account_name
    if payload.display_phone_number is not None:
        account.display_phone_number = payload.display_phone_number
    if payload.business_account_id is not None:
        account.business_account_id = payload.business_account_id
    if payload.webhook_verify_token is not None:
        account.webhook_verify_token = payload.webhook_verify_token
    if payload.provider_config is not None:
        account.provider_config = payload.provider_config
    if payload.is_active is not None:
        account.is_active = payload.is_active

    if payload.access_token:
        account.access_token_encrypted = encrypt_secret(payload.access_token)
    if payload.secret_key is not None:
        account.secret_key_encrypted = encrypt_secret(payload.secret_key) if payload.secret_key else None

    await db.commit()
    await db.refresh(account)

    await log_audit_event(
        db,
        action="WHATSAPP_ACCOUNT_UPDATED",
        resource_type="whatsapp_account",
        resource_id=str(account.id),
        user_id=requesting_user.id,
        ip_address=ip_address,
        payload={"account_name": account.account_name, "is_active": account.is_active},
    )
    await db.commit()

    return WhatsAppAccountResponse(
        id=account.id,
        provider=account.provider,
        account_name=account.account_name,
        phone_number_id=account.phone_number_id,
        business_account_id=account.business_account_id,
        display_phone_number=account.display_phone_number,
        webhook_verify_token=account.webhook_verify_token,
        has_access_token=bool(account.access_token_encrypted),
        has_secret_key=bool(account.secret_key_encrypted),
        is_active=account.is_active,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


async def test_whatsapp_connection(
    db: AsyncSession, account_id: uuid.UUID
) -> ConnectionTestResponse:
    """Execute live provider API handshake using decrypted credentials."""
    account = await get_whatsapp_account_by_id(db, account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="WhatsApp account not found.")

    adapter = get_provider_adapter(account)
    res = await adapter.validate_connection()

    return ConnectionTestResponse(
        is_valid=res.is_valid,
        display_name=res.display_name,
        phone_number=res.phone_number,
        error=res.error,
    )


# -----------------------------------------------------------------------------
# Outbound Message Sending
# -----------------------------------------------------------------------------

async def send_outbound_text_message(
    db: AsyncSession,
    account_id: uuid.UUID,
    to: str,
    text: str,
    preview_url: bool = False,
    requesting_user: Optional[User] = None,
    ip_address: Optional[str] = None,
) -> MessageSendResponse:
    """Send an outbound text message through the configured provider and persist in database."""
    account = await get_whatsapp_account_by_id(db, account_id)
    if not account or not account.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Configured WhatsApp connection is inactive or not found.",
        )

    adapter = get_provider_adapter(account)
    clean_to = clean_phone_number(to)

    # 1. Send via provider
    send_result = await adapter.send_text_message(to=clean_to, text=text, preview_url=preview_url)
    if not send_result.success:
        return MessageSendResponse(
            success=False,
            status=MessageStatus.FAILED.value,
            error=send_result.error,
        )

    # 2. Persist contact and conversation thread
    stmt = select(WhatsAppContact).where(WhatsAppContact.wa_id == clean_to)
    contact = (await db.execute(stmt)).scalar_one_or_none()
    if not contact:
        contact = WhatsAppContact(wa_id=clean_to, last_active_at=datetime.now(timezone.utc))
        db.add(contact)
        await db.flush()

    # Find or create active conversation
    stmt = select(Conversation).where(
        Conversation.contact_id == contact.id,
        Conversation.status != "closed",
    ).order_by(Conversation.created_at.desc())
    conversation = (await db.execute(stmt)).scalars().first()
    if not conversation:
        conversation = Conversation(
            contact_id=contact.id,
            status="open",
            last_message_at=datetime.now(timezone.utc),
        )
        db.add(conversation)
        await db.flush()
    else:
        conversation.last_message_at = datetime.now(timezone.utc)

    # 3. Persist outbound WhatsApp message
    provider_msg_id = send_result.provider_message_id or f"outbound_{uuid.uuid4()}"
    msg = WhatsAppMessage(
        conversation_id=conversation.id,
        contact_id=contact.id,
        provider=account.provider,
        provider_message_id=provider_msg_id,
        direction=MessageDirection.OUTBOUND.value,
        message_type=MessageType.TEXT.value,
        body=text,
        status=MessageStatus.SENT.value,
        raw_payload=send_result.raw_response,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)

    if requesting_user:
        await log_audit_event(
            db,
            action="WHATSAPP_TEST_MESSAGE_SENT",
            resource_type="whatsapp_message",
            resource_id=str(msg.id),
            user_id=requesting_user.id,
            ip_address=ip_address,
            payload={"recipient": clean_to, "provider": account.provider},
        )
        await db.commit()

    return MessageSendResponse(
        success=True,
        message_id=str(msg.id),
        provider_message_id=provider_msg_id,
        status=MessageStatus.SENT.value,
    )


# -----------------------------------------------------------------------------
# Inbound Webhook Processing & Idempotency
# -----------------------------------------------------------------------------

async def process_incoming_webhook(
    db: AsyncSession,
    provider_name: str,
    headers: Dict[str, str],
    raw_body: bytes,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Ingest, verify, deduplicate, and process inbound webhook events."""
    account = await get_active_account_by_provider(db, provider_name)
    if not account:
        logger.warning("Webhook received for unconfigured provider: %s", provider_name)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active WhatsApp account configured for provider '{provider_name}'.",
        )

    adapter = get_provider_adapter(account)

    # 1. Cryptographic Signature Verification
    if not adapter.verify_webhook_signature(headers, raw_body):
        logger.warning("Webhook signature verification failed for provider: %s", provider_name)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid cryptographic webhook signature.",
        )

    # 2. Extract Event ID & Check Idempotency / Duplicate Prevention
    event_id = None
    if provider_name.startswith("meta"):
        # Meta event identifier or content digest
        entries = payload.get("entry", [])
        if entries:
            first_entry = entries[0]
            entry_id = first_entry.get("id")
            changes = first_entry.get("changes", [])
            change_field = changes[0].get("field") if changes else "messages"
            # Combine entry ID with change timestamp or body hash for uniqueness
            event_id = f"meta_{entry_id}_{hashlib.sha256(raw_body).hexdigest()[:16]}"
    else:
        # YCloud event identifier or body hash
        event_id = payload.get("id") or f"ycloud_{hashlib.sha256(raw_body).hexdigest()[:20]}"

    if not event_id:
        event_id = f"{provider_name}_{hashlib.sha256(raw_body).hexdigest()[:24]}"

    # Check for duplicate event
    stmt = select(WebhookEvent).where(
        WebhookEvent.provider == account.provider,
        WebhookEvent.event_id == event_id,
    )
    existing_event = (await db.execute(stmt)).scalar_one_or_none()
    if existing_event:
        logger.info("Duplicate webhook event ignored: provider=%s, event_id=%s", account.provider, event_id)
        return {"status": "duplicate", "event_id": event_id, "message": "Event already recorded."}

    # 3. Durable Event Record
    webhook_record = WebhookEvent(
        provider=account.provider,
        event_id=event_id,
        event_type="webhook",
        payload=payload,
        status="received",
    )
    db.add(webhook_record)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return {"status": "duplicate", "event_id": event_id, "message": "Duplicate event race prevented."}

    # 4. Parse Messages and Statuses using Provider Adapter
    inbound_messages, status_updates = adapter.parse_webhook_payload(payload)

    # 4a. Process Inbound Messages
    for in_msg in inbound_messages:
        try:
            # Lookup or create contact
            stmt = select(WhatsAppContact).where(WhatsAppContact.wa_id == in_msg.sender_wa_id)
            contact = (await db.execute(stmt)).scalar_one_or_none()
            if not contact:
                contact = WhatsAppContact(
                    wa_id=in_msg.sender_wa_id,
                    last_active_at=in_msg.timestamp,
                )
                db.add(contact)
                await db.flush()
            else:
                contact.last_active_at = in_msg.timestamp

            # Lookup or create open conversation
            stmt = select(Conversation).where(
                Conversation.contact_id == contact.id,
                Conversation.status != "closed",
            ).order_by(Conversation.created_at.desc())
            conversation = (await db.execute(stmt)).scalars().first()
            if not conversation:
                conversation = Conversation(
                    contact_id=contact.id,
                    status="open",
                    last_message_at=in_msg.timestamp,
                )
                db.add(conversation)
                await db.flush()
            else:
                conversation.last_message_at = in_msg.timestamp

            # Store message (guarded by uq_provider_message_id)
            stmt = select(WhatsAppMessage).where(
                WhatsAppMessage.provider == account.provider,
                WhatsAppMessage.provider_message_id == in_msg.message_id,
            )
            existing_msg = (await db.execute(stmt)).scalar_one_or_none()
            if not existing_msg:
                new_msg = WhatsAppMessage(
                    conversation_id=conversation.id,
                    contact_id=contact.id,
                    provider=account.provider,
                    provider_message_id=in_msg.message_id,
                    direction=MessageDirection.INBOUND.value,
                    message_type=in_msg.message_type,
                    body=in_msg.text_body,
                    media_url=in_msg.media_url,
                    media_mime_type=in_msg.media_mime_type,
                    status=MessageStatus.RECEIVED.value,
                    raw_payload=in_msg.raw_payload,
                )
                db.add(new_msg)
        except Exception as e:
            logger.error("Error processing inbound message %s: %s", in_msg.message_id, str(e))

    # 4b. Process Status Updates
    for st_up in status_updates:
        try:
            stmt = select(WhatsAppMessage).where(
                WhatsAppMessage.provider == account.provider,
                WhatsAppMessage.provider_message_id == st_up.message_id,
            )
            target_msg = (await db.execute(stmt)).scalar_one_or_none()
            if target_msg:
                target_msg.status = st_up.status.value
                if st_up.error_message:
                    target_msg.error_message = st_up.error_message
        except Exception as e:
            logger.error("Error updating status for message %s: %s", st_up.message_id, str(e))

    # Mark webhook processed
    webhook_record.status = "processed"
    webhook_record.processed_at = datetime.now(timezone.utc)
    await db.commit()

    return {
        "status": "success",
        "event_id": event_id,
        "inbound_count": len(inbound_messages),
        "status_count": len(status_updates),
    }
