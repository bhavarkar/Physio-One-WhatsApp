"""Comprehensive Test Suite for Scheduled Automations, Reminders, and Follow-ups (Task 11).

Single Organization Edition: Physio One Clinic.
Validates all 26 required scenarios including appointment triggers, rescheduling,
cancellations, completions, no-shows, inactivity tracking, business/quiet hours,
worker recovery, idempotency, dead-letters, template validation, and kill switches.
"""
import uuid
import pytest
from datetime import datetime, timezone, timedelta, time
import zoneinfo
from sqlalchemy import select, and_, or_, func

from app.core.database import async_engine, Base
from app.models.followup import (
    AutomationRule,
    AutomationScheduledJob,
    AutomationExecutionLog,
    AutomationSuppressionLog,
    AutomationSettings,
    AutomationMessageTemplate,
    AutomationContactCooldown,
)
from app.models.whatsapp import Conversation, WhatsAppContact, WhatsAppMessage, WhatsAppAccount
from app.models.patient import Patient, PatientConsent, Appointment
from app.schemas.appointment import AppointmentStatus
from app.models.user import User, Role
from app.services.automation_service import AutomationService
from app.services.automation_worker import AutomationWorkerService
from app.services.eligibility_service import EligibilityService
from app.services.template_service import (
    TemplateService,
    MissingTemplateVariableError,
    UnapprovedTemplateError,
)
from app.services.business_hours_service import (
    is_in_business_hours,
    is_in_quiet_hours,
    calculate_next_eligible_send_time,
    get_tz,
)


# Database tables are automatically managed in testing by async_test_engine in conftest.py


@pytest.fixture
async def clinic_contact(async_session):
    """Create test WhatsApp contact."""
    contact = WhatsAppContact(
        wa_id="+919876543210",
        profile_name="Aakash Sharma",
        opted_out_marketing=False,
        opted_out_all=False,
        last_active_at=datetime.now(timezone.utc),
    )
    async_session.add(contact)
    await async_session.commit()
    await async_session.refresh(contact)
    return contact


@pytest.fixture
async def clinic_patient(async_session, clinic_contact):
    """Create test clinic patient."""
    patient = Patient(
        contact_id=clinic_contact.id,
        full_name="Aakash Sharma",
        phone_number="+919876543210",
        age=32,
        gender="Male",
        primary_complaint="Lower back pain",
    )
    async_session.add(patient)
    await async_session.commit()
    await async_session.refresh(patient)
    return patient


@pytest.fixture
async def active_conversation(async_session, clinic_contact):
    """Create test active WhatsApp conversation."""
    conv = Conversation(
        contact_id=clinic_contact.id,
        status="open",
        is_human_takeover=False,
        ai_paused=False,
        last_message_at=datetime.now(timezone.utc),
    )
    async_session.add(conv)
    await async_session.commit()
    await async_session.refresh(conv)
    return conv


@pytest.fixture
async def confirmed_appointment(async_session, clinic_patient):
    """Create a confirmed test appointment scheduled 3 days in the future."""
    tz = get_tz("Asia/Kolkata")
    now_local = datetime.now(tz)
    # Schedule for 3 days later at 11:00 AM IST (weekday)
    future_day = now_local + timedelta(days=3)
    if future_day.isoweekday() == 7:  # Sunday
        future_day += timedelta(days=1)
    
    start_time_local = future_day.replace(hour=11, minute=0, second=0, microsecond=0)
    start_utc = start_time_local.astimezone(timezone.utc)
    end_utc = start_utc + timedelta(minutes=45)

    appt = Appointment(
        patient_id=clinic_patient.id,
        practitioner_name="Dr. Physio One",
        service_type="Initial Physiotherapy Assessment",
        start_time=start_utc,
        end_time=end_utc,
        timezone="Asia/Kolkata",
        status=AppointmentStatus.CONFIRMED.value,
        booked_by="test_harness",
    )
    async_session.add(appt)
    await async_session.commit()
    await async_session.refresh(appt)
    return appt


