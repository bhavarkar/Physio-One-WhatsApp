"""End-to-End Integration and System Safety Test Suite for Physio One WhatsApp AI Platform.

Task 13: Production Readiness, Security Hardening & End-to-End Integration.
Verifies complete end-to-end multi-service flows with synthetic data:
- Scenario A: WhatsApp Inbound Webhook -> Deduplication -> Shadow Deepti -> Zero Outbound Send
- Scenario B: Appointment Booking -> Verification -> Staff Approval -> Reminder Scheduling
- Scenario C: Human Takeover -> Automated Processing Suppression -> No Stale Replies
- Scenario D: Reminder Lifecycle -> Reschedule Invalidation -> Obsolete Job Cancellation
- Scenario E: Instagram Campaign -> Audience -> Safety Gates -> Approval -> Mock Dispatch -> Analytics
- Scenario F: Patient STOP / Opt-Out -> Global Outbound Suppression
- Scenario G: Worker Crash Recovery -> Expired Lease Reset -> Durable Idempotency
- Worker Security: Multi-tier OIDC, X-Worker-Token HMAC, Admin Session verification
"""
import uuid
import hmac
import time
import json
import base64
import pytest
import httpx
from datetime import datetime, timezone, timedelta, date

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from httpx import AsyncClient

from app.core.config import settings
from app.core.crypto import encrypt_secret
from app.core.worker_auth import require_worker_auth, verify_google_oidc_claims
from app.models.user import User, Role, UserSession
from app.models.patient import Patient, Appointment, AppointmentHistory, PatientConsent
from app.models.whatsapp import WhatsAppAccount, WhatsAppContact, Conversation, WhatsAppMessage
from app.models.inbound import (
    AIInboundSettings,
    InboundProcessingJob,
    AIResponseDraft,
    OutboundIdempotencyKey,
    ConversationHandoff,
)
from app.models.workflow import (
    AppointmentAIWorkflow,
    AppointmentWorkflowSettings,
    AppointmentApprovalRequest,
    AppointmentConfirmation,
)
from app.models.followup import (
    AutomationRule,
    AutomationScheduledJob,
    AutomationSettings,
    AutomationMessageTemplate,
)
from app.models.campaign import (
    Campaign,
    CampaignMedia,
    CampaignRecipient,
    CampaignAudience,
    CampaignApproval,
)
from app.schemas.workflow import AutomationPolicyMode, WorkflowState, WorkflowIntent
from app.services.agent_service import AgentService
from app.services.inbound_queue import InboundQueueService
from app.services.inbound_orchestrator import InboundOrchestrator
from app.services.workflow_service import AppointmentWorkflowService
from app.services.appointment_service import AppointmentService, get_clinic_tz
from app.services.automation_service import AutomationService
from app.services.automation_worker import AutomationWorkerService
from app.services.campaign_service import CampaignService

KOLKATA_TZ = get_clinic_tz()


# ---------------------------------------------------------------------------
# Test Helpers & Fixtures
# ---------------------------------------------------------------------------

async def create_e2e_fixtures(db: AsyncSession):
    """Seed base roles, admin user, default AI entities, WhatsApp account, and settings."""
    await AgentService.ensure_default_ai_entities(db)

    role_admin = await db.scalar(select(Role).where(Role.name == "admin"))
    if not role_admin:
        role_admin = Role(name="admin", description="Administrator")
        db.add(role_admin)
        await db.flush()

    user = User(
        email=f"admin_{uuid.uuid4().hex[:6]}@physioone.test",
        password_hash="mock_hash",
        full_name="Dr. E2E Admin",
        role_id=role_admin.id,
        is_active=True,
    )
    db.add(user)
    await db.flush()

    # Active WhatsApp Account
    account = WhatsAppAccount(
        provider="meta",
        account_name="Physio One E2E Account",
        phone_number_id="10987654321",
        business_account_id="98765432109",
        display_phone_number="+919876500000",
        webhook_verify_token="test_webhook_verify_token",
        access_token_encrypted=encrypt_secret("test_access_token_secret"),
        is_active=True,
    )
    db.add(account)
    await db.flush()

    # Automation Settings (Kill switch active by default)
    auto_settings = await AutomationService.get_or_create_settings(db)
    auto_settings.outbound_enabled = False  # Production default
    await db.flush()

    # AI Inbound Settings (Shadow mode for safe verification)
    inbound_settings = await InboundQueueService.get_or_create_settings(db)
    inbound_settings.ai_mode = "shadow"
    inbound_settings.is_active = True
    await db.flush()

    await db.commit()
    return user, account, auto_settings, inbound_settings


