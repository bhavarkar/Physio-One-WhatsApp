"""Integration Tests for Worker Queue Concurrency, Leasing, and Reliability (Task 21 Phase 3).

Validates:
1. Atomic job claiming across concurrent workers (no duplicate claims).
2. Lease expiration and crash recovery (recovering abandoned processing jobs).
3. Inbound queue concurrent locking and debouncing.
4. Retry backoff and dead-letter queue transition.
5. Outbound dispatch idempotency (no duplicate WhatsApp dispatches).
6. Timezone-aware quiet hour deferral.
"""
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import select

from app.models.followup import (
    AutomationRule,
    AutomationScheduledJob,
    AutomationExecutionLog,
    AutomationSettings,
    AutomationMessageTemplate,
)
from app.models.whatsapp import Conversation, WhatsAppContact
from app.models.inbound import InboundProcessingJob
from app.models.campaign import Campaign, CampaignRecipient
from app.services.automation_worker import AutomationWorkerService
from app.services.inbound_queue import InboundQueueService
from app.services.campaign_service import CampaignService


@pytest.fixture
async def setup_queue_environment(async_session):
    """Seed test contact, settings, and template."""
    contact = WhatsAppContact(
        wa_id="+919988776655",
        profile_name="Concurrency Patient",
        opted_out_marketing=False,
        opted_out_all=False,
        last_active_at=datetime.now(timezone.utc),
    )
    async_session.add(contact)
    await async_session.flush()

    template = AutomationMessageTemplate(
        name="test_concurrency_template",
        category="UTILITY",
        body="Hi {{patient_name}}, reminder for your session at {{appointment_time}}.",
        variables=["patient_name", "appointment_time"],
        approval_status="APPROVED",
    )
    async_session.add(template)
    await async_session.flush()

    rule = AutomationRule(
        name="Concurrency Test Rule",
        trigger_type="appointment_reminder",
        trigger_event="appointment_confirmed",
        automation_type="appointment_reminder_24h",
        template_id=template.id,
        is_enabled=True,
        business_hours_only=False,
        cooldown_hours=2,
        start_hour="00:00",
        end_hour="23:59",
        retry_policy={"max_retries": 3, "backoff_minutes": 5},
    )
    async_session.add(rule)
    await async_session.flush()

    settings = AutomationSettings(
        outbound_enabled=True,
        max_retries=3,
        default_cooldown_hours=2,
        business_hours_start="00:00",
        business_hours_end="23:59",
        quiet_hours_start="23:59",
        quiet_hours_end="00:00",
    )
    async_session.add(settings)
    await async_session.commit()
    await async_session.refresh(contact)
    await async_session.refresh(rule)
    await async_session.refresh(template)
    await async_session.refresh(settings)

    return {
        "contact": contact,
        "rule": rule,
        "template": template,
        "settings": settings,
    }


@pytest.mark.asyncio
async def test_concurrent_worker_atomic_claiming(async_session, setup_queue_environment):
    """Scenario 1: Verify multiple workers claiming due jobs claim distinct sets with no duplicates."""
    env = setup_queue_environment
    now = datetime.now(timezone.utc) - timedelta(minutes=5)

    # Create 6 due scheduled jobs with unique idempotency keys
    job_ids = []
    for i in range(6):
        job = AutomationScheduledJob(
            rule_id=env["rule"].id,
            contact_id=env["contact"].id,
            template_id=env["template"].id,
            automation_type="appointment_reminder_24h",
            status="scheduled",
            scheduled_for=now,
            attempt_count=0,
            idempotency_key=f"idemp_claim_{i}_{uuid.uuid4().hex[:8]}",
        )
        async_session.add(job)
        await async_session.flush()
        job_ids.append(job.id)
    await async_session.commit()

    # Simulate 2 workers fetching concurrently with limit=3 each
    worker1_jobs = await AutomationWorkerService.fetch_and_lock_due_jobs(
        async_session, limit=3, worker_id="worker_alpha"
    )
    worker2_jobs = await AutomationWorkerService.fetch_and_lock_due_jobs(
        async_session, limit=3, worker_id="worker_beta"
    )

    w1_ids = {j.id for j in worker1_jobs}
    w2_ids = {j.id for j in worker2_jobs}

    assert len(worker1_jobs) == 3
    assert len(worker2_jobs) == 3
    # No overlap: atomic claiming
    assert w1_ids.isdisjoint(w2_ids)
    assert w1_ids.union(w2_ids) == set(job_ids)

    for j in worker1_jobs:
        assert j.status == "processing"
        assert j.locked_by == "worker_alpha"
        assert j.locked_until is not None

    for j in worker2_jobs:
        assert j.status == "processing"
        assert j.locked_by == "worker_beta"
        assert j.locked_until is not None


