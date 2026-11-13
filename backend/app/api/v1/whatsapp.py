"""WhatsApp Connection Management API Routes

Single Organization Edition: Physio One.
Provides RBAC-protected management for Meta Cloud API and YCloud provider connections.
"""
import uuid
from typing import List
from fastapi import APIRouter, Depends, Request, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rbac import ROLE_OWNER, ROLE_ADMIN
from app.api.deps import require_role
from app.models.user import User
from app.schemas.whatsapp import (
    WhatsAppAccountCreateRequest,
    WhatsAppAccountUpdateRequest,
    WhatsAppAccountResponse,
    ConnectionTestResponse,
    TestMessageRequest,
    MessageSendResponse,
)
from app.services.whatsapp_service import (
    list_whatsapp_accounts,
    get_whatsapp_account_by_id,
    create_whatsapp_account,
    update_whatsapp_account,
    test_whatsapp_connection,
    send_outbound_text_message,
)

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp Connections"])


@router.get("/connections", response_model=List[WhatsAppAccountResponse])
async def get_connections(
    current_user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """List all configured WhatsApp provider connections."""
    return await list_whatsapp_accounts(db)


@router.post("/connections", response_model=WhatsAppAccountResponse, status_code=status.HTTP_201_CREATED)
async def create_connection(
    payload: WhatsAppAccountCreateRequest,
    request: Request,
    current_user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Register a new WhatsApp connection (Meta Cloud API or YCloud) with encrypted secrets."""
    client_ip = request.client.host if request.client else None
    return await create_whatsapp_account(
        db, payload=payload, requesting_user=current_user, ip_address=client_ip
    )


@router.get("/connections/{account_id}", response_model=WhatsAppAccountResponse)
async def get_connection_details(
    account_id: uuid.UUID,
    current_user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve details for a specific WhatsApp connection."""
    account = await get_whatsapp_account_by_id(db, account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="WhatsApp account not found.")

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


@router.put("/connections/{account_id}", response_model=WhatsAppAccountResponse)
async def update_connection(
    account_id: uuid.UUID,
    payload: WhatsAppAccountUpdateRequest,
    request: Request,
    current_user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Update connection metadata or rotate provider credentials."""
    client_ip = request.client.host if request.client else None
    return await update_whatsapp_account(
        db, account_id=account_id, payload=payload, requesting_user=current_user, ip_address=client_ip
    )


@router.post("/connections/{account_id}/test", response_model=ConnectionTestResponse)
async def test_connection_handshake(
    account_id: uuid.UUID,
    current_user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Test live provider API connectivity without sending messages."""
    return await test_whatsapp_connection(db, account_id)


@router.post("/connections/{account_id}/send-test", response_model=MessageSendResponse)
async def send_administrative_test_message(
    account_id: uuid.UUID,
    payload: TestMessageRequest,
    request: Request,
    current_user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Send an administrative test message to verify outbound transmission."""
    client_ip = request.client.host if request.client else None
    return await send_outbound_text_message(
        db,
        account_id=account_id,
        to=payload.recipient_phone,
        text=payload.message_text,
        requesting_user=current_user,
        ip_address=client_ip,
    )