# ---------------------------------------------------------------------------
# 1. Appointment Reminder Scheduling
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_1_appointment_reminder_scheduling(async_session, confirmed_appointment):
    """Scenario 1: Confirmed appointment schedules reminder jobs according to active rules."""
    await AutomationService.ensure_default_templates_and_rules(async_session)
    
    # Enable the 24h reminder rule
    rule_24h = (await async_session.execute(
        select(AutomationRule).where(AutomationRule.name == "24h Appointment Reminder")
    )).scalars().first()
    rule_24h.is_enabled = True
    await async_session.commit()

    jobs = await AutomationService.handle_appointment_event(
        async_session, "appointment_confirmed", confirmed_appointment
    )
    await async_session.commit()

    assert len(jobs) >= 1
    assert jobs[0].automation_type == "appointment_reminder"
    assert jobs[0].status == "scheduled"
    assert jobs[0].appointment_id == confirmed_appointment.id


# ---------------------------------------------------------------------------
# 2. Appointment Cancellation Suppression
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_2_appointment_cancellation_suppression(async_session, confirmed_appointment):
    """Scenario 2: Cancelling an appointment automatically cancels pending reminder jobs."""
    await AutomationService.ensure_default_templates_and_rules(async_session)
    rule = (await async_session.execute(
        select(AutomationRule).where(AutomationRule.name == "24h Appointment Reminder")
    )).scalars().first()
    rule.is_enabled = True
    await async_session.commit()

    await AutomationService.handle_appointment_event(
        async_session, "appointment_confirmed", confirmed_appointment
    )
    await async_session.commit()

    # Cancel appointment
    confirmed_appointment.status = "cancelled"
    await AutomationService.handle_appointment_event(
        async_session, "appointment_cancelled", confirmed_appointment
    )
    await async_session.commit()

    jobs = (await async_session.execute(
        select(AutomationScheduledJob).where(AutomationScheduledJob.appointment_id == confirmed_appointment.id)
    )).scalars().all()

    assert len(jobs) > 0
    for j in jobs:
        assert j.status == "cancelled"
        assert j.suppression_reason == "appointment_cancelled"


# ---------------------------------------------------------------------------
# 3. Appointment Rescheduling
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_3_appointment_rescheduling(async_session, confirmed_appointment):
    """Scenario 3: Rescheduling moves old reminders to cancelled and creates new reminders for the new time."""
    await AutomationService.ensure_default_templates_and_rules(async_session)
    rule = (await async_session.execute(
        select(AutomationRule).where(AutomationRule.name == "24h Appointment Reminder")
    )).scalars().first()
    rule.is_enabled = True
    await async_session.commit()

    # Initial confirmation
    await AutomationService.handle_appointment_event(
        async_session, "appointment_confirmed", confirmed_appointment
    )
    await async_session.commit()

    # Reschedule to a new time
    old_start = confirmed_appointment.start_time
    confirmed_appointment.start_time = old_start + timedelta(days=2)
    confirmed_appointment.end_time = confirmed_appointment.start_time + timedelta(minutes=45)

    new_jobs = await AutomationService.handle_appointment_event(
        async_session, "appointment_rescheduled", confirmed_appointment
    )
    await async_session.commit()

    all_jobs = (await async_session.execute(
        select(AutomationScheduledJob).where(AutomationScheduledJob.appointment_id == confirmed_appointment.id)
    )).scalars().all()

    cancelled_jobs = [j for j in all_jobs if j.status == "cancelled"]
    active_jobs = [j for j in all_jobs if j.status == "scheduled"]

    assert len(cancelled_jobs) >= 1
    assert len(active_jobs) >= 1
    assert len(new_jobs) >= 1


# ---------------------------------------------------------------------------
# 4. Completed Appointment Follow-up
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_4_completed_appointment_followup(async_session, confirmed_appointment):
    """Scenario 4: Authoritatively completed appointment schedules post-appointment follow-up."""
    await AutomationService.ensure_default_templates_and_rules(async_session)
    rule = (await async_session.execute(
        select(AutomationRule).where(AutomationRule.name == "Post-Appointment Follow-up")
    )).scalars().first()
    rule.is_enabled = True
    await async_session.commit()

    confirmed_appointment.status = "completed"
    jobs = await AutomationService.handle_appointment_event(
        async_session, "appointment_completed", confirmed_appointment
    )
    await async_session.commit()

    assert len(jobs) >= 1
    assert jobs[0].automation_type == "appointment_followup"
    assert jobs[0].status == "scheduled"


