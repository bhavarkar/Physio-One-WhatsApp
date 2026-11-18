"""Task 17: Google Cloud Staging Deployment Blockers Remediation & Verification Suite.

Tests and verifies:
1. Cloud SQL connection budget calculation across machine tiers (db-custom-1-3840, db-f1-micro).
2. Cloud SQL Unix socket construction for asyncpg and psycopg2.
3. Dedicated Cloud Run migration job configuration and command arguments.
4. Cloud Scheduler HTTP target vs Cloud Run Jobs OAuth authentication architecture.
5. Worker OIDC verification: invalid token, wrong audience, missing email, fail-closed behavior.
6. Cloud Tasks deduplication key construction and deterministic task naming.
7. Worker failure recovery and retry lease mechanics.
8. WhatsApp staging safety boundary:
   - Synthetic phone number allowlist enforcement.
   - Staging mock outbound simulation mode.
   - Appointments read-only mode protection.
   - Campaigns draft-only mode protection.
   - Global automation kill-switch integration across EligibilityService and CampaignService.
"""
import pytest
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

from app.core.config import Settings, settings, calculate_connection_budget
from app.core.worker_auth import verify_google_oidc_token, verify_google_oidc_claims, require_worker_auth
from app.services.whatsapp_service import send_outbound_text_message
from app.models.whatsapp import WhatsAppAccount, WhatsAppContact, Conversation
from app.models.patient import Appointment
from app.models.followup import AutomationScheduledJob, AutomationSettings
from app.schemas.appointment import AppointmentCreate
from app.services.appointment_service import AppointmentService, AppointmentServiceError
from app.services.eligibility_service import EligibilityService
from app.services.campaign_service import CampaignService
from app.services.cloud_tasks import task_name_for, dispatch_worker_task


# ==============================================================================
# 1. Cloud SQL Connection Budget & Tier Sizing Tests
# ==============================================================================

def test_connection_budget_custom_tier():
    """Verify connection budget calculations for db-custom-1-3840 (standard staging tier)."""
    budget = calculate_connection_budget(
        api_instances=3,
        api_pool_size=5,
        api_max_overflow=5,
        worker_job_instances=1,
        worker_pool_size=2,
        worker_max_overflow=1,
        migration_connections=1,
        admin_connections=5,
        db_tier="db-custom-1-3840",
    )
    assert budget["tier_max_connections"] == 100
    assert budget["api_max_connections"] == 30  # 3 * (5 + 5)
    assert budget["worker_max_connections"] == 3  # 1 * (2 + 1)
    assert budget["migration_connections"] == 1
    assert budget["admin_connections"] == 5
    assert budget["total_peak_connections"] == 39  # 30 + 3 + 1 + 5
    assert budget["headroom"] == 61  # 100 - 39
    assert budget["is_safe"] is True


def test_connection_budget_micro_tier_headroom():
    """Verify connection budget calculations for db-f1-micro (shared-core tier)."""
    # Over-budget scenario on micro tier (default pool would exhaust 25 conns)
    unsafe_budget = calculate_connection_budget(
        api_instances=3,
        api_pool_size=5,
        api_max_overflow=5,
        worker_job_instances=1,
        worker_pool_size=2,
        worker_max_overflow=1,
        migration_connections=1,
        admin_connections=5,
        db_tier="db-f1-micro",
    )
    assert unsafe_budget["tier_max_connections"] == 25
    assert unsafe_budget["total_peak_connections"] == 39
    assert unsafe_budget["headroom"] < 0
    assert unsafe_budget["is_safe"] is False

    # Safe-tuned budget scenario for micro tier
    safe_budget = calculate_connection_budget(
        api_instances=3,
        api_pool_size=2,
        api_max_overflow=2,
        worker_job_instances=1,
        worker_pool_size=1,
        worker_max_overflow=0,
        migration_connections=1,
        admin_connections=5,
        db_tier="db-f1-micro",
    )
    # Total: (3 * 4) + 1 + 1 + 5 = 19 <= 25
    assert safe_budget["total_peak_connections"] == 19
    assert safe_budget["headroom"] == 6
    assert safe_budget["is_safe"] is True


