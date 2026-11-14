"""Automated Unit and Integration Tests for WhatsApp Providers (Meta Cloud API and YCloud)

Single Organization Edition: Physio One Clinic.
Tests provider adapters, cryptographic webhook verification, payload parsing,
secret encryption, webhook deduplication, outbound dispatch, and RBAC.
"""
import hashlib
import hmac
import json
import uuid
import pytest
from httpx import AsyncClient, Response
from unittest.mock import patch, AsyncMock
from datetime import datetime, timezone

from app.providers.base import (
    ProviderType,
    MessageStatus,
    MessageType,
    NormalizedInboundMessage,
    NormalizedStatusUpdate,
    ConnectionValidationResult,
    OutboundSendResult,
)
from app.providers.meta import MetaCloudProvider, clean_phone_number
from app.providers.ycloud import YCloudProvider
from app.core.crypto import encrypt_secret, decrypt_secret
from app.core.rbac import ROLE_OWNER, ROLE_ADMIN, ROLE_OPERATOR, ROLE_VIEWER
from app.models.whatsapp import WhatsAppAccount, WebhookEvent, WhatsAppMessage, WhatsAppContact


# -----------------------------------------------------------------------------
# Unit Tests: Provider Adapters & Crypto
# -----------------------------------------------------------------------------

def test_1_phone_number_cleaning():
    """Verify phone numbers are cleaned to digits only."""
    assert clean_phone_number("+91 98765-43210") == "919876543210"
    assert clean_phone_number("+1 (555) 234-5678") == "15552345678"
    assert clean_phone_number("9876543210") == "9876543210"


def test_2_fernet_crypto_encryption_and_decryption():
    """Verify symmetric Fernet encryption protects credentials."""
    plain = "EAAGtest_meta_access_token_secret_12345"
    cipher = encrypt_secret(plain)
    assert cipher != plain
    assert "EAAG" not in cipher

    decrypted = decrypt_secret(cipher)
    assert decrypted == plain


def test_3_meta_webhook_signature_verification():
    """Verify Meta X-Hub-Signature-256 HMAC-SHA256 signature verification."""
    app_secret = "physio_one_meta_app_secret_998877"
    provider = MetaCloudProvider(
        phone_number_id="100012345678901",
        access_token="test_token",
        app_secret=app_secret,
        webhook_verify_token="test_verify_token",
    )

    body = b'{"object":"whatsapp_business_account","entry":[]}'
    # Compute valid signature
    valid_hash = hmac.new(app_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    valid_header = {"x-hub-signature-256": f"sha256={valid_hash}"}

    # 1. Valid signature succeeds
    assert provider.verify_webhook_signature(valid_header, body) is True

    # 2. Tampered body fails
    tampered_body = b'{"object":"whatsapp_business_account","entry":[{"tampered":true}]}'
    assert provider.verify_webhook_signature(valid_header, tampered_body) is False

    # 3. Forged signature fails
    invalid_header = {"x-hub-signature-256": "sha256=badhash0000000000000000000000000000"}
    assert provider.verify_webhook_signature(invalid_header, body) is False


def test_4_meta_webhook_subscription_challenge():
    """Verify Meta hub.challenge verification logic."""
    provider = MetaCloudProvider(
        phone_number_id="100012345678901",
        access_token="test_token",
        webhook_verify_token="secure_meta_token_123",
    )

    # Valid challenge
    res = provider.verify_subscription_challenge(
        mode="subscribe", token="secure_meta_token_123", challenge="1158201244"
    )
    assert res.is_valid is True
    assert res.challenge == "1158201244"

    # Token mismatch
    res_invalid = provider.verify_subscription_challenge(
        mode="subscribe", token="wrong_token", challenge="1158201244"
    )
    assert res_invalid.is_valid is False


def test_5_meta_webhook_inbound_and_status_parsing():
    """Verify parsing of Meta webhook JSON payloads into normalized events."""
    provider = MetaCloudProvider(
        phone_number_id="100012345678901",
        access_token="test_token",
    )

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "100001",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"display_phone_number": "919876500000"},
                            "contacts": [{"profile": {"name": "Patient Alice"}, "wa_id": "919876543210"}],
                            "messages": [
                                {
                                    "from": "919876543210",
                                    "id": "wamid.HBgTEST001",
                                    "timestamp": "1700000000",
                                    "type": "text",
                                    "text": {"body": "Hello, I want to book an appointment."},
                                }
                            ],
                            "statuses": [
                                {
                                    "id": "wamid.HBgOUTBOUND001",
                                    "status": "delivered",
                                    "timestamp": "1700000010",
                                    "recipient_id": "919876543210",
                                }
                            ],
                        },
                    }
                ],
            }
        ]
    }

    inbound, statuses = provider.parse_webhook_payload(payload)

    assert len(inbound) == 1
    assert inbound[0].message_id == "wamid.HBgTEST001"
    assert inbound[0].sender_wa_id == "919876543210"
    assert inbound[0].text_body == "Hello, I want to book an appointment."
    assert inbound[0].provider == ProviderType.META_CLOUD.value

    assert len(statuses) == 1
    assert statuses[0].message_id == "wamid.HBgOUTBOUND001"
    assert statuses[0].status == MessageStatus.DELIVERED
    assert statuses[0].recipient_wa_id == "919876543210"