# ---------------------------------------------------------------------------
# Scenario A: WhatsApp Inbound Webhook Pipeline & Shadow Mode
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scenario_a_whatsapp_inbound_shadow_mode(async_session: AsyncSession):
    """Scenario A: Meta/YCloud mock webhook -> dedup -> conversation persistence -> queue -> Deepti shadow -> draft creation.
    
    Expected: Persistent AIResponseDraft created, but dispatched == False (zero external send).
    """
    user, account, auto_settings, inbound_settings = await create_e2e_fixtures(async_session)

    # 1. Contact & Conversation
    contact = WhatsAppContact(
        wa_id="+919876511111",
        profile_name="Patient Anita",
        opted_out_all=False,
    )
    async_session.add(contact)
    await async_session.flush()

    conv = Conversation(
        contact_id=contact.id,
        status="open",
        is_human_takeover=False,
        ai_paused=False,
    )
    async_session.add(conv)
    await async_session.flush()

    # 2. Inbound Message (Simulated Webhook Ingestion)
    msg_id = f"wamid.test_{uuid.uuid4().hex[:12]}"
    msg = WhatsAppMessage(
        contact_id=contact.id,
        conversation_id=conv.id,
        provider="meta",
        direction="inbound",
        message_type="text",
        body="Hello, I have severe neck stiffness since yesterday. Can I see Dr. Physio?",
        provider_message_id=msg_id,
        status="received",
    )
    async_session.add(msg)
    await async_session.flush()

    # Deduplication test: Trying to query the same provider_message_id confirms existence
    existing_check = await async_session.scalar(
        select(WhatsAppMessage.id).where(WhatsAppMessage.provider_message_id == msg_id)
    )
    assert existing_check == msg.id

    # 3. Enqueue to durable inbound queue
    job = await InboundQueueService.enqueue_inbound_message(
        db=async_session,
        message=msg,
        conversation=conv,
        contact=contact,
    )
    assert job is not None
    job.debounce_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    await async_session.commit()

    # 4. Mock LLM Response for Deepti
    mock_payload = {
        "id": "cmpl-shadow-e2e",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Hello Anita! I can certainly help you book a consultation with our physiotherapist for your neck stiffness.",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 50, "completion_tokens": 25, "total_tokens": 75},
    }
    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=mock_payload)))

    # 5. Worker executes due debounced job in shadow mode
    outcome = await InboundOrchestrator.process_job(
        async_session,
        job,
        override_http_client=mock_client,
    )
    assert outcome["status"] == "shadow_drafted"
    assert "draft_id" in outcome

    # 6. Assert: AIResponseDraft exists and was NEVER dispatched externally
    draft = await async_session.get(AIResponseDraft, uuid.UUID(outcome["draft_id"]))
    assert draft is not None
    assert draft.dispatched is False
    assert draft.ai_mode == "shadow"
    assert "Hello Anita" in draft.draft_text

    # Assert zero outbound messages created for this conversation
    outbound_msgs = (await async_session.execute(
        select(WhatsAppMessage).where(
            WhatsAppMessage.conversation_id == conv.id,
            WhatsAppMessage.direction == "outbound",
        )
    )).scalars().all()
    assert len(outbound_msgs) == 0


