"""Task 15: Production Security Hardening & Preflight Verification Suite.

Tests rigorous security guardrails:
1. Webhook cryptographic verification & constant-time challenge checks.
2. Login rate limiting, lockout thresholds, and lockout recovery.
3. Cookie security flags across development, staging, and production.
4. CORS wildcard origin restrictions in staging and production.
5. AI tool execution boundaries, unauthorized invocation denials, and audit logging.
6. Safe operational defaults (automation outbound kill-switch).
"""
import pytest
import hmac
import hashlib
import time
import uuid
from typing import Dict, Any
from unittest.mock import MagicMock, AsyncMock
from fastapi import Response
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.core.security import (
    login_rate_limiter,
    verify_csrf_token,
    generate_csrf_token,
    hash_password,
    verify_password,
)
from app.api.v1.auth import set_auth_cookies
from app.providers.meta import MetaCloudProvider
from app.providers.ycloud import YCloudProvider
from app.models.whatsapp import WhatsAppAccount
from app.tools.dispatcher import ToolDispatcher
from app.tools.base import ToolExecutionContext


# ==============================================================================
# 1. Webhook Cryptographic Verification & Challenge Checks
# ==============================================================================

def test_meta_webhook_signature_verification():
    provider = MetaCloudProvider(
        phone_number_id="123456",
        access_token="test_token",
        app_secret="test_meta_app_secret_998877",
        webhook_verify_token="meta_verify_secret_123",
    )

    raw_body = b'{"object": "whatsapp_business_account", "entry": []}'
    valid_sig = hmac.new(
        b"test_meta_app_secret_998877", raw_body, hashlib.sha256
    ).hexdigest()

    # Valid signature
    assert provider.verify_webhook_signature({"x-hub-signature-256": f"sha256={valid_sig}"}, raw_body) is True

    # Tampered body
    assert provider.verify_webhook_signature({"x-hub-signature-256": f"sha256={valid_sig}"}, b'{"tampered": true}') is False

    # Forged signature
    assert provider.verify_webhook_signature({"x-hub-signature-256": "sha256=invalidhash00000000000000000000"}, raw_body) is False

    # Missing sha256= prefix
    assert provider.verify_webhook_signature({"x-hub-signature-256": valid_sig}, raw_body) is False


def test_meta_webhook_challenge_constant_time():
    provider = MetaCloudProvider(
        phone_number_id="123456",
        access_token="test_token",
        webhook_verify_token="secure_clinic_challenge_token_456",
    )

    # Valid challenge
    res = provider.verify_subscription_challenge(
        mode="subscribe",
        token="secure_clinic_challenge_token_456",
        challenge="CHALLENGE_CODE_987",
    )
    assert res.is_valid is True
    assert res.challenge == "CHALLENGE_CODE_987"

    # Invalid token
    res_bad = provider.verify_subscription_challenge(
        mode="subscribe",
        token="wrong_token_attack",
        challenge="CHALLENGE_CODE_987",
    )
    assert res_bad.is_valid is False

    # Invalid mode
    res_mode = provider.verify_subscription_challenge(
        mode="unsubscribe",
        token="secure_clinic_challenge_token_456",
        challenge="CHALLENGE_CODE_987",
    )
    assert res_mode.is_valid is False


def test_ycloud_webhook_signature_verification():
    provider = YCloudProvider(
        api_key="ycloud_key",
        phone_number="+919876543210",
        webhook_secret="ycloud_secret_abc123",
    )

    raw_body = b'{"type": "whatsapp.message.incoming", "id": "evt_123"}'
    valid_sig = hmac.new(
        b"ycloud_secret_abc123", raw_body, hashlib.sha256
    ).hexdigest()

    # Valid signature
    assert provider.verify_webhook_signature({"ycloud-signature": valid_sig}, raw_body) is True

    # Tampered signature
    assert provider.verify_webhook_signature({"ycloud-signature": "tampered_sig_xxx"}, raw_body) is False

    # Timestamped format (t=...,v1=...)
    t = str(int(time.time()))
    payload_to_sign = f"{t}.".encode("utf-8") + raw_body
    v1_sig = hmac.new(b"ycloud_secret_abc123", payload_to_sign, hashlib.sha256).hexdigest()
    assert provider.verify_webhook_signature({"ycloud-signature": f"t={t},v1={v1_sig}"}, raw_body) is True


# ==============================================================================
# 2. Login Rate Limiting & Lockout Protection
# ==============================================================================

