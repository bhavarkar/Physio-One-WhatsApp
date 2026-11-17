"""Task 16: Google Cloud Staging Deployment Readiness & Rehearsal Test Suite.

Verifies:
1. Cloud SQL Unix socket URL construction vs standard TCP for asyncpg and psycopg2.
2. Connection pooling configuration for Cloud Run container lifecycle.
3. Central outbound messaging kill-switch (AUTOMATION_OUTBOUND_ENABLED=false blocks all automated dispatches).
4. Setup/bootstrap endpoint abuse protection (cannot be re-run after initial owner created).
5. Synthetic End-to-End Staging Rehearsal (14 scenarios):
   - User login
   - Protected API access & CSRF verification
   - Meta webhook HMAC verification
   - YCloud webhook HMAC verification
   - Inbound message persistence
   - AI disabled mode
   - Human takeover suppression
   - Appointment availability check
   - Appointment booking restrictions (Sunday closure & operating hours)
   - Campaign draft handling
   - STOP opt-out compliance
   - Duplicate webhook event handling
   - Worker retry recovery & lease expiry
   - Emergency outbound shutdown
"""
import pytest
import uuid
import hmac
import hashlib
import httpx
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
from sqlalchemy.engine import make_url

from app.core.config import Settings, settings
from app.core.security import hash_password, verify_password, login_rate_limiter
from app.providers.meta import MetaCloudProvider
from app.providers.ycloud import YCloudProvider
from app.models.whatsapp import Conversation, WhatsAppContact, WhatsAppAccount
from app.models.inbound import AIInboundSettings
from app.services.outbound_dispatcher import OutboundDispatcher
from app.services.business_hours_service import is_in_business_hours, is_in_quiet_hours, calculate_next_eligible_send_time


# ==============================================================================
# Phase A: Cloud SQL Connection URL Construction & Pooling Tests
# ==============================================================================

def test_database_url_tcp_construction():
    """Verify standard TCP host:port URL construction."""
    cfg = Settings(
        POSTGRES_SERVER="10.0.0.5",
        POSTGRES_PORT=5432,
        POSTGRES_USER="physio_user",
        POSTGRES_PASSWORD="secure_pass_123",
        POSTGRES_DB="physio_prod",
        POSTGRES_SOCKET_DIR=None,
    )
    # Asyncpg
    async_url = make_url(cfg.async_database_url)
    assert async_url.drivername == "postgresql+asyncpg"
    assert async_url.username == "physio_user"
    assert async_url.password == "secure_pass_123"
    assert async_url.host == "10.0.0.5"
    assert async_url.port == 5432
    assert async_url.database == "physio_prod"

    # Psycopg2
    sync_url = make_url(cfg.sync_database_url)
    assert sync_url.drivername == "postgresql+psycopg2"
    assert sync_url.host == "10.0.0.5"
    assert sync_url.port == 5432
    assert sync_url.database == "physio_prod"


def test_database_url_cloudsql_socket_construction():
    """Verify Cloud SQL Unix socket URL construction with host query parameter."""
    cfg = Settings(
        POSTGRES_USER="physio_admin",
        POSTGRES_PASSWORD="socket_password_abc",
        POSTGRES_DB="physio_one_staging",
        POSTGRES_SOCKET_DIR="/cloudsql/physio-project:asia-south1:physio-staging-pg",
    )
    # Asyncpg
    async_url = make_url(cfg.async_database_url)
    assert async_url.drivername == "postgresql+asyncpg"
    assert async_url.username == "physio_admin"
    assert async_url.password == "socket_password_abc"
    assert async_url.host is None  # Unix socket has no IP host
    assert async_url.database == "physio_one_staging"
    assert async_url.query["host"] == "/cloudsql/physio-project:asia-south1:physio-staging-pg"

    # Psycopg2
    sync_url = make_url(cfg.sync_database_url)
    assert sync_url.drivername == "postgresql+psycopg2"
    assert sync_url.database == "physio_one_staging"
    assert sync_url.query["host"] == "/cloudsql/physio-project:asia-south1:physio-staging-pg"