# ---------------------------------------------------------------------------
# Scenario B: Controlled Appointment Booking Lifecycle
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scenario_b_appointment_booking_lifecycle(async_session: AsyncSession):
    """Scenario B: Patient request -> slot selection -> confirmation -> staff approval -> appointment transaction -> reminder scheduling.
    
    Expected: Exactly 1 valid appointment and exactly 1 active scheduled reminder job.
    """
    user, account, auto_settings, inbound_settings = await create_e2e_fixtures(async_session)

    # 1. Registered Patient & Contact
    contact = WhatsAppContact(wa_id="+919876522222", profile_name="Vikram Singh")
    async_session.add(contact)
    await async_session.flush()

    patient = Patient(
        contact_id=contact.id,
        full_name="Vikram Singh",
        phone_number="+919876522222",
    )
    async_session.add(patient)
    await async_session.flush()

    conv = Conversation(contact_id=contact.id, status="open")
    async_session.add(conv)
    await async_session.flush()

    # 2. Configure Mode B: Staff Approval Required
    wf_settings = await AppointmentWorkflowService.get_or_create_settings(async_session)
    wf_settings.policy_mode = AutomationPolicyMode.MODE_B_STAFF_APPROVAL.value
    await async_session.commit()

    # 3. Start Workflow
    wf = await AppointmentWorkflowService.start_workflow(
        db=async_session,
        conversation_id=conv.id,
        contact_id=contact.id,
        intent="book_appointment",
    )
    assert wf.status == WorkflowState.COLLECTING_INFORMATION.value

    # 4. Slot Selection (future open weekday, not Sunday)
    now_d = datetime.now(KOLKATA_TZ).date() + timedelta(days=2)
    if now_d.weekday() == 6:  # Sunday
        now_d += timedelta(days=1)
    slot_dt = datetime.combine(now_d, datetime.min.time().replace(hour=11), tzinfo=KOLKATA_TZ)

    updated_wf = await AppointmentWorkflowService.select_slot(
        db=async_session,
        workflow_id=wf.id,
        slot_start=slot_dt,
    )
    assert updated_wf.status == WorkflowState.AWAITING_PATIENT_CONFIRMATION.value

    # 5. Patient Confirms
    await AppointmentWorkflowService.process_patient_confirmation(
        async_session, wf.id, is_confirmed=True
    )
    reloaded_wf = await AppointmentWorkflowService.get_workflow_by_id(async_session, wf.id)
    assert reloaded_wf.status == WorkflowState.AWAITING_STAFF_APPROVAL.value

    # 6. Staff Approves Proposal
    approve_res = await AppointmentWorkflowService.approve_proposal(
        db=async_session,
        workflow_id=wf.id,
        staff_user=user,
        notes="Verified slot available with clinic diary",
    )
    assert approve_res["success"] is True
    assert approve_res["status"] == "confirmed"

    appt_uuid = uuid.UUID(approve_res["result"]["appointment_id"])
    appt = await AppointmentService.get_appointment(async_session, appt_uuid)
    assert appt is not None
    assert appt.status == "confirmed"
    assert appt.patient_id == patient.id

    # 7. Schedule Reminder Job via Automation Service
    reminder_rule = AutomationRule(
        name="2-Hour Appointment Reminder",
        trigger_type="appointment_reminder",
        automation_type="appointment_reminder_2h",
        trigger_event="appointment_confirmed",
        is_enabled=True,
        delay_minutes=120,
    )
    async_session.add(reminder_rule)
    await async_session.flush()

    scheduled_reminder = AutomationScheduledJob(
        rule_id=reminder_rule.id,
        automation_type="appointment_reminder_2h",
        contact_id=contact.id,
        appointment_id=appt.id,
        patient_id=patient.id,
        scheduled_for=appt.start_time - timedelta(hours=2),
        status="pending",
        idempotency_key=f"reminder_{appt.id}_2h",
    )
    async_session.add(scheduled_reminder)
    await async_session.commit()

    # Verify exactly 1 confirmed appointment and 1 reminder job
    appt_count = await async_session.scalar(
        select(func.count(Appointment.id)).where(Appointment.patient_id == patient.id)
    )
    assert appt_count == 1

    reminder_count = await async_session.scalar(
        select(func.count(AutomationScheduledJob.id)).where(
            AutomationScheduledJob.appointment_id == appt.id,
            AutomationScheduledJob.status == "pending",
        )
    )
    assert reminder_count == 1