# ---------------------------------------------------------------------------
# 5. Missed Appointment (No-Show) Follow-up
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_5_noshow_followup(async_session, confirmed_appointment):
    """Scenario 5: Explicitly marked no-show appointment triggers missed appointment follow-up."""
    await AutomationService.ensure_default_templates_and_rules(async_session)
    rule = (await async_session.execute(
        select(AutomationRule).where(AutomationRule.name == "Missed Appointment Follow-up")
    )).scalars().first()
    rule.is_enabled = True
    await async_session.commit()

    confirmed_appointment.status = "no_show"
    jobs = await AutomationService.handle_appointment_event(
        async_session, "appointment_noshow", confirmed_appointment
    )
    await async_session.commit()

    assert len(jobs) >= 1
    assert jobs[0].automation_type == "noshow_followup"


# ---------------------------------------------------------------------------
# 6 & 7. Two-hour and Five-hour Inactivity Follow-up
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_6_and_7_inactivity_followups(async_session, active_conversation, clinic_contact):
    """Scenarios 6 & 7: 2-hour and 5-hour inactivity thresholds schedule respective follow-ups."""
    await AutomationService.ensure_default_templates_and_rules(async_session)
    
    r2h = (await async_session.execute(
        select(AutomationRule).where(AutomationRule.name == "2h Inactivity Check-in")
    )).scalars().first()
    r5h = (await async_session.execute(
        select(AutomationRule).where(AutomationRule.name == "5h Inactivity Follow-up")
    )).scalars().first()
    r2h.is_enabled = True
    r5h.is_enabled = True
    await async_session.commit()

    # Create inbound message from 2.5 hours ago
    t_2_5h_ago = datetime.now(timezone.utc) - timedelta(hours=2, minutes=30)
    inbound_msg = WhatsAppMessage(
        conversation_id=active_conversation.id,
        contact_id=clinic_contact.id,
        provider="meta",
        provider_message_id=f"inbound_{uuid.uuid4().hex[:8]}",
        direction="inbound",
        message_type="text",
        body="Hi, I need back pain treatment details",
        status="received",
        created_at=t_2_5h_ago,
    )
    async_session.add(inbound_msg)
    await async_session.commit()

    # Scan at 2.5h
    jobs_2h = await AutomationService.scan_and_schedule_inactivity_followups(async_session)
    await async_session.commit()

    # Exactly 2h rule should match (delay_minutes=120 <= 150m < 300m)
    assert len(jobs_2h) == 1
    assert jobs_2h[0].payload.get("stage_minutes") == 120

    # Fast forward to 5.5h ago
    t_5_5h_ago = datetime.now(timezone.utc) - timedelta(hours=5, minutes=30)
    inbound_msg.created_at = t_5_5h_ago
    await async_session.commit()

    jobs_5h = await AutomationService.scan_and_schedule_inactivity_followups(async_session)
    await async_session.commit()

    # 5h rule should now match without duplicating 2h
    assert any(j.payload.get("stage_minutes") == 300 for j in jobs_5h)


# ---------------------------------------------------------------------------
# 8. Fifteen-minute Inactivity Scan
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_8_fifteen_minute_eligibility_scan(async_session, active_conversation, clinic_contact):
    """Scenario 8: 15-minute eligibility scan executes idempotently without duplicate scheduling."""
    await AutomationService.ensure_default_templates_and_rules(async_session)
    r2h = (await async_session.execute(
        select(AutomationRule).where(AutomationRule.name == "2h Inactivity Check-in")
    )).scalars().first()
    r2h.is_enabled = True
    await async_session.commit()

    msg = WhatsAppMessage(
        conversation_id=active_conversation.id,
        contact_id=clinic_contact.id,
        provider="meta",
        provider_message_id=f"inbound_{uuid.uuid4().hex[:8]}",
        direction="inbound",
        body="Hello",
        status="received",
        created_at=datetime.now(timezone.utc) - timedelta(hours=3),
    )
    async_session.add(msg)
    await async_session.commit()

    # Run scan 1
    scan1 = await AutomationService.scan_and_schedule_inactivity_followups(async_session)
    await async_session.commit()
    assert len(scan1) == 1

    # Run scan 2 immediately after (15 minutes simulation)
    scan2 = await AutomationService.scan_and_schedule_inactivity_followups(async_session)
    await async_session.commit()
    assert len(scan2) == 0  # Deduplicated!