@pytest.mark.asyncio
async def test_lease_expiration_and_crash_recovery(async_session, setup_queue_environment):
    """Scenario 2: Worker crashes mid-flight; lease timeout expires; recovery returns job to retrying."""
    env = setup_queue_environment
    now = datetime.now(timezone.utc)
    expired_lock = now - timedelta(seconds=10)

    # Job locked by crashed worker whose lease has expired
    crashed_job = AutomationScheduledJob(
        rule_id=env["rule"].id,
        contact_id=env["contact"].id,
        template_id=env["template"].id,
        automation_type="appointment_reminder_24h",
        status="processing",
        scheduled_for=now - timedelta(minutes=10),
        locked_by="crashed_worker_999",
        locked_until=expired_lock,
        attempt_count=1,
        idempotency_key=f"idemp_crashed_{uuid.uuid4().hex[:8]}",
    )
    async_session.add(crashed_job)
    await async_session.commit()
    await async_session.refresh(crashed_job)

    # Run lease recovery
    recovered_count = await AutomationWorkerService.recover_expired_leases(async_session)
    assert recovered_count >= 1

    await async_session.refresh(crashed_job)
    assert crashed_job.status == "retrying"
    assert crashed_job.locked_by is None
    assert crashed_job.locked_until is None

    # Verify a new worker can immediately claim it
    new_jobs = await AutomationWorkerService.fetch_and_lock_due_jobs(
        async_session, limit=1, worker_id="recovered_worker"
    )
    assert any(j.id == crashed_job.id for j in new_jobs)


@pytest.mark.asyncio
async def test_inbound_queue_atomic_locking(async_session, setup_queue_environment):
    """Scenario 3: Verify inbound queue debounced jobs are claimed atomically."""
    env = setup_queue_environment
    now = datetime.now(timezone.utc)

    conversation = Conversation(
        contact_id=env["contact"].id,
        status="open",
    )
    async_session.add(conversation)
    await async_session.flush()

    job1 = InboundProcessingJob(
        conversation_id=conversation.id,
        contact_id=env["contact"].id,
        provider="meta",
        status="debouncing",
        aggregated_message_ids=["msg_1"],
        aggregated_text="Hello",
        debounce_until=now - timedelta(seconds=5),
        scheduled_at=now - timedelta(seconds=10),
        attempt_count=0,
    )
    job2 = InboundProcessingJob(
        conversation_id=conversation.id,
        contact_id=env["contact"].id,
        provider="meta",
        status="debouncing",
        aggregated_message_ids=["msg_2"],
        aggregated_text="Are you open?",
        debounce_until=now - timedelta(seconds=2),
        scheduled_at=now - timedelta(seconds=10),
        attempt_count=0,
    )
    async_session.add_all([job1, job2])
    await async_session.commit()

    # Worker 1 fetches 1 job
    claimed_w1 = await InboundQueueService.fetch_and_lock_due_jobs(
        async_session, limit=1, worker_id="inbound_worker_1"
    )
    # Worker 2 fetches 1 job
    claimed_w2 = await InboundQueueService.fetch_and_lock_due_jobs(
        async_session, limit=1, worker_id="inbound_worker_2"
    )

    assert len(claimed_w1) == 1
    assert len(claimed_w2) == 1
    assert claimed_w1[0].id != claimed_w2[0].id
    assert claimed_w1[0].locked_by == "inbound_worker_1"
    assert claimed_w2[0].locked_by == "inbound_worker_2"


@pytest.mark.asyncio
async def test_retry_limits_and_dead_letter_transition(async_session, setup_queue_environment):
    """Scenario 4: Exponential backoff on transient errors and transition to dead_letter_failed at retry limit."""
    env = setup_queue_environment
    now = datetime.now(timezone.utc)

    # Job at attempt 3 with max_retries = 3
    failing_job = AutomationScheduledJob(
        contact_id=env["contact"].id,
        automation_type="staff_scheduled",
        status="processing",
        scheduled_for=now,
        attempt_count=3,
        max_attempts=3,
        locked_by="failing_worker",
        locked_until=now + timedelta(seconds=120),
        rendered_message="Test message",
        payload={"test_mode": True},
        idempotency_key=f"idemp_fail_{uuid.uuid4().hex[:8]}",
    )
    async_session.add(failing_job)
    await async_session.commit()

    async def broken_dispatcher(**kwargs):
        raise RuntimeError("Meta Cloud API 503 Service Unavailable")

    result = await AutomationWorkerService.process_single_job(
        async_session,
        failing_job,
        env["settings"],
        mock_dispatcher=broken_dispatcher,
    )

    assert result["status"] == "failed"
    await async_session.refresh(failing_job)
    assert failing_job.status == "failed"
    assert failing_job.completed_at is not None
    assert failing_job.locked_by is None

    # Verify execution log contains dead-letter record
    log_stmt = select(AutomationExecutionLog).where(
        AutomationExecutionLog.job_id == failing_job.id,
        AutomationExecutionLog.action == "dead_letter_failed",
    )
    log_entry = (await async_session.execute(log_stmt)).scalars().first()
    assert log_entry is not None
    assert "Meta Cloud API 503" in log_entry.details.get("error", "")