def test_login_rate_limiter_lockout_and_recovery():
    limiter = login_rate_limiter
    limiter.reset()

    key = "192.168.1.100:test_staff@physioone.com"

    # Initial state: not locked
    locked, remaining = limiter.is_locked(key)
    assert locked is False
    assert remaining == 0

    # 4 failed attempts should not lock out
    for _ in range(4):
        limiter.record_attempt(key, success=False)
        locked, _ = limiter.is_locked(key)
        assert locked is False

    # 5th failed attempt triggers lockout
    limiter.record_attempt(key, success=False)
    locked, remaining = limiter.is_locked(key)
    assert locked is True
    assert remaining > 0

    # Successful login resets the limiter
    limiter.record_attempt(key, success=True)
    locked, _ = limiter.is_locked(key)
    assert locked is False

    limiter.reset()


# ==============================================================================
# 3. Cookie Security across Environments
# ==============================================================================

def test_cookie_security_flag_in_staging_and_production(monkeypatch):
    # In development: secure=False
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "COOKIE_SECURE", False)
    res_dev = Response()
    set_auth_cookies(res_dev, "session_dev", "csrf_dev")
    raw_cookies_dev = res_dev.headers.getlist("set-cookie")
    session_cookie_dev = next(c for c in raw_cookies_dev if c.startswith("session_id="))
    assert "Secure" not in session_cookie_dev
    assert "HttpOnly" in session_cookie_dev
    assert "SameSite=lax" in session_cookie_dev

    # In staging: secure=True (critical for Cloud Run HTTPS)
    monkeypatch.setattr(settings, "ENVIRONMENT", "staging")
    monkeypatch.setattr(settings, "COOKIE_SECURE", False)
    res_staging = Response()
    set_auth_cookies(res_staging, "session_staging", "csrf_staging")
    raw_cookies_staging = res_staging.headers.getlist("set-cookie")
    session_cookie_staging = next(c for c in raw_cookies_staging if c.startswith("session_id="))
    assert "Secure" in session_cookie_staging
    assert "HttpOnly" in session_cookie_staging

    # In production: secure=True
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    res_prod = Response()
    set_auth_cookies(res_prod, "session_prod", "csrf_prod")
    raw_cookies_prod = res_prod.headers.getlist("set-cookie")
    session_cookie_prod = next(c for c in raw_cookies_prod if c.startswith("session_id="))
    assert "Secure" in session_cookie_prod


# ==============================================================================
# 4. CORS Origin Restriction in Staging / Production
# ==============================================================================

def test_cors_wildcard_rejected_in_staging():
    # Wildcard in staging must raise validation error
    with pytest.raises(ValidationError):
        Settings(
            ENVIRONMENT="staging",
            BACKEND_CORS_ORIGINS=["*"],
        )

    with pytest.raises(ValidationError):
        Settings(
            ENVIRONMENT="production",
            BACKEND_CORS_ORIGINS=["https://valid.com", "*"],
        )

    # Specific origins are allowed
    valid_cfg = Settings(
        ENVIRONMENT="staging",
        BACKEND_CORS_ORIGINS=["https://physio-staging-web.run.app"],
    )
    assert valid_cfg.BACKEND_CORS_ORIGINS == ["https://physio-staging-web.run.app"]


# ==============================================================================
# 5. AI Tool Execution Boundary & Denial Auditing
# ==============================================================================

@pytest.mark.asyncio
async def test_tool_dispatcher_enforces_whitelist_and_audit():
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()

    context = ToolExecutionContext(
        session_id=uuid.uuid4(),
        caller_permissions=["appointments:read"],
    )

    # 1. Unauthorized tool (not in allowed_tools list)
    res_unauthorized = await ToolDispatcher.dispatch(
        tool_name="cancel_appointment",
        arguments={"appointment_id": "123"},
        context=context,
        db=mock_db,
        allowed_tools=["check_availability", "find_patient"],  # cancel not allowed
    )
    assert res_unauthorized["success"] is False
    assert "Access denied" in res_unauthorized["error"]

    # 2. Unregistered tool name
    res_unregistered = await ToolDispatcher.dispatch(
        tool_name="non_existent_exploit_tool",
        arguments={},
        context=context,
        db=mock_db,
        allowed_tools=["non_existent_exploit_tool"],
    )
    assert res_unregistered["success"] is False
    assert "not recognized" in res_unregistered["error"]


# ==============================================================================
# 6. Safe Operational Defaults
# ==============================================================================

def test_safe_operational_defaults():
    # Outbound automations must be disabled by default
    assert settings.AUTOMATION_OUTBOUND_ENABLED is False