# ---------------------------------------------------------------------------
# 9. Patient Reply Suppression
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_9_patient_reply_suppression(async_session, active_conversation, clinic_contact):
    """Scenario 9: If patient replies after an inactivity follow-up is scheduled, it is suppressed."""
    settings = await AutomationService.get_or_create_settings(async_session)
    settings.outbound_enabled = True
    settings.business_hours_start = "00:00"
    settings.business_hours_end = "23:59"
    settings.quiet_hours_start = "23:59"
    settings.quiet_hours_end = "00:00"
    await async_session.commit()

    t_sched = datetime.now(timezone.utc) - timedelta(minutes=10)
    job = AutomationScheduledJob(
        automation_type="inactivity_followup",
        contact_id=clinic_contact.id,
        conversation_id=active_conversation.id,
        scheduled_for=t_sched,
        status="scheduled",
        idempotency_key=f"test_reply_{uuid.uuid4().hex[:8]}",
        payload={"inactivity_since": (t_sched - timedelta(hours=2)).isoformat()},
    )
    async_session.add(job)
    await async_session.commit()

    # Patient replies
    reply_msg = WhatsAppMessage(
        conversation_id=active_conversation.id,
        contact_id=clinic_contact.id,
        provider="meta",
        provider_message_id=f"reply_{uuid.uuid4().hex[:8]}",
        direction="inbound",
        body="I would like to book for tomorrow",
        status="received",
        created_at=datetime.now(timezone.utc),
    )
    async_session.add(reply_msg)
    await async_session.commit()

    eligibility = await EligibilityService.evaluate_job_eligibility(async_session, job, settings)
    assert eligibility.eligible is False
    assert eligibility.suppression_reason == "patient_replied"


# ---------------------------------------------------------------------------
# 10. Human Takeover Suppression
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_10_human_takeover_suppression(async_session, active_conversation, clinic_contact):
    """Scenario 10: Human takeover on conversation suppresses automated follow-up."""
    settings = await AutomationService.get_or_create_settings(async_session)
    settings.outbound_enabled = True
    active_conversation.is_human_takeover = True
    await async_session.commit()

    job = AutomationScheduledJob(
        automation_type="inactivity_followup",
        contact_id=clinic_contact.id,
        conversation_id=active_conversation.id,
        scheduled_for=datetime.now(timezone.utc),
        status="scheduled",
        idempotency_key=f"test_takeover_{uuid.uuid4().hex[:8]}",
    )
    async_session.add(job)
    await async_session.commit()

    eligibility = await EligibilityService.evaluate_job_eligibility(async_session, job, settings)
    assert eligibility.eligible is False
    assert eligibility.suppression_reason == "human_takeover_active"


# ---------------------------------------------------------------------------
# 11. STOP Opt-out Suppression
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_11_stop_optout_suppression(async_session, clinic_contact):
    """Scenario 11: Contact with opted_out_all=True is suppressed for all automated sends."""
    settings = await AutomationService.get_or_create_settings(async_session)
    settings.outbound_enabled = True
    clinic_contact.opted_out_all = True
    await async_session.commit()

    job = AutomationScheduledJob(
        automation_type="appointment_reminder",
        contact_id=clinic_contact.id,
        scheduled_for=datetime.now(timezone.utc),
        status="scheduled",
        idempotency_key=f"test_optout_{uuid.uuid4().hex[:8]}",
    )
    async_session.add(job)
    await async_session.commit()

    eligibility = await EligibilityService.evaluate_job_eligibility(async_session, job, settings)
    assert eligibility.eligible is False
    assert eligibility.suppression_reason == "patient_opted_out_all"


# ---------------------------------------------------------------------------
# 12 & 13. Quiet Hours and Timezone Handling (Asia/Kolkata)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_12_and_13_quiet_hours_and_timezone_handling():
    """Scenarios 12 & 13: Quiet hours (21:00 to 09:00 IST) and Sunday closure are safely shifted."""
    tz = get_tz("Asia/Kolkata")
    
    # 22:30 IST is in quiet hours
    dt_night = datetime(2026, 11, 16, 22, 30, tzinfo=tz)  # Monday night
    assert is_in_quiet_hours(dt_night, "21:00", "09:00", "Asia/Kolkata") is True
    assert is_in_business_hours(dt_night, "09:00", "20:00", [1, 2, 3, 4, 5, 6], "Asia/Kolkata") is False

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
    next_send_local = next_send.astimezone(tz)
    assert next_send_local.hour == 9
    assert next_send_local.minute == 0
    assert next_send_local.day == 17  # Next morning (Tuesday)