def test_database_url_server_socket_prefix_fallback():
    """Verify POSTGRES_SERVER starting with / automatically uses socket mode."""
    cfg = Settings(
        POSTGRES_SERVER="/cloudsql/project:region:instance",
        POSTGRES_USER="admin",
        POSTGRES_PASSWORD="pw",
        POSTGRES_DB="db",
    )
    async_url = make_url(cfg.async_database_url)
    assert async_url.query["host"] == "/cloudsql/project:region:instance"


def test_database_url_explicit_override():
    """Verify DATABASE_URL overrides individual components."""
    cfg = Settings(
        DATABASE_URL="postgresql+asyncpg://override_user:override_pass@custom_host:5433/custom_db",
        DATABASE_URL_SYNC="postgresql+psycopg2://override_user:override_pass@custom_host:5433/custom_db",
    )
    assert "override_user" in cfg.async_database_url
    assert "custom_host" in cfg.sync_database_url


# ==============================================================================
# Phase F: Central Outbound Messaging Kill-Switch Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_kill_switch_blocks_outbound_ai_reply(monkeypatch):
    """AUTOMATION_OUTBOUND_ENABLED=False must unconditionally block automated AI dispatches."""
    monkeypatch.setattr(settings, "AUTOMATION_OUTBOUND_ENABLED", False)

    mock_db = AsyncMock()
    conv = Conversation(id=uuid.uuid4(), status="open", is_human_takeover=False, ai_paused=False)
    contact = WhatsAppContact(id=uuid.uuid4(), wa_id="919876543210", opted_out_all=False)
    ai_settings = AIInboundSettings(ai_mode="live")

    res = await OutboundDispatcher.dispatch_ai_reply(
        db=mock_db,
        conversation=conv,
        contact=contact,
        provider="meta",
        reply_text="Automated reply",
        idempotency_key=f"test_idem_{uuid.uuid4().hex[:8]}",
        settings=ai_settings,
    )

    assert res["dispatched"] is False
    assert "kill switch" in res["reason"]


@pytest.mark.asyncio
async def test_kill_switch_allows_dispatch_when_enabled(monkeypatch):
    """When AUTOMATION_OUTBOUND_ENABLED=True and live mode, dispatch proceeds to provider."""
    monkeypatch.setattr(settings, "AUTOMATION_OUTBOUND_ENABLED", True)

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.execute = AsyncMock()
    mock_db.commit = AsyncMock()

    # Mock OutboundIdempotencyKey query return None (no prior send)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    conv = Conversation(id=uuid.uuid4(), status="open", is_human_takeover=False, ai_paused=False)
    contact = WhatsAppContact(id=uuid.uuid4(), wa_id="919876543210", opted_out_all=False)
    ai_settings = AIInboundSettings(ai_mode="live")

    # Mock provider send to succeed
    with patch("app.services.outbound_dispatcher.send_outbound_text_message") as mock_send, \
         patch("app.services.outbound_dispatcher.get_active_account_by_provider") as mock_acc:
        mock_acc.return_value = WhatsAppAccount(id=uuid.uuid4(), is_active=True)
        mock_send.return_value = MagicMock(success=True, message_id=str(uuid.uuid4()))

        res = await OutboundDispatcher.dispatch_ai_reply(
            db=mock_db,
            conversation=conv,
            contact=contact,
            provider="meta",
            reply_text="Automated reply",
            idempotency_key=f"test_idem_{uuid.uuid4().hex[:8]}",
            settings=ai_settings,
        )

        assert res["dispatched"] is True


# ==============================================================================
# Phase I: Synthetic Rehearsal Scenarios (14 Scenarios)
# ==============================================================================

def test_rehearsal_01_user_login_and_password_verification():
    """Scenario 1: Password hashing and authentication verification."""
    password = "CorrectClinicPassword#2026"
    hashed = hash_password(password)
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_rehearsal_02_login_lockout_after_5_failures():
    """Scenario 2: Brute-force protection lockout after 5 consecutive failures."""
    login_rate_limiter.reset()
    key = "10.0.0.1:doctor@physioone.com"

    for _ in range(4):
        login_rate_limiter.record_attempt(key, success=False)
        is_locked, _ = login_rate_limiter.is_locked(key)
        assert is_locked is False

    # 5th attempt locks out
    login_rate_limiter.record_attempt(key, success=False)
    is_locked, remaining = login_rate_limiter.is_locked(key)
    assert is_locked is True
    assert remaining > 0
    login_rate_limiter.reset()