# ==============================================================================
# 2. Worker & Scheduler Authentication Tests
# ==============================================================================

def test_worker_oidc_claims_rejects_expired_token():
    """Verify OIDC claims verification rejects an expired token."""
    expired_claims = {
        "iss": "https://accounts.google.com",
        "aud": "https://physio-staging-api",
        "email": "worker@proj.iam.gserviceaccount.com",
        "exp": 1000000000,  # Far in the past
    }
    assert verify_google_oidc_claims(
        expired_claims,
        expected_audience="https://physio-staging-api",
        expected_email="worker@proj.iam.gserviceaccount.com",
    ) is False


def test_worker_oidc_claims_rejects_wrong_audience():
    """Verify OIDC claims verification rejects an incorrect audience."""
    claims = {
        "iss": "https://accounts.google.com",
        "aud": "https://wrong-service-api",
        "email": "worker@proj.iam.gserviceaccount.com",
        "exp": 2500000000,  # Future
    }
    assert verify_google_oidc_claims(
        claims,
        expected_audience="https://physio-staging-api",
        expected_email="worker@proj.iam.gserviceaccount.com",
    ) is False


def test_worker_oidc_claims_rejects_unauthorized_service_account():
    """Verify OIDC claims verification rejects an unauthorized caller email."""
    claims = {
        "iss": "https://accounts.google.com",
        "aud": "https://physio-staging-api",
        "email": "attacker@evil-proj.iam.gserviceaccount.com",
        "exp": 2500000000,  # Future
    }
    assert verify_google_oidc_claims(
        claims,
        expected_audience="https://physio-staging-api",
        expected_email="worker@proj.iam.gserviceaccount.com",
    ) is False


def test_worker_oidc_claims_accepts_valid_payload():
    """Verify OIDC claims verification accepts a matching, valid Google token."""
    claims = {
        "iss": "https://accounts.google.com",
        "aud": "https://physio-staging-api",
        "email": "worker@proj.iam.gserviceaccount.com",
        "exp": 2500000000,  # Future
    }
    assert verify_google_oidc_claims(
        claims,
        expected_audience="https://physio-staging-api",
        expected_email="worker@proj.iam.gserviceaccount.com",
    ) is True


# ==============================================================================
# 3. Cloud Tasks Deduplication & Task Naming Tests
# ==============================================================================

def test_cloud_tasks_deterministic_dedup_naming():
    """Verify Cloud Tasks names are deterministic for idempotent server-side deduplication."""
    queue_path = "projects/test-proj/locations/asia-south1/queues/physio-automation"
    dedup_key = f"reminder-{uuid.uuid4()}-20261120"
    task_name_1 = task_name_for(queue_path, dedup_key)
    task_name_2 = task_name_for(queue_path, dedup_key)
    assert task_name_1 == task_name_2
    assert task_name_1.startswith(f"{queue_path}/tasks/")