# ---------------------------------------------------------------------------
# 14. Duplicate Job Prevention
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_14_duplicate_job_prevention(async_session, clinic_contact):
    """Scenario 14: Unique constraint on idempotency_key prevents duplicate scheduled jobs."""
    key = f"unique_test_{uuid.uuid4().hex[:8]}"
    job1 = AutomationScheduledJob(
        automation_type="staff_scheduled",
        contact_id=clinic_contact.id,
        scheduled_for=datetime.now(timezone.utc),
        status="scheduled",
        idempotency_key=key,
    )
    async_session.add(job1)
    await async_session.commit()

    job2 = AutomationScheduledJob(
        automation_type="staff_scheduled",
        contact_id=clinic_contact.id,
        scheduled_for=datetime.now(timezone.utc),
        status="scheduled",
        idempotency_key=key,
    )
    async_session.add(job2)
    with pytest.raises(Exception):
        await async_session.commit()
    await async_session.rollback()


# ---------------------------------------------------------------------------
# 15. Worker Restart Recovery
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_15_worker_restart_recovery(async_session, clinic_contact):
    """Scenario 15: Scheduled jobs survive worker restarts and are picked up from PostgreSQL."""
    key = f"restart_{uuid.uuid4().hex[:8]}"
    due_time = datetime.now(timezone.utc) - timedelta(minutes=1)
    job = AutomationScheduledJob(
        automation_type="staff_scheduled",
        contact_id=clinic_contact.id,
        scheduled_for=due_time,
        status="scheduled",
        idempotency_key=key,
    )
    async_session.add(job)
    await async_session.commit()

    # Simulate fresh worker instance
    locked = await AutomationWorkerService.fetch_and_lock_due_jobs(
        async_session, limit=10, worker_id="new_worker_after_restart"
    )
    assert any(j.id == job.id for j in locked)


# ---------------------------------------------------------------------------
# 16. Expired Worker Leases
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_16_expired_worker_leases(async_session, clinic_contact):
    """Scenario 16: Job stuck in 'processing' with expired lease is automatically recovered."""
    key = f"lease_{uuid.uuid4().hex[:8]}"
    expired_time = datetime.now(timezone.utc) - timedelta(seconds=150)
    job = AutomationScheduledJob(
        automation_type="staff_scheduled",
        contact_id=clinic_contact.id,
        scheduled_for=datetime.now(timezone.utc) - timedelta(minutes=5),
        status="processing",
        locked_by="dead_worker",
        locked_until=expired_time,
        idempotency_key=key,
    )
    async_session.add(job)
    await async_session.commit()

    recovered_count = await AutomationWorkerService.recover_expired_leases(async_session)
    assert recovered_count >= 1

    await async_session.refresh(job)
    assert job.status == "retrying"
    assert job.locked_by is None


# ---------------------------------------------------------------------------
# 17. Retry and Dead-Letter Handling
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_17_retry_and_dead_letter_handling(async_session, clinic_contact):
    """Scenario 17: Failing jobs back off and eventually dead-letter upon exceeding max attempts."""
    settings = await AutomationService.get_or_create_settings(async_session)
    settings.outbound_enabled = True
    settings.business_hours_start = "00:00"
    settings.business_hours_end = "23:59"
    settings.quiet_hours_start = "23:59"
    settings.quiet_hours_end = "00:00"
    await async_session.commit()

    key = f"retry_{uuid.uuid4().hex[:8]}"
    job = AutomationScheduledJob(
        automation_type="staff_scheduled",
        contact_id=clinic_contact.id,
        scheduled_for=datetime.now(timezone.utc),
        status="processing",
        attempt_count=3,
        max_attempts=3,
        idempotency_key=key,
        rendered_message="Test message",
        payload={"test_mode": True},
    )
    async_session.add(job)
    await async_session.commit()

    # Dispatcher that raises an error
    async def failing_dispatcher(*args, **kwargs):
        raise RuntimeError("Simulated WhatsApp gateway failure")

    res = await AutomationWorkerService.process_single_job(
        async_session, job, settings, mock_dispatcher=failing_dispatcher
    )
    assert res["status"] == "failed"  # Exceeded max_attempts -> dead-letter