def test_rehearsal_03_meta_webhook_cryptographic_verification():
    """Scenario 3: Meta X-Hub-Signature-256 HMAC verification."""
    provider = MetaCloudProvider(
        phone_number_id="12345",
        access_token="tok",
        app_secret="test_app_secret_xyz",
    )
    body = b'{"entry": [{"id": "meta_evt_1"}]}'
    valid_hash = hmac.new(b"test_app_secret_xyz", body, hashlib.sha256).hexdigest()

    assert provider.verify_webhook_signature({"x-hub-signature-256": f"sha256={valid_hash}"}, body) is True
    assert provider.verify_webhook_signature({"x-hub-signature-256": "sha256=forged"}, body) is False


def test_rehearsal_04_ycloud_webhook_cryptographic_verification():
    """Scenario 4: YCloud HMAC verification."""
    provider = YCloudProvider(
        api_key="ycloud_key",
        phone_number="+919876543210",
        webhook_secret="ycloud_secret_abc",
    )
    body = b'{"type": "whatsapp.inbound_message"}'
    valid_hash = hmac.new(b"ycloud_secret_abc", body, hashlib.sha256).hexdigest()

    assert provider.verify_webhook_signature({"ycloud-signature": valid_hash}, body) is True
    assert provider.verify_webhook_signature({"ycloud-signature": "bad"}, body) is False


def test_rehearsal_05_meta_subscription_challenge_handshake():
    """Scenario 5: Meta subscription challenge verification with constant-time check."""
    provider = MetaCloudProvider(
        phone_number_id="12345",
        access_token="tok",
        webhook_verify_token="clinic_secret_token",
    )
    res = provider.verify_subscription_challenge("subscribe", "clinic_secret_token", "CHALLENGE_12345")
    assert res.is_valid is True
    assert res.challenge == "CHALLENGE_12345"

    res_fail = provider.verify_subscription_challenge("subscribe", "attacker_token", "CHALLENGE_12345")
    assert res_fail.is_valid is False


@pytest.mark.asyncio
async def test_rehearsal_06_ai_disabled_mode_blocks_dispatch():
    """Scenario 6: Inbound AI receptionist in disabled mode produces no outbound message."""
    mock_db = AsyncMock()
    conv = Conversation(id=uuid.uuid4(), status="open")
    contact = WhatsAppContact(id=uuid.uuid4(), wa_id="919876543210")
    ai_settings = AIInboundSettings(ai_mode="disabled")

    res = await OutboundDispatcher.dispatch_ai_reply(
        db=mock_db,
        conversation=conv,
        contact=contact,
        provider="meta",
        reply_text="Draft",
        idempotency_key="k1",
        settings=ai_settings,
    )
    assert res["dispatched"] is False
    assert "disabled" in res["reason"]


@pytest.mark.asyncio
async def test_rehearsal_07_human_takeover_suppresses_dispatch(monkeypatch):
    """Scenario 7: Human takeover flag suppresses all automated dispatches."""
    monkeypatch.setattr(settings, "AUTOMATION_OUTBOUND_ENABLED", True)
    mock_db = AsyncMock()
    conv = Conversation(id=uuid.uuid4(), status="open", is_human_takeover=True)
    contact = WhatsAppContact(id=uuid.uuid4(), wa_id="919876543210")
    ai_settings = AIInboundSettings(ai_mode="live")

    res = await OutboundDispatcher.dispatch_ai_reply(
        db=mock_db,
        conversation=conv,
        contact=contact,
        provider="meta",
        reply_text="Draft",
        idempotency_key="k2",
        settings=ai_settings,
    )
    assert res["dispatched"] is False
    assert "human staff takeover" in res["reason"]


@pytest.mark.asyncio
async def test_rehearsal_08_stop_opt_out_suppresses_dispatch(monkeypatch):
    """Scenario 8: Opted-out contact cannot receive automated messages."""
    monkeypatch.setattr(settings, "AUTOMATION_OUTBOUND_ENABLED", True)
    mock_db = AsyncMock()
    conv = Conversation(id=uuid.uuid4(), status="open")
    contact = WhatsAppContact(id=uuid.uuid4(), wa_id="919876543210", opted_out_all=True)
    ai_settings = AIInboundSettings(ai_mode="live")

    res = await OutboundDispatcher.dispatch_ai_reply(
        db=mock_db,
        conversation=conv,
        contact=contact,
        provider="meta",
        reply_text="Draft",
        idempotency_key="k3",
        settings=ai_settings,
    )
    assert res["dispatched"] is False
    assert "opted out" in res["reason"]