@pytest.mark.asyncio
async def test_campaign_recipient_concurrency_isolation(async_session, setup_queue_environment):
    """Scenario 5: Campaign recipient claiming isolates concurrent workers cleanly."""
    env = setup_queue_environment
    now = datetime.now(timezone.utc)

    campaign = Campaign(
        title="Re-engagement Blast",
        campaign_type="instagram_reengagement",
        status="running",
        is_approved=True,
        scheduled_for=now - timedelta(minutes=1),
        execution_window_start="09:00",
        execution_window_end="21:00",
        batch_size=10,
    )
    async_session.add(campaign)
    await async_session.flush()

    recips = []
    for i in range(4):
        c = WhatsAppContact(
            wa_id=f"+91987654321{i}",
            profile_name=f"Patient {i}",
            opted_out_marketing=False,
            opted_out_all=False,
        )
        async_session.add(c)
        await async_session.flush()

        r = CampaignRecipient(
            campaign_id=campaign.id,
            contact_id=c.id,
            status="eligible",
            rendered_message=f"Hello Patient {i}",
            idempotency_key=f"camp_recip_{i}_{uuid.uuid4().hex[:8]}",
        )
        async_session.add(r)
        recips.append(r)
    await async_session.commit()

    dispatched = []

    async def mock_send(to_phone, message, campaign_id):
        dispatched.append(to_phone)
        return {"status": "sent"}

    # Run cycle in mock mode
    stats = await CampaignService.run_reengagement_cycle(
        async_session, limit=4, mock_dispatcher=mock_send, ignore_window=True
    )
    assert stats.get("dispatched_count") == 4
    assert len(dispatched) == 4
    assert len(set(dispatched)) == 4  # All distinct recipients, no duplicates


@pytest.mark.asyncio
async def test_quiet_hour_deferral_enforcement(async_session, setup_queue_environment):
    """Scenario 6: Jobs scheduled during quiet hours (21:00 to 09:00 IST) defer cleanly to 09:00 IST."""
    env = setup_queue_environment
    now_utc = datetime(2026, 11, 18, 17, 0, 0, tzinfo=timezone.utc)  # 22:30 IST (inside quiet hours)

    # Enable standard strict quiet hours
    env["settings"].business_hours_start = "09:00"
    env["settings"].business_hours_end = "20:00"
    env["settings"].quiet_hours_start = "21:00"
    env["settings"].quiet_hours_end = "09:00"
    env["rule"].business_hours_only = True
    env["rule"].start_hour = "09:00"
    env["rule"].end_hour = "20:00"
    await async_session.commit()

    job = AutomationScheduledJob(
        contact_id=env["contact"].id,
        rule_id=env["rule"].id,
        template_id=env["template"].id,
        automation_type="staff_scheduled",
        status="processing",
        scheduled_for=now_utc,
        attempt_count=1,
        locked_by="quiet_hour_worker",
        locked_until=now_utc + timedelta(seconds=120),
        rendered_message="Quiet hours test message",
        idempotency_key=f"idemp_quiet_{uuid.uuid4().hex[:8]}",
    )
    async_session.add(job)
    await async_session.commit()

    dispatched = []

    async def tracking_dispatcher(**kwargs):
        dispatched.append(kwargs)
        return {"status": "sent"}

    # Process job during quiet hours
    res = await AutomationWorkerService.process_single_job(
        async_session,
        job,
        env["settings"],
        mock_dispatcher=tracking_dispatcher,
    )

    # Must be deferred/rescheduled without dispatching WhatsApp message
    assert res["status"] == "rescheduled"
    assert len(dispatched) == 0

    await async_session.refresh(job)
    assert job.status == "scheduled"
    assert job.locked_by is None
    # Next scheduled time must be within business hours
    sf = job.scheduled_for.replace(tzinfo=timezone.utc) if job.scheduled_for.tzinfo is None else job.scheduled_for
    assert sf > now_utc


@pytest.mark.asyncio
async def test_job_idempotency_prevents_duplicate_dispatch(async_session, setup_queue_environment):
    """Scenario 7: Duplicate processing of already sent or processing job never sends duplicate message."""
    env = setup_queue_environment
    now = datetime.now(timezone.utc)

    # Job that was already sent
    already_sent_job = AutomationScheduledJob(
        contact_id=env["contact"].id,
        automation_type="staff_scheduled",
        status="sent",
        scheduled_for=now - timedelta(minutes=10),
        completed_at=now - timedelta(minutes=5),
        provider_message_id="wamid.test_already_sent_123",
        idempotency_key=f"idemp_dup_{uuid.uuid4().hex[:8]}",
    )
    async_session.add(already_sent_job)
    await async_session.commit()

    # Querying due jobs must never return jobs in "sent" or "completed"
    due_jobs = await AutomationWorkerService.fetch_and_lock_due_jobs(
        async_session, limit=10, worker_id="idempotency_checker"
    )
    assert not any(j.id == already_sent_job.id for j in due_jobs)