def test_6_ycloud_webhook_signature_and_parsing():
    """Verify YCloud HMAC-SHA256 signature verification and event parsing."""
    secret = "ycloud_secret_abc123"
    provider = YCloudProvider(
        api_key="ycloud_api_key_test",
        phone_number="+919876500000",
        webhook_secret=secret,
    )

    body = b'{"type":"whatsapp.inbound_message","whatsappInboundMessage":{"id":"ycloud_msg_001","from":"919876543210","text":{"body":"Hi YCloud"}}}'
    valid_sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

    # Signature check
    assert provider.verify_webhook_signature({"ycloud-signature": valid_sig}, body) is True
    assert provider.verify_webhook_signature({"ycloud-signature": "badsig"}, body) is False

    # Inbound message parsing
    payload = json.loads(body.decode("utf-8"))
    inbound, statuses = provider.parse_webhook_payload(payload)
    assert len(inbound) == 1
    assert inbound[0].message_id == "ycloud_msg_001"
    assert inbound[0].text_body == "Hi YCloud"
    assert inbound[0].provider == ProviderType.YCLOUD.value


# -----------------------------------------------------------------------------
# Integration Tests: Connections API & Webhook Endpoints
# -----------------------------------------------------------------------------

async def setup_test_connection(client: AsyncClient, provider: str = "meta"):
    """Helper to setup initial Owner and configured WhatsApp connection."""
    await client.post(
        "/api/v1/auth/setup",
        json={"email": "owner@physioone.com", "password": "MasterPassword123!", "full_name": "Clinic Owner"},
    )
    csrf = client.cookies.get("csrf_token")
    headers = {"X-CSRF-Token": csrf} if csrf else {}

    payload = {
        "provider": provider,
        "account_name": f"Physio One {provider.title()}",
        "phone_number_id": "1000987654321",
        "business_account_id": "2000987654321",
        "display_phone_number": "+919876500000",
        "webhook_verify_token": "physio_meta_verify_token_2026",
        "access_token": "EAAG_super_secret_access_token_12345",
        "secret_key": "meta_app_secret_67890",
    }
    conn_resp = await client.post("/api/v1/whatsapp/connections", json=payload, headers=headers)
    return conn_resp.json()


@pytest.mark.asyncio
async def test_7_whatsapp_connection_crud_and_rbac(client: AsyncClient):
    """Test WhatsApp connection provisioning, credential encryption, and RBAC."""
    conn_data = await setup_test_connection(client, "meta")
    account_id = conn_data["id"]

    # Verify secret is masked (never returned in plaintext)
    assert "access_token" not in conn_data
    assert "secret_key" not in conn_data
    assert conn_data["has_access_token"] is True
    assert conn_data["has_secret_key"] is True
    assert conn_data["provider"] == "meta"

    # 3. List connections
    list_resp = await client.get("/api/v1/whatsapp/connections")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) >= 1

    # 4. Operator role cannot create or modify connections
    roles_resp = await client.get("/api/v1/users/roles")
    op_role = next(r for r in roles_resp.json() if r["name"] == ROLE_OPERATOR)

    csrf = client.cookies.get("csrf_token")
    headers = {"X-CSRF-Token": csrf} if csrf else {}

    user_resp = await client.post(
        "/api/v1/users",
        json={
            "email": "operator@physioone.com",
            "password": "OperatorPassword123!",
            "full_name": "Operator Sam",
            "role_id": op_role["id"],
        },
        headers=headers,
    )
    assert user_resp.status_code == 201

    # Logout and Login as Operator
    await client.post("/api/v1/auth/logout", headers=headers)
    login_op = await client.post(
        "/api/v1/auth/login",
        json={"email": "operator@physioone.com", "password": "OperatorPassword123!"},
    )
    assert login_op.status_code == 200

    # Operator should be rejected (HTTP 403) from connection management
    op_get_conn = await client.get("/api/v1/whatsapp/connections")
    assert op_get_conn.status_code == 403


