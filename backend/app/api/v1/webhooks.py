"""Inbound WhatsApp Webhook Endpoints

Single Organization Edition: Physio One.
Receives and cryptographically verifies webhooks from Meta Cloud API and YCloud.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, Request, Response, Query, HTTPException, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.whatsapp_service import (
    get_active_account_by_provider,
    process_incoming_webhook,
)
from app.providers.factory import get_provider_adapter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/whatsapp", tags=["WhatsApp Webhooks"])


@router.get("/meta", response_class=PlainTextResponse)
async def verify_meta_subscription(
    mode: Optional[str] = Query(None, alias="hub.mode"),
    verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    challenge: Optional[str] = Query(None, alias="hub.challenge"),
    db: AsyncSession = Depends(get_db),
):
    """Meta Webhook Subscription Challenge Verification.
    
    Triggered by Meta when configuring or validating the Webhook URL in Meta App Dashboard.
    """
    account = await get_active_account_by_provider(db, "meta")
    if not account:
        logger.warning("Meta webhook verification rejected: No active Meta account found.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verification failed. No active Meta WhatsApp connection.",
        )

    adapter = get_provider_adapter(account)
    res = adapter.verify_subscription_challenge(mode=mode, token=verify_token, challenge=challenge)
    if res.is_valid and res.challenge:
        logger.info("Meta webhook challenge verified successfully for account: %s", account.account_name)
        return PlainTextResponse(content=res.challenge, status_code=status.HTTP_200_OK)

    logger.warning("Meta webhook challenge rejected. Invalid token.")
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Verification token mismatch.",
    )


@router.post("/meta")
async def receive_meta_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Meta WhatsApp Cloud API Inbound Webhook Receiver.
    
    Verifies X-Hub-Signature-256 and processes inbound messages and delivery statuses.
    """
    raw_body = await request.body()
    headers = dict(request.headers)
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload.")

    res = await process_incoming_webhook(
        db,
        provider_name="meta",
        headers=headers,
        raw_body=raw_body,
        payload=payload,
    )
    return {"status": "EVENT_RECEIVED", **res}


@router.post("/ycloud")
async def receive_ycloud_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """YCloud Inbound Webhook Receiver for existing Physio One WhatsApp workflows.
    
    Verifies YCloud-Signature and processes inbound messages and status updates.
    """
    raw_body = await request.body()
    headers = dict(request.headers)
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload.")

    res = await process_incoming_webhook(
        db,
        provider_name="ycloud",
        headers=headers,
        raw_body=raw_body,
        payload=payload,
    )
    return {"status": "SUCCESS", **res}