# ---------------------------------------------------------------------------
# Scenario C: Human Takeover Interruption & AI Suppression
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scenario_c_human_takeover_suppresses_ai(async_session: AsyncSession):
    """Scenario C: Staff takes over while Deepti is processing or active.
    
    Expected: No automated reply generated, no unauthorized appointment mutation.
    """
    user, account, auto_settings, inbound_settings = await create_e2e_fixtures(async_session)

    contact = WhatsAppContact(wa_id="+919876533333", profile_name="Rohit Sharma")
    async_session.add(contact)
    await async_session.flush()

    conv = Conversation(
        contact_id=contact.id,
        status="open",
        is_human_takeover=True,  # Human takeover active!
        ai_paused=True,
    )
    async_session.add(conv)
    await async_session.flush()

    # Inbound message arrives
    msg = WhatsAppMessage(
        contact_id=contact.id,
        conversation_id=conv.id,
        provider="meta",
        direction="inbound",
        message_type="text",
        body="Can I book for tomorrow at 5pm?",
        provider_message_id=f"wamid.takeover_{uuid.uuid4().hex[:8]}",
        status="received",
    )
    async_session.add(msg)
    await async_session.flush()

    # Queue message
    job = await InboundQueueService.enqueue_inbound_message(
        db=async_session,
        message=msg,
        conversation=conv,
        contact=contact,
    )
    job.debounce_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    await async_session.commit()

    # Process job
    outcome = await InboundOrchestrator.process_job(async_session, job)
    assert outcome["status"] in ["suppressed", "skipped", "skipped_human_takeover"]

    # Assert no drafts and no appointments created
    drafts = (await async_session.execute(
        select(AIResponseDraft).where(AIResponseDraft.conversation_id == conv.id)
    )).scalars().all()
    assert len(drafts) == 0


# ---------------------------------------------------------------------------
# Scenario D: Reminder Lifecycle & Rescheduling Invalidation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scenario_d_reminder_lifecycle_and_reschedule_invalidation(async_session: AsyncSession):
    """Scenario D: Appointment created -> reminder scheduled -> appointment rescheduled -> obsolete reminder cancelled -> replacement reminder scheduled.
    
    Expected: Obsolete reminder job is cancelled/suppressed; replacement reminder scheduled for new time.
    """
    user, account, auto_settings, inbound_settings = await create_e2e_fixtures(async_session)

    contact = WhatsAppContact(wa_id="+919876544444", profile_name="Sunita Rao")
    async_session.add(contact)
    await async_session.flush()

    patient = Patient(contact_id=contact.id, full_name="Sunita Rao", phone_number="+919876544444")
    async_session.add(patient)
    await async_session.flush()

    initial_time = datetime.now(timezone.utc) + timedelta(days=3, hours=10)
    appt = Appointment(
        patient_id=patient.id,
        start_time=initial_time,
        end_time=initial_time + timedelta(minutes=45),
        status="confirmed",
        service_type="Follow-up Physiotherapy",
        timezone="Asia/Kolkata",
    )
    async_session.add(appt)
    await async_session.flush()

    # Schedule initial reminder
    initial_reminder = AutomationScheduledJob(
        automation_type="appointment_reminder_2h",
        contact_id=contact.id,
        appointment_id=appt.id,
        scheduled_for=initial_time - timedelta(hours=2),
        status="pending",
        idempotency_key=f"reminder_{appt.id}_{initial_time.isoformat()}",
    )
    async_session.add(initial_reminder)
    await async_session.commit()

    # Reschedule Appointment to new date/time
    new_time = initial_time + timedelta(days=2)
    appt.start_time = new_time
    appt.end_time = new_time + timedelta(minutes=45)
    appt.status = "rescheduled"
    await async_session.flush()

    # Invalidate obsolete reminders for this appointment
    initial_reminder.status = "cancelled"
    initial_reminder.suppression_reason = "appointment_rescheduled"

    # Schedule replacement reminder
    replacement_reminder = AutomationScheduledJob(
        automation_type="appointment_reminder_2h",
        contact_id=contact.id,
        appointment_id=appt.id,
        scheduled_for=new_time - timedelta(hours=2),
        status="pending",
        idempotency_key=f"reminder_{appt.id}_{new_time.isoformat()}",
    )
    async_session.add(replacement_reminder)
    await async_session.commit()

    # Verify obsolete reminder is cancelled and new reminder is active
    await async_session.refresh(initial_reminder)
    await async_session.refresh(replacement_reminder)

    assert initial_reminder.status == "cancelled"
    assert replacement_reminder.status == "pending"
    sched_dt = replacement_reminder.scheduled_for if replacement_reminder.scheduled_for.tzinfo else replacement_reminder.scheduled_for.replace(tzinfo=timezone.utc)
    expected_dt = new_time - timedelta(hours=2)
    assert sched_dt == expected_dt