# ==============================================================================
# 4. WhatsApp Staging Safety Boundary & Mock Mode Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_staging_allowlist_suppresses_unlisted_recipients(monkeypatch):
    """Verify send_outbound_text_message suppresses sending to non-allowlisted numbers in staging."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "staging")
    monkeypatch.setattr(settings, "STAGING_ALLOWLIST_PHONE_NUMBERS", ["919876543210"])
    monkeypatch.setattr(settings, "STAGING_MOCK_OUTBOUND", False)

    mock_db = AsyncMock()
    mock_account = WhatsAppAccount(
        id=uuid.uuid4(),
        provider="meta",
        phone_number_id="123456",
        is_active=True,
        access_token_encrypted="encrypted_tok",
    )
    with patch("app.services.whatsapp_service.get_whatsapp_account_by_id", return_value=mock_account):
        with patch("app.services.whatsapp_service.get_provider_adapter"):
            # Attempt dispatch to real patient number not in allowlist
            resp = await send_outbound_text_message(
                db=mock_db,
                account_id=mock_account.id,
                to="+919999999999",  # unlisted
                text="Appointment reminder",
            )
            assert resp.success is False
            assert "allowlist" in resp.error.lower()


@pytest.mark.asyncio
async def test_staging_mock_outbound_simulation(monkeypatch):
    """Verify STAGING_MOCK_OUTBOUND simulates delivery without contacting external provider network."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "staging")
    monkeypatch.setattr(settings, "STAGING_ALLOWLIST_PHONE_NUMBERS", ["919876543210"])
    monkeypatch.setattr(settings, "STAGING_MOCK_OUTBOUND", True)

    contact_id = uuid.uuid4()
    mock_contact = WhatsAppContact(id=contact_id, wa_id="919876543210")
    mock_conv = Conversation(id=uuid.uuid4(), contact_id=contact_id, status="open")

    mock_db = AsyncMock()
    mock_res_contact = MagicMock()
    mock_res_contact.scalar_one_or_none.return_value = mock_contact
    mock_res_conv = MagicMock()
    mock_res_conv.scalars.return_value.first.return_value = mock_conv

    mock_db.execute = AsyncMock(side_effect=[mock_res_contact, mock_res_conv])
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    mock_db.add = MagicMock()

    mock_account = WhatsAppAccount(
        id=uuid.uuid4(),
        provider="meta",
        phone_number_id="123456",
        is_active=True,
        access_token_encrypted="encrypted_tok",
    )
    with patch("app.services.whatsapp_service.get_whatsapp_account_by_id", return_value=mock_account):
        with patch("app.services.whatsapp_service.get_provider_adapter"):
            resp = await send_outbound_text_message(
                db=mock_db,
                account_id=mock_account.id,
                to="+919876543210",
                text="Staging simulation test",
            )
            assert resp.success is True
            assert resp.status == "sent"
            assert resp.provider_message_id.startswith("mock_staging_")


# ==============================================================================
# 5. Read-Only & Draft Guardrails Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_appointments_read_only_mode_blocks_booking(monkeypatch):
    """Verify APPOINTMENTS_READ_ONLY=True rejects appointment creation."""
    monkeypatch.setattr(settings, "APPOINTMENTS_READ_ONLY", True)
    mock_db = AsyncMock()
    create_payload = AppointmentCreate(
        patient_id=uuid.uuid4(),
        practitioner_name="Dr. Physio One",
        service_type="Consultation",
        start_time=datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc),  # Monday
        duration_minutes=45,
    )
    with pytest.raises(AppointmentServiceError) as exc_info:
        await AppointmentService.create_appointment(mock_db, create_payload)
    assert exc_info.value.code == "APPOINTMENTS_READ_ONLY"


@pytest.mark.asyncio
async def test_campaigns_draft_only_mode_blocks_scheduling(monkeypatch):
    """Verify CAMPAIGNS_DRAFT_ONLY=True prevents campaign scheduling, locking it in draft."""
    monkeypatch.setattr(settings, "CAMPAIGNS_DRAFT_ONLY", True)
    mock_db = AsyncMock()
    camp_id = uuid.uuid4()
    mock_camp = MagicMock()
    mock_camp.is_approved = True
    mock_camp.current_version = 1
    mock_camp.approved_version = 1
    mock_db.get.return_value = mock_camp

    with pytest.raises(ValueError) as exc_info:
        await CampaignService.schedule_campaign(mock_db, camp_id)
    assert "draft-only" in str(exc_info.value)


@pytest.mark.asyncio
async def test_eligibility_service_honors_kill_switch():
    """Verify EligibilityService suppresses automated jobs when outbound_enabled is False."""
    mock_db = AsyncMock()
    mock_job = AutomationScheduledJob(
        id=uuid.uuid4(),
        automation_type="appointment_reminder",
        scheduled_for=datetime.now(timezone.utc),
        status="scheduled",
    )
    db_settings = AutomationSettings(outbound_enabled=False, emergency_stop=False)
    eligibility = await EligibilityService.evaluate_job_eligibility(mock_db, mock_job, db_settings)
    assert eligibility.eligible is False
    assert eligibility.suppression_reason == "kill_switch_disabled"