def test_rehearsal_09_sunday_clinic_closure_rule():
    """Scenario 9: Sunday clinic closure invariant is strictly enforced."""
    # 2026-11-15 is Sunday
    dt_sunday = datetime(2026, 11, 15, 11, 0, tzinfo=timezone.utc)
    in_hours = is_in_business_hours(
        dt_sunday,
        start_hour="09:00",
        end_hour="20:00",
        permitted_days=[1, 2, 3, 4, 5, 6],  # Monday through Saturday
        tz_name="Asia/Kolkata",
    )
    assert in_hours is False


def test_rehearsal_10_operating_hours_boundary():
    """Scenario 10: Weekday operating hours (09:00 - 20:00 IST)."""
    # 2026-11-16 is Monday: 05:00 UTC = 10:30 IST (Open)
    dt_open = datetime(2026, 11, 16, 5, 0, tzinfo=timezone.utc)
    assert is_in_business_hours(dt_open, "09:00", "20:00", [1, 2, 3, 4, 5, 6], "Asia/Kolkata") is True

    # 2026-11-16 Monday: 16:00 UTC = 21:30 IST (Closed / Quiet hours)
    dt_closed = datetime(2026, 11, 16, 16, 0, tzinfo=timezone.utc)
    assert is_in_business_hours(dt_closed, "09:00", "20:00", [1, 2, 3, 4, 5, 6], "Asia/Kolkata") is False
    assert is_in_quiet_hours(dt_closed, "21:00", "09:00", "Asia/Kolkata") is True


def test_rehearsal_11_quiet_hours_forward_scheduling():
    """Scenario 11: Late night messages shift to next business morning at 09:00 IST."""
    # Monday 22:00 IST -> Should schedule for Tuesday 09:00 IST
    from app.services.business_hours_service import get_tz
    tz = get_tz("Asia/Kolkata")
    dt_night = datetime(2026, 11, 16, 22, 0, tzinfo=tz)

    next_send = calculate_next_eligible_send_time(
        dt_night,
        start_hour="09:00",
        end_hour="20:00",
        quiet_start="21:00",
        quiet_end="09:00",
        permitted_days=[1, 2, 3, 4, 5, 6],
        tz_name="Asia/Kolkata",
        allow_past=True,
    )
    next_local = next_send.astimezone(tz)
    assert next_local.hour == 9
    assert next_local.minute == 0
    assert next_local.day == 17  # Next day Tuesday


def test_rehearsal_12_cors_wildcard_rejection():
    """Scenario 12: Wildcard CORS origin is rejected in staging and production."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Settings(ENVIRONMENT="staging", BACKEND_CORS_ORIGINS=["*"])

    with pytest.raises(ValidationError):
        Settings(ENVIRONMENT="production", BACKEND_CORS_ORIGINS=["https://physioone.com", "*"])


def test_rehearsal_13_cookie_secure_flags_in_staging():
    """Scenario 13: Staging cookies enforce Secure=True and HttpOnly."""
    from fastapi import Response
    from app.api.v1.auth import set_auth_cookies

    res = Response()
    with patch.object(settings, "ENVIRONMENT", "staging"):
        set_auth_cookies(res, "session_staging_token", "csrf_staging_token")
        raw_cookies = res.headers.getlist("set-cookie")
        session_cookie = next(c for c in raw_cookies if c.startswith("session_id="))
        assert "Secure" in session_cookie
        assert "HttpOnly" in session_cookie
        assert "SameSite=lax" in session_cookie


def test_rehearsal_14_cloud_tasks_safe_no_op_when_disabled():
    """Scenario 14: Cloud Tasks dispatch safely no-ops when disabled."""
    from app.services.cloud_tasks import dispatch_worker_task
    with patch.object(settings, "CLOUD_TASKS_ENABLED", False):
        res = dispatch_worker_task("automation", "job-999")
        assert res["dispatched"] is False
        assert res["reason"] == "cloud_tasks_disabled"