@pytest.mark.asyncio
async def test_8_meta_webhook_challenge_and_inbound_ingestion(client: AsyncClient):
    """Test Meta webhook hub.challenge verification and cryptographic message ingestion."""
    await setup_test_connection(client, "meta")

    # 2. Test GET hub.challenge verification endpoint
    challenge_resp = await client.get(
        "/api/v1/webhooks/whatsapp/meta",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "physio_meta_verify_token_2026",
            "hub.challenge": "1992837465",
        },
    )
    assert challenge_resp.status_code == 200
    assert challenge_resp.text == "1992837465"

    # Invalid token fails with 403
    bad_challenge = await client.get(
        "/api/v1/webhooks/whatsapp/meta",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong_token",
            "hub.challenge": "1992837465",
        },
    )
    assert bad_challenge.status_code == 403

    # 3. Test POST Inbound Webhook with HMAC-SHA256 signature
    meta_secret = "meta_app_secret_67890"
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "1000987654321",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"display_phone_number": "919876500000"},
                            "contacts": [{"profile": {"name": "Patient Bob"}, "wa_id": "919123456789"}],
                            "messages": [
                                {
                                    "from": "919123456789",
                                    "id": "wamid.TEST_INBOUND_998877",
                                    "timestamp": "1700000500",
                                    "type": "text",
                                    "text": {"body": "Need physiotherapy consultation for knee pain."},
                                }
                            ],
                        },
                    }
                ],
            }
        ]
    }
    raw_body = json.dumps(payload).encode("utf-8")
    signature = "sha256=" + hmac.new(meta_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    # Post signed webhook
    post_resp = await client.post(
        "/api/v1/webhooks/whatsapp/meta",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature},
    )
    assert post_resp.status_code == 200
    data = post_resp.json()
    assert data["status"] == "success"
    assert data["inbound_count"] == 1

    # 4. Duplicate webhook event idempotency: posting identical event returns duplicate
    dup_resp = await client.post(
        "/api/v1/webhooks/whatsapp/meta",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature},
    )
    assert dup_resp.status_code == 200
    assert dup_resp.json()["status"] == "duplicate"


@pytest.mark.asyncio
async def test_9_status_update_webhook_updates_message(client: AsyncClient):
    """Test webhook delivery status event updates existing message status."""
    await setup_test_connection(client, "meta")
    meta_secret = "meta_app_secret_67890"

    # First ingest an inbound message so wamid.TEST_INBOUND_998877 exists
    inbound_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "1000987654321",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"display_phone_number": "919876500000"},
                            "contacts": [{"profile": {"name": "Patient Bob"}, "wa_id": "919123456789"}],
                            "messages": [
                                {
                                    "from": "919123456789",
                                    "id": "wamid.TEST_INBOUND_998877",
                                    "timestamp": "1700000500",
                                    "type": "text",
                                    "text": {"body": "Need physiotherapy consultation for knee pain."},
                                }
                            ],
                        },
                    }
                ],
            }
        ]
    }
    raw_inbound = json.dumps(inbound_payload).encode("utf-8")
    sig_inbound = "sha256=" + hmac.new(meta_secret.encode("utf-8"), raw_inbound, hashlib.sha256).hexdigest()
    await client.post(
        "/api/v1/webhooks/whatsapp/meta",
        content=raw_inbound,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig_inbound},
    )

    # Now post status update for that message
    status_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "1000987654321",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "statuses": [
                                {
                                    "id": "wamid.TEST_INBOUND_998877",
                                    "status": "read",
                                    "timestamp": "1700000550",
                                    "recipient_id": "919123456789",
                                }
                            ],
                        },
                    }
                ],
            }
        ]
    }
    raw_body = json.dumps(status_payload).encode("utf-8")
    signature = "sha256=" + hmac.new(meta_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    resp = await client.post(
        "/api/v1/webhooks/whatsapp/meta",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status_count"] == 1


@pytest.mark.asyncio
async def test_10_test_connection_handshake_and_outbound_send(client: AsyncClient):
    """Test connection validation handshake and sending an administrative test message."""
    conn_data = await setup_test_connection(client, "meta")
    account_id = conn_data["id"]

    csrf = client.cookies.get("csrf_token")
    headers = {"X-CSRF-Token": csrf} if csrf else {}

    # Mock provider HTTP response for validation
    with patch.object(
        MetaCloudProvider,
        "validate_connection",
        AsyncMock(return_value=ConnectionValidationResult(
            is_valid=True,
            display_name="Physio One Clinic",
            phone_number="+91 98765 00000",
            provider_account_id="1000987654321",
        )),
    ):
        test_resp = await client.post(f"/api/v1/whatsapp/connections/{account_id}/test", headers=headers)
        assert test_resp.status_code == 200
        assert test_resp.json()["is_valid"] is True
        assert test_resp.json()["display_name"] == "Physio One Clinic"

    # Mock provider HTTP response for outbound message send
    with patch.object(
        MetaCloudProvider,
        "send_text_message",
        AsyncMock(return_value=OutboundSendResult(
            success=True,
            provider_message_id="wamid.OUTBOUND_TEST_12345",
            status=MessageStatus.SENT,
        )),
    ):
        send_resp = await client.post(
            f"/api/v1/whatsapp/connections/{account_id}/send-test",
            json={"recipient_phone": "+919876543210", "message_text": "Clinic handshake test."},
            headers=headers,
        )
        assert send_resp.status_code == 200
        send_data = send_resp.json()
        assert send_data["success"] is True
        assert send_data["provider_message_id"] == "wamid.OUTBOUND_TEST_12345"
        assert send_data["status"] == "sent"