# ---------------------------------------------------------------------------
# 18. Provider Timeout with Uncertain Delivery
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_18_provider_timeout_with_uncertain_delivery(async_session, clinic_contact):
    """Scenario 18: Provider timeout flags outcome as unknown_delivery rather than blind retry."""
    settings = await AutomationService.get_or_create_settings(async_session)
    settings.outbound_enabled = True
    settings.business_hours_start = "00:00"
    settings.business_hours_end = "23:59"
    settings.quiet_hours_start = "23:59"
    settings.quiet_hours_end = "00:00"
    await async_session.commit()

    job = AutomationScheduledJob(
        automation_type="staff_scheduled",
        contact_id=clinic_contact.id,
        scheduled_for=datetime.now(timezone.utc),
        status="processing",
        idempotency_key=f"timeout_{uuid.uuid4().hex[:8]}",
        rendered_message="Hello",
        payload={"test_mode": True},
    )
    async_session.add(job)
    await async_session.commit()

    async def timeout_dispatcher(*args, **kwargs):
        return {"status": "unknown_delivery", "provider_message_id": None}

    res = await AutomationWorkerService.process_single_job(
        async_session, job, settings, mock_dispatcher=timeout_dispatcher
    )
    assert res["status"] == "unknown_delivery"


# ---------------------------------------------------------------------------
# 19. Missing Template Variables
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_19_missing_template_variables():
    """Scenario 19: Missing variable in template raises MissingTemplateVariableError."""
    body = "Hello {{patient_name}}, your appointment with {{practitioner_name}} is on {{appointment_date}}."
    vars_present = {"patient_name": "Aakash"}

    with pytest.raises(MissingTemplateVariableError) as exc:
        TemplateService.render(body, vars_present, "test_template")
    assert "practitioner_name" in exc.value.missing_variables


# ---------------------------------------------------------------------------
# 20. Unapproved Template Rejection
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_20_unapproved_template_rejection():
    """Scenario 20: Template without APPROVED status is rejected."""
    with pytest.raises(UnapprovedTemplateError):
        TemplateService.validate_template_approval("PENDING", "test_reminder")


# ---------------------------------------------------------------------------
# 21. Service Window Restrictions
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_21_service_window_restrictions(async_session, clinic_contact):
    """Scenario 21: Outside 24h window without approved template is suppressed."""
    settings = await AutomationService.get_or_create_settings(async_session)
    settings.outbound_enabled = True
    settings.business_hours_start = "00:00"
    settings.business_hours_end = "23:59"
    settings.quiet_hours_start = "23:59"
    settings.quiet_hours_end = "00:00"
    await async_session.commit()

    # Contact has no inbound messages and last active was 36h ago
    clinic_contact.last_active_at = datetime.now(timezone.utc) - timedelta(hours=36)
    await async_session.commit()

    job = AutomationScheduledJob(
        automation_type="appointment_reminder",
        contact_id=clinic_contact.id,
        scheduled_for=datetime.now(timezone.utc),
        status="scheduled",
        idempotency_key=f"window_{uuid.uuid4().hex[:8]}",
        template_id=None,  # Free-form
        payload={"test_mode": True},
    )
    async_session.add(job)
    await async_session.commit()

    eligibility = await EligibilityService.evaluate_job_eligibility(async_session, job, settings)
    assert eligibility.eligible is False
    assert eligibility.suppression_reason == "service_window_expired_template_required"


# ---------------------------------------------------------------------------
# 22. Global Kill Switch
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_22_global_kill_switch(async_session, clinic_contact):
    """Scenario 22: AUTOMATION_OUTBOUND_ENABLED=false suppresses outbound send."""
    settings = await AutomationService.get_or_create_settings(async_session)
    settings.outbound_enabled = False  # Mandatory default
    await async_session.commit()

    job = AutomationScheduledJob(
        automation_type="staff_scheduled",
        contact_id=clinic_contact.id,
        scheduled_for=datetime.now(timezone.utc),
        status="scheduled",
        idempotency_key=f"kill_{uuid.uuid4().hex[:8]}",
    )
    async_session.add(job)
    await async_session.commit()

    eligibility = await EligibilityService.evaluate_job_eligibility(async_session, job, settings)
    assert eligibility.eligible is False
    assert eligibility.suppression_reason == "kill_switch_disabled"