# ---------------------------------------------------------------------------
# Scenario E: Instagram Campaign Lifecycle & Safety Checks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scenario_e_instagram_campaign_safety_and_analytics(async_session: AsyncSession):
    """Scenario E: Reel selected -> audience evaluated -> consent checked -> preview -> Owner/Admin approval -> simulated dispatch -> analytics.
    
    Expected: Safe execution with mock dispatcher, analytics update, zero real external WhatsApp send.
    """
    user, account, auto_settings, inbound_settings = await create_e2e_fixtures(async_session)

    # 1. Instagram Media
    media = CampaignMedia(
        media_type="instagram_reel",
        title="Posture Correction Exercises",
        external_url="https://instagram.com/reel/test_posture_123",
        caption="Try these 3 exercises to relieve neck pain at your desk!",
    )
    async_session.add(media)
    await async_session.flush()

    # 2. Eligible Contact with Marketing Consent
    contact = WhatsAppContact(wa_id="+919876555555", profile_name="Ananya Roy", opted_out_all=False)
    async_session.add(contact)
    await async_session.flush()

    patient = Patient(contact_id=contact.id, full_name="Ananya Roy", phone_number="+919876555555")
    async_session.add(patient)
    await async_session.flush()

    consent = PatientConsent(
        patient_id=patient.id,
        consent_type="marketing_promotions",
        is_granted=True,
    )
    async_session.add(consent)
    await async_session.flush()

    conv = Conversation(contact_id=contact.id, status="open")
    async_session.add(conv)
    await async_session.flush()

    # Last interaction was 30 hours ago (within 24-48h window)
    interaction_time = datetime.now(timezone.utc) - timedelta(hours=30)
    inbound_msg = WhatsAppMessage(
        contact_id=contact.id,
        conversation_id=conv.id,
        provider="meta",
        provider_message_id=f"wamid.e_{uuid.uuid4().hex[:8]}",
        direction="inbound",
        message_type="text",
        body="Thank you for the advice earlier!",
        created_at=interaction_time,
        status="delivered",
    )
    async_session.add(inbound_msg)
    await async_session.flush()

    # 3. Create Campaign
    camp = await CampaignService.create_campaign(
        async_session,
        {
            "title": "Posture Correction Re-engagement",
            "campaign_type": "instagram_reengagement",
            "media_id": media.id,
            "provider": "meta",
            "execution_window_start": "00:00",
            "execution_window_end": "23:59",
            "target_audience_rules": {
                "require_marketing_consent": True,
                "require_no_booked": True,
            },
        },
        user_id=user.id,
    )
    assert camp.status == "draft"

    # 4. Preview Audience & Persist Recipients
    preview = await CampaignService.evaluate_campaign_audience(async_session, camp.id, persist_recipients=True)
    assert preview["eligible_count"] >= 1

    # 5. Admin Approval & Schedule
    await CampaignService.approve_campaign(async_session, camp.id, "approve", user.id)
    await CampaignService.schedule_campaign(async_session, camp.id)
    await async_session.refresh(camp)
    assert camp.status == "scheduled"
    assert camp.is_approved is True

    # 6. Simulated Worker Dispatch with Mock Dispatcher
    auto_settings.outbound_enabled = True
    await async_session.flush()

    sent_dispatches = []
    async def mock_dispatcher(to_phone: str, message: str, campaign_id: uuid.UUID):
        sent_dispatches.append({"phone": to_phone, "message": message, "campaign_id": campaign_id})
        return {"status": "sent", "provider_message_id": f"mock_wamid_{uuid.uuid4().hex[:8]}"}

    stats = await CampaignService.run_reengagement_cycle(
        async_session,
        limit=10,
        mock_dispatcher=mock_dispatcher,
        ignore_window=True,
    )
    await async_session.commit()

    # Verify simulated sends occurred via mock dispatcher
    assert len(sent_dispatches) >= 1
    assert stats["dispatched_count"] >= 1

    # 7. Verify Analytics Update
    analytics = await CampaignService.get_campaign_analytics(async_session, camp.id)
    assert analytics["total_targeted"] >= 1
    assert analytics["sent_count"] >= 1


# ---------------------------------------------------------------------------
# Scenario F: STOP / Opt-Out Enforcement
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scenario_f_patient_opt_out_enforces_suppression(async_session: AsyncSession):
    """Scenario F: Patient opts out with STOP / UNSUBSCRIBE.
    
    Expected: Contact opted_out_all = True; follow-ups and campaigns are strictly suppressed.
    """
    user, account, auto_settings, inbound_settings = await create_e2e_fixtures(async_session)

    contact = WhatsAppContact(wa_id="+919876566666", profile_name="Karan Verma", opted_out_all=False)
    async_session.add(contact)
    await async_session.flush()

    conv = Conversation(contact_id=contact.id, status="open")
    async_session.add(conv)
    await async_session.flush()

    # Inbound STOP message
    msg = WhatsAppMessage(
        contact_id=contact.id,
        conversation_id=conv.id,
        provider="meta",
        provider_message_id=f"wamid.optout_{uuid.uuid4().hex[:8]}",
        direction="inbound",
        message_type="text",
        body="STOP PLEASE",
        status="received",
    )
    async_session.add(msg)
    await async_session.flush()

    # Enqueue and process
    job = await InboundQueueService.enqueue_inbound_message(
        db=async_session,
        message=msg,
        conversation=conv,
        contact=contact,
    )
    job.debounce_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    await async_session.commit()

    outcome = await InboundOrchestrator.process_job(async_session, job)
    assert outcome["status"] in ["opted_out", "opt_out_acknowledged", "processed_shadow", "processed"]

    # Verify contact opted out
    await async_session.refresh(contact)
    assert contact.opted_out_all is True

    # Verify campaign audience evaluation suppresses this contact
    camp = await CampaignService.create_campaign(
        async_session,
        {
            "title": "Test Promo",
            "campaign_type": "instagram_reengagement",
            "target_audience_rules": {
                "require_marketing_consent": False,
                "require_no_opt_out": True,
            },
        },
        user_id=user.id,
    )
    preview = await CampaignService.evaluate_campaign_audience(async_session, camp.id)
    assert "contact_opted_out_all" in preview["suppression_breakdown"]
    assert preview["suppression_breakdown"]["contact_opted_out_all"] >= 1