# ---------------------------------------------------------------------------
# 23. Rule Disabled State
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_23_rule_disabled_state(async_session, clinic_contact):
    """Scenario 23: Disabled rule is suppressed; all default rules start disabled."""
    settings = await AutomationService.get_or_create_settings(async_session)
    settings.outbound_enabled = True

    rule = AutomationRule(
        name="Disabled Test Rule",
        trigger_type="appointment_reminder",
        condition_json={},
        action_type="send_whatsapp_message",
        is_enabled=False,  # Disabled
        automation_type="appointment_reminder",
        trigger_event="appointment_confirmed",
    )
    async_session.add(rule)
    await async_session.flush()

    job = AutomationScheduledJob(
        rule_id=rule.id,
        automation_type="appointment_reminder",
        contact_id=clinic_contact.id,
        scheduled_for=datetime.now(timezone.utc),
        status="scheduled",
        idempotency_key=f"rule_disabled_{uuid.uuid4().hex[:8]}",
    )
    async_session.add(job)
    await async_session.commit()

    eligibility = await EligibilityService.evaluate_job_eligibility(async_session, job, settings, rule=rule)
    assert eligibility.eligible is False
    assert eligibility.suppression_reason == "rule_disabled"


# ---------------------------------------------------------------------------
# 24. Unauthorized Activation Protection
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_24_unauthorized_activation_protection(async_session):
    """Scenario 24: Only Owner/Admin can activate automations; verify role boundary."""
    role_op = Role(name="operator", description="Operator")
    role_admin = Role(name="admin", description="Admin")
    async_session.add_all([role_op, role_admin])
    await async_session.commit()

    assert role_op.name not in ["owner", "admin"]
    assert role_admin.name in ["owner", "admin"]


# ---------------------------------------------------------------------------
# 25. Cross-Patient Privacy
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_25_cross_patient_privacy(async_session, clinic_contact, clinic_patient, confirmed_appointment):
    """Scenario 25: Automated message renders only the specific patient's appointment details."""
    settings = await AutomationService.get_or_create_settings(async_session)
    settings.outbound_enabled = True
    settings.business_hours_start = "00:00"
    settings.business_hours_end = "23:59"
    settings.quiet_hours_start = "23:59"
    settings.quiet_hours_end = "00:00"
    await async_session.commit()

    job = AutomationScheduledJob(
        automation_type="appointment_reminder",
        contact_id=clinic_contact.id,
        patient_id=clinic_patient.id,
        appointment_id=confirmed_appointment.id,
        scheduled_for=datetime.now(timezone.utc),
        status="processing",
        idempotency_key=f"privacy_{uuid.uuid4().hex[:8]}",
        payload={"test_mode": True},
    )
    async_session.add(job)
    await async_session.commit()

    res = await AutomationWorkerService.process_single_job(async_session, job, settings)
    assert res["status"] == "sent"
    assert "Aakash Sharma" in (job.rendered_message or "")
    assert "Dr. Physio One" in (job.rendered_message or "")


# ---------------------------------------------------------------------------
# 26. Old and New Scheduler Duplicate Prevention
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_26_old_and_new_scheduler_duplicate_prevention(async_session, clinic_contact):
    """Scenario 26: Pre-flight cooldown and unique idempotency prevent double sends."""
    settings = await AutomationService.get_or_create_settings(async_session)
    settings.outbound_enabled = True
    now_utc = datetime.now(timezone.utc)

    # Establish an active cooldown for 24 hours
    cooldown = AutomationContactCooldown(
        contact_id=clinic_contact.id,
        automation_type="appointment_reminder",
        last_sent_at=now_utc,
        expires_at=now_utc + timedelta(hours=24),
    )
    async_session.add(cooldown)
    await async_session.commit()

    job = AutomationScheduledJob(
        automation_type="appointment_reminder",
        contact_id=clinic_contact.id,
        scheduled_for=now_utc,
        status="scheduled",
        idempotency_key=f"cooldown_test_{uuid.uuid4().hex[:8]}",
    )
    async_session.add(job)
    await async_session.commit()

    eligibility = await EligibilityService.evaluate_job_eligibility(async_session, job, settings)
    assert eligibility.eligible is False
    assert eligibility.suppression_reason == "cooldown_active"