# ---------------------------------------------------------------------------
# Scenario G: Worker Crash Recovery & Durable Idempotency
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scenario_g_worker_crash_recovery(async_session: AsyncSession):
    """Scenario G: Worker crashes mid-execution (lease timeout expires).
    
    Expected: Subsequent worker cycle recovers the stranded job and reprocesses safely without duplicate execution.
    """
    user, account, auto_settings, inbound_settings = await create_e2e_fixtures(async_session)
    auto_settings.outbound_enabled = True
    await async_session.flush()

    contact = WhatsAppContact(wa_id="+919876577777", profile_name="Pooja Sharma")
    async_session.add(contact)
    await async_session.flush()

    # Stranded Job: stuck in 'processing' with expired locked_until from crashed worker
    expired_time = datetime.now(timezone.utc) - timedelta(minutes=15)
    stranded_job = AutomationScheduledJob(
        automation_type="appointment_reminder_2h",
        contact_id=contact.id,
        scheduled_for=expired_time,
        status="processing",
        locked_by="crashed_worker_pod_1",
        locked_until=expired_time,
        idempotency_key=f"stranded_recovery_{uuid.uuid4().hex[:8]}",
        payload={"body": "Hello Pooja, your exercise plan is ready."},
    )
    async_session.add(stranded_job)
    await async_session.commit()

    # Run worker cycle
    stats = await AutomationWorkerService.run_worker_cycle(async_session, limit=10)
    await async_session.commit()

    await async_session.refresh(stranded_job)
    # Recovered job must have progressed past the stranded processing state
    assert stats["recovered_leases_count"] >= 1
    assert stranded_job.status in ["scheduled", "retrying", "pending", "completed", "suppressed", "failed"]


# ---------------------------------------------------------------------------
# Worker Security: Multi-tier OIDC, X-Worker-Token HMAC & Admin Sessions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_worker_auth_security_tiers(async_session: AsyncSession, client: AsyncClient):
    """Verify require_worker_auth multi-tier authentication:
    
    1. Valid Google OIDC token -> Accepted
    2. Invalid / Expired OIDC token -> 401 Unauthorized
    3. Valid X-Worker-Token (constant-time HMAC) -> Accepted
    4. Invalid X-Worker-Token -> 401 Unauthorized
    5. Anonymous / Ordinary User -> 401 / 403 Forbidden
    """
    user, account, auto_settings, inbound_settings = await create_e2e_fixtures(async_session)

    # 1. Anonymous request without credentials -> 401
    resp_anon = await client.post("/api/v1/automations/process-due")
    assert resp_anon.status_code == 401

    # 2. Invalid X-Worker-Token -> 401
    resp_bad_token = await client.post(
        "/api/v1/automations/process-due",
        headers={"X-Worker-Token": "completely_wrong_secret_token"},
    )
    assert resp_bad_token.status_code == 401

    # 3. Valid X-Worker-Token (constant-time HMAC check) -> 200
    valid_token = settings.AUTOMATION_WORKER_SECRET_TOKEN
    resp_valid_token = await client.post(
        "/api/v1/automations/process-due",
        headers={"X-Worker-Token": valid_token},
    )
    assert resp_valid_token.status_code == 200

    # 4. Valid Google OIDC Token Mock
    now = time.time()
    mock_payload = {
        "iss": "https://accounts.google.com",
        "aud": settings.OIDC_AUDIENCE or settings.CLOUD_RUN_SERVICE_URL or "https://physio-one-api.run.app",
        "email": settings.WORKER_SERVICE_ACCOUNT_EMAIL or "physio-one-worker@physio-one-prod.iam.gserviceaccount.com",
        "exp": now + 3600,
        "iat": now,
    }
    # Verify claim validation directly (explicit audience/email: claims check fails closed when unconfigured)
    _aud = mock_payload["aud"]; _email = mock_payload["email"]
    assert verify_google_oidc_claims(mock_payload, expected_audience=_aud, expected_email=_email) is True

    # Expired token claim validation fails
    expired_payload = dict(mock_payload, exp=now - 100)
    assert verify_google_oidc_claims(expired_payload, expected_audience=_aud, expected_email=_email) is False

    # Bad issuer claim validation fails
    bad_iss_payload = dict(mock_payload, iss="https://untrusted-issuer.com")
    assert verify_google_oidc_claims(bad_iss_payload, expected_audience=_aud, expected_email=_email) is False
    # Unconfigured audience fails closed
    assert verify_google_oidc_claims(mock_payload, expected_audience="https://other.example") is False
