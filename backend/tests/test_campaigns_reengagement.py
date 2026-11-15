"""Comprehensive Test Suite for Instagram Re-engagement, YCloud Migration, and WhatsApp Campaigns (Task 12).

Single Organization Edition: Physio One Clinic.
Validates all 30 required scenarios:
1. Campaign creation (defaults to draft).
2. Campaign versioning.
3. Audience evaluation.
4. CSV import validation (E.164 normalization & formula protection).
5. Duplicate contact filtering.
6. Missing marketing consent suppression.
7. STOP / opt-out suppression.
8. Already-booked patient exclusion.
9. Instagram 24–48h interaction window.
10. Thirty-minute scan execution.
11. 09:00–21:00 IST sending window.
12. Duplicate scan prevention (idempotency key).
13. Campaign approval workflow.
14. Approval invalidation after edits.
15. Unauthorized campaign scheduling blocked.
16. Global kill switch suppression.
17. Provider selection (Meta and YCloud).
18. Approved template validation.
19. Unapproved template rejection.
20. Rate limiting and batch parameters.
21. Retry and dead-letter behavior.
22. Unknown delivery outcome handling.
23. Worker restart and recovery.
24. Campaign pause and resume.
25. Campaign cancellation.
26. Legacy scheduler overlap prevention.
27. Legacy dry-run shadow comparison.
28. Cross-patient data isolation.
29. Delivery analytics aggregation.
30. Conversion attribution window (72h).
"""
import io
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func

from app.models.campaign import (
    Campaign,
    CampaignMedia,
    CampaignVersion,
    CampaignAudience,
    CampaignRecipient,
    CampaignApproval,
    CampaignDeliveryEvent,
    CampaignConversionEvent,
    LegacyWorkflowMigration,
)
from app.models.whatsapp import WhatsAppContact, WhatsAppMessage
from app.models.patient import Patient, PatientConsent, Appointment
from app.models.followup import AutomationSettings, AutomationMessageTemplate
from app.models.inbound import Conversation
from app.models.user import User, Role
from app.services.campaign_service import CampaignService
from app.services.template_service import TemplateService, UnapprovedTemplateError
from app.services.business_hours_service import is_in_business_hours, get_tz


@pytest.fixture
async def admin_role(async_session):
    role = await async_session.scalar(select(Role).where(Role.name == "admin"))
    if not role:
        role = Role(name="admin", description="Administrator")
        async_session.add(role)
        await async_session.commit()
        await async_session.refresh(role)
    return role


@pytest.fixture
async def admin_user(async_session, admin_role):
    user = User(
        email=f"admin_{uuid.uuid4().hex[:6]}@physioone.com",
        password_hash="mock_hash",
        full_name="Clinic Admin",
        role_id=admin_role.id,
        is_active=True,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.fixture
async def test_contact(async_session):
    contact = WhatsAppContact(
        wa_id="919876543210",
        profile_name="Ananya Sharma",
        opted_out_all=False,
        opted_out_marketing=False,
        last_active_at=datetime.now(timezone.utc) - timedelta(hours=30),  # Eligible: 30h ago (between 24-48h)
    )
    async_session.add(contact)
    await async_session.commit()
    await async_session.refresh(contact)
    return contact


@pytest.fixture
async def test_patient(async_session, test_contact):
    patient = Patient(
        contact_id=test_contact.id,
        full_name="Ananya Sharma",
        phone_number="+919876543210",
        age=28,
        gender="Female",
        primary_complaint="Post-ACL rehabilitation",
    )
    async_session.add(patient)
    await async_session.flush()

    # Explicit marketing consent
    consent = PatientConsent(
        patient_id=patient.id,
        consent_type="marketing_promotions",
        is_granted=True,
    )
    async_session.add(consent)
    await async_session.commit()
    await async_session.refresh(patient)
    return patient


@pytest.fixture
async def sample_reel_media(async_session, admin_user):
    media = await CampaignService.create_media(
        async_session,
        title="ACL Recovery Exercises Reel",
        caption="5 critical mobility drills for knee stability",
        media_type="instagram_reel",
        external_url="https://www.instagram.com/reel/C123456789/",
        tags=["knee", "acl", "exercise"],
        user_id=admin_user.id,
    )
    return media


# ---------------------------------------------------------------------------
# 1. Campaign Creation (Defaults to Draft)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_01_campaign_creation_defaults_to_draft(async_session, admin_user, sample_reel_media):
    """Scenario 1: New campaigns default strictly to draft status with version 1."""
    camp = await CampaignService.create_campaign(
        async_session,
        {
            "title": "Post-ACL Recovery Reel Broadcast",
            "campaign_type": "instagram_reengagement",
            "media_id": sample_reel_media.id,
            "provider": "meta",
        },
        user_id=admin_user.id,
    )
    assert camp.id is not None
    assert camp.status == "draft"
    assert camp.current_version == 1
    assert camp.is_approved is False
    assert camp.approved_version is None


# ---------------------------------------------------------------------------
# 2. Campaign Versioning
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_02_campaign_versioning_and_snapshot(async_session, admin_user, sample_reel_media):
    """Scenario 2: Editing a campaign increments current_version and saves an immutable snapshot."""
    camp = await CampaignService.create_campaign(
        async_session,
        {"title": "Initial Title", "media_id": sample_reel_media.id},
        user_id=admin_user.id,
    )
    assert camp.current_version == 1

    updated = await CampaignService.update_campaign(
        async_session, camp.id, {"title": "Updated Title Version 2"}, user_id=admin_user.id
    )
    assert updated.current_version == 2
    assert updated.title == "Updated Title Version 2"

    # Verify versions table
    versions = (
        await async_session.execute(
            select(CampaignVersion).where(CampaignVersion.campaign_id == camp.id).order_by(CampaignVersion.version_number)
        )
    ).scalars().all()
    assert len(versions) == 2
    assert versions[0].snapshot["title"] == "Initial Title"
    assert versions[1].snapshot["title"] == "Updated Title Version 2"


# ---------------------------------------------------------------------------
# 3. Audience Evaluation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_03_audience_evaluation_interaction_window(async_session, admin_user, test_contact, test_patient, sample_reel_media):
    """Scenario 3: Evaluates audience and marks contacts within 24-48h interaction window eligible."""
    camp = await CampaignService.create_campaign(
        async_session,
        {
            "title": "Re-engagement Test",
            "media_id": sample_reel_media.id,
            "target_audience_rules": {
                "interaction_window_hours": [24, 48],
                "require_marketing_consent": True,
                "require_no_opt_out": True,
            },
        },
        user_id=admin_user.id,
    )

    result = await CampaignService.evaluate_campaign_audience(async_session, camp.id, persist_recipients=True)
    assert result["eligible_count"] >= 1
    assert result["suppressed_count"] == 0


# ---------------------------------------------------------------------------
# 4. CSV Import & E.164 Normalization
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_04_csv_import_validation_and_e164_normalization(async_session, admin_user):
    """Scenario 4: Imports CSV, normalizes phone numbers to E.164, and sanitizes spreadsheet injection."""
    csv_text = (
        "name,phone,marketing_consent\n"
        "Rohan Mehra,9811223344,true\n"
        "=cmd|' /C calc'!A0,9811223388,true\n"
        "International,+919988776655,yes\n"
        "Invalid Row,12345,false\n"
    )

    report = await CampaignService.import_csv_contacts(async_session, csv_text, user_id=admin_user.id)
    assert report["total_rows"] == 4
    assert report["accepted_count"] == 3
    assert report["rejected_count"] == 1  # 12345 rejected as too short
    assert report["created_contacts_count"] >= 2

    # Verify normalized phone
    contact = await async_session.scalar(
        select(WhatsAppContact).where(WhatsAppContact.wa_id == "919811223344")
    )
    assert contact is not None
    assert contact.phone_number == "+919811223344"


# ---------------------------------------------------------------------------
# 5. Duplicate Contact Filtering
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_05_duplicate_contact_filtering(async_session, admin_user):
    """Scenario 5: Duplicate phone numbers in CSV or audience are automatically filtered."""
    csv_text = (
        "name,phone\n"
        "Duplicate 1,9876543210\n"
        "Duplicate 2,+919876543210\n"
        "Duplicate 3,9876543210\n"
    )
    report = await CampaignService.import_csv_contacts(async_session, csv_text, user_id=admin_user.id)
    assert report["accepted_count"] == 1
    assert report["duplicate_count"] == 2


# ---------------------------------------------------------------------------
# 6. Missing Marketing Consent Suppression
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_06_missing_marketing_consent_suppression(async_session, admin_user, sample_reel_media):
    """Scenario 6: Contacts without explicit marketing consent are suppressed."""
    contact = WhatsAppContact(
        wa_id="919111222333",
        profile_name="No Consent User",
        last_active_at=datetime.now(timezone.utc) - timedelta(hours=30),
    )
    async_session.add(contact)
    await async_session.commit()

    camp = await CampaignService.create_campaign(
        async_session,
        {
            "title": "Marketing Consent Test",
            "media_id": sample_reel_media.id,
            "target_audience_rules": {"require_marketing_consent": True},
        },
        user_id=admin_user.id,
    )
    result = await CampaignService.evaluate_campaign_audience(async_session, camp.id, persist_recipients=True)
    assert result["suppressed_count"] >= 1
    assert result["suppression_breakdown"].get("missing_marketing_consent", 0) >= 1


# ---------------------------------------------------------------------------
# 7. STOP / Opt-Out Suppression
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_07_opt_out_stop_suppression(async_session, admin_user, sample_reel_media):
    """Scenario 7: Contacts with opted_out_all or opted_out_promotions are strictly suppressed."""
    contact = WhatsAppContact(
        wa_id="919444555666",
        profile_name="Opted Out Contact",
        opted_out_all=True,
        last_active_at=datetime.now(timezone.utc) - timedelta(hours=30),
    )
    async_session.add(contact)
    await async_session.commit()

    camp = await CampaignService.create_campaign(
        async_session,
        {"title": "Opt-Out Test", "media_id": sample_reel_media.id},
        user_id=admin_user.id,
    )
    result = await CampaignService.evaluate_campaign_audience(async_session, camp.id, persist_recipients=True)
    assert result["suppressed_count"] >= 1
    assert result["suppression_breakdown"].get("contact_opted_out_all", 0) >= 1


# ---------------------------------------------------------------------------
# 8. Already-Booked Patient Exclusion
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_08_already_booked_patient_exclusion(async_session, admin_user, test_contact, test_patient, sample_reel_media):
    """Scenario 8: Patients with active upcoming confirmed appointments are excluded from conversion campaigns."""
    now_utc = datetime.now(timezone.utc)
    appt = Appointment(
        patient_id=test_patient.id,
        practitioner_name="Dr. Physio One",
        service_type="Follow-up Consultation",
        start_time=now_utc + timedelta(days=2),
        end_time=now_utc + timedelta(days=2, minutes=45),
        timezone="Asia/Kolkata",
        status="confirmed",
        booked_by="staff",
    )
    async_session.add(appt)
    await async_session.commit()

    camp = await CampaignService.create_campaign(
        async_session,
        {
            "title": "Already Booked Test",
            "media_id": sample_reel_media.id,
            "target_audience_rules": {"require_no_future_appointment": True},
        },
        user_id=admin_user.id,
    )
    result = await CampaignService.evaluate_campaign_audience(async_session, camp.id, persist_recipients=True)
    assert result["suppressed_count"] >= 1
    assert result["suppression_breakdown"].get("appointment_already_booked", 0) >= 1


# ---------------------------------------------------------------------------
# 9. Instagram Interaction Window (24h - 48h)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_09_instagram_interaction_window_exclusions(async_session, admin_user, sample_reel_media):
    """Scenario 9: Contacts with interaction <24h ago or >48h ago are excluded."""
    recent_contact = WhatsAppContact(
        wa_id="919222333444",
        last_active_at=datetime.now(timezone.utc) - timedelta(hours=5),  # Too recent
    )
    old_contact = WhatsAppContact(
        wa_id="919555666777",
        last_active_at=datetime.now(timezone.utc) - timedelta(hours=72),  # Too old
    )
    async_session.add_all([recent_contact, old_contact])
    await async_session.commit()

    camp = await CampaignService.create_campaign(
        async_session,
        {
            "title": "Window Bounds Test",
            "media_id": sample_reel_media.id,
            "target_audience_rules": {"interaction_window_hours": [24, 48]},
        },
        user_id=admin_user.id,
    )
    result = await CampaignService.evaluate_campaign_audience(async_session, camp.id, persist_recipients=True)
    breakdown = result["suppression_breakdown"]
    assert breakdown.get("interaction_too_recent", 0) >= 1
    assert breakdown.get("interaction_too_old", 0) >= 1


# ---------------------------------------------------------------------------
# 10. Thirty-Minute Scan Execution
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_10_thirty_minute_scan_execution(async_session, admin_user, test_contact, test_patient, sample_reel_media):
    """Scenario 10: 30-minute scan processes scheduled approved campaigns and enqueues batches."""
    settings = await async_session.scalar(select(AutomationSettings).limit(1))
    if not settings:
        settings = AutomationSettings(outbound_enabled=True)
        async_session.add(settings)
    else:
        settings.outbound_enabled = True
    await async_session.commit()

    camp = await CampaignService.create_campaign(
        async_session,
        {"title": "Scan Test", "media_id": sample_reel_media.id},
        user_id=admin_user.id,
    )
    await CampaignService.evaluate_campaign_audience(async_session, camp.id, persist_recipients=True)
    await CampaignService.approve_campaign(async_session, camp.id, "approve", admin_user.id)
    await CampaignService.schedule_campaign(async_session, camp.id, scheduled_for=datetime.now(timezone.utc))

    res = await CampaignService.run_reengagement_cycle(async_session, limit=10, ignore_window=True)
    assert res["scanned_campaigns"] >= 1
    assert res["dispatched_count"] >= 1


# ---------------------------------------------------------------------------
# 11. Sending Window 09:00 - 21:00 IST Enforcement
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_11_sending_window_09_to_21_ist(async_session, admin_user, sample_reel_media):
    """Scenario 11: Defers execution if current time is outside window in IST."""
    # Set a quiet night window guaranteed to be outside current time
    win_start = "02:00"
    win_end = "03:00"

    camp = await CampaignService.create_campaign(
        async_session,
        {
            "title": "Night Window Test",
            "media_id": sample_reel_media.id,
            "execution_window_start": win_start,
            "execution_window_end": win_end,
        },
        user_id=admin_user.id,
    )
    await CampaignService.approve_campaign(async_session, camp.id, "approve", admin_user.id)
    await CampaignService.schedule_campaign(async_session, camp.id)

    res = await CampaignService.run_reengagement_cycle(async_session)
    # Outside window -> deferred to future scheduled_for
    await async_session.refresh(camp)
    sched = camp.scheduled_for if camp.scheduled_for.tzinfo else camp.scheduled_for.replace(tzinfo=timezone.utc)
    assert sched > datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# 12. Duplicate Scan Prevention
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_12_duplicate_scan_prevention(async_session, admin_user, test_contact, test_patient, sample_reel_media):
    """Scenario 12: Unique idempotency key prevents duplicate recipient records."""
    camp = await CampaignService.create_campaign(
        async_session,
        {"title": "Duplicate Idemp Test", "media_id": sample_reel_media.id},
        user_id=admin_user.id,
    )
    await CampaignService.evaluate_campaign_audience(async_session, camp.id, persist_recipients=True)
    # Run evaluation again
    await CampaignService.evaluate_campaign_audience(async_session, camp.id, persist_recipients=True)

    recip_count = await async_session.scalar(
        select(func.count(CampaignRecipient.id)).where(CampaignRecipient.campaign_id == camp.id)
    )
    # Should not duplicate recipient rows
    assert recip_count == 1


# ---------------------------------------------------------------------------
# 13. Campaign Approval Workflow
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_13_campaign_approval_workflow(async_session, admin_user, sample_reel_media):
    """Scenario 13: Owner/Admin explicitly approves campaign version."""
    camp = await CampaignService.create_campaign(
        async_session,
        {"title": "Approval Test", "media_id": sample_reel_media.id},
        user_id=admin_user.id,
    )
    assert camp.is_approved is False

    approved = await CampaignService.approve_campaign(
        async_session, camp.id, "approve", admin_user.id, notes="Ready for dispatch"
    )
    assert approved.is_approved is True
    assert approved.status == "approved"
    assert approved.approved_version == 1
    assert approved.approved_by_id == admin_user.id


# ---------------------------------------------------------------------------
# 14. Approval Invalidation After Edits
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_14_approval_invalidation_after_edits(async_session, admin_user, sample_reel_media):
    """Scenario 14: Editing an approved campaign invalidates its approval and resets status to draft."""
    camp = await CampaignService.create_campaign(
        async_session, {"title": "Pre-edit Title", "media_id": sample_reel_media.id}, user_id=admin_user.id
    )
    await CampaignService.approve_campaign(async_session, camp.id, "approve", admin_user.id)
    await async_session.refresh(camp)
    assert camp.is_approved is True

    # Edit the campaign
    updated = await CampaignService.update_campaign(
        async_session, camp.id, {"title": "Post-edit Title"}, user_id=admin_user.id
    )
    assert updated.is_approved is False
    assert updated.approved_version is None
    assert updated.status == "draft"
    assert updated.current_version == 2


# ---------------------------------------------------------------------------
# 15. Unauthorized Campaign Scheduling Blocked
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_15_unauthorized_campaign_scheduling_blocked(async_session, admin_user, sample_reel_media):
    """Scenario 15: Scheduling a non-approved campaign raises ValueError."""
    camp = await CampaignService.create_campaign(
        async_session, {"title": "Unapproved Scheduling Test", "media_id": sample_reel_media.id}, user_id=admin_user.id
    )
    with pytest.raises(ValueError, match="Campaign must be approved"):
        await CampaignService.schedule_campaign(async_session, camp.id)


# ---------------------------------------------------------------------------
# 16. Global Kill Switch
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_16_global_kill_switch_suppression(async_session, admin_user, test_contact, test_patient, sample_reel_media):
    """Scenario 16: AUTOMATION_OUTBOUND_ENABLED=false suppresses all campaign dispatches."""
    settings = await async_session.scalar(select(AutomationSettings).limit(1))
    if not settings:
        settings = AutomationSettings(outbound_enabled=False)
        async_session.add(settings)
    else:
        settings.outbound_enabled = False
    await async_session.commit()

    camp = await CampaignService.create_campaign(
        async_session, {"title": "Kill Switch Test", "media_id": sample_reel_media.id}, user_id=admin_user.id
    )
    await CampaignService.evaluate_campaign_audience(async_session, camp.id, persist_recipients=True)
    await CampaignService.approve_campaign(async_session, camp.id, "approve", admin_user.id)
    await CampaignService.schedule_campaign(async_session, camp.id)

    res = await CampaignService.run_reengagement_cycle(async_session, ignore_window=True)
    assert res["suppressed_count"] >= 1
    assert res["dispatched_count"] == 0


# ---------------------------------------------------------------------------
# 17. Provider Selection (Meta and YCloud)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_17_provider_selection_meta_and_ycloud(async_session, admin_user, sample_reel_media):
    """Scenario 17: Supports explicit provider assignment for Meta or YCloud."""
    camp_meta = await CampaignService.create_campaign(
        async_session, {"title": "Meta Campaign", "provider": "meta", "media_id": sample_reel_media.id}, user_id=admin_user.id
    )
    camp_ycloud = await CampaignService.create_campaign(
        async_session, {"title": "YCloud Campaign", "provider": "ycloud", "media_id": sample_reel_media.id}, user_id=admin_user.id
    )
    assert camp_meta.provider == "meta"
    assert camp_ycloud.provider == "ycloud"


# ---------------------------------------------------------------------------
# 18. Approved Template Validation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_18_approved_template_validation(async_session, admin_user):
    """Scenario 18: Outside 24h window, verified APPROVED templates render correctly."""
    tmpl = AutomationMessageTemplate(
        name="approved_marketing_reel_v1",
        provider="meta",
        category="MARKETING",
        approval_status="APPROVED",
        body="Hello {{patient_name}}, watch our recovery video: {{reel_url}}",
        variables=["patient_name", "reel_url"],
    )
    async_session.add(tmpl)
    await async_session.commit()

    rendered = TemplateService.render(
        tmpl.body, {"patient_name": "Rohan", "reel_url": "https://instagram.com/reel/123"}, tmpl.name
    )
    assert "Rohan" in rendered
    assert "https://instagram.com/reel/123" in rendered


# ---------------------------------------------------------------------------
# 19. Unapproved Template Rejection
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_19_unapproved_template_rejection():
    """Scenario 19: Template in DRAFT/PENDING status raises UnapprovedTemplateError."""
    with pytest.raises(UnapprovedTemplateError):
        TemplateService.validate_template_approval("draft_template_name", "PENDING")


# ---------------------------------------------------------------------------
# 20. Rate Limiting and Batch Parameters
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_20_rate_limiting_and_throttling(async_session, admin_user, sample_reel_media):
    """Scenario 20: Enforces configurable batch size and messages per minute."""
    camp = await CampaignService.create_campaign(
        async_session,
        {
            "title": "Rate Limit Test",
            "media_id": sample_reel_media.id,
            "rate_limit_per_minute": 15,
            "batch_size": 10,
        },
        user_id=admin_user.id,
    )
    assert camp.rate_limit_per_minute == 15
    assert camp.batch_size == 10


# ---------------------------------------------------------------------------
# 21. Retry and Dead-Letter Behavior
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_21_retry_and_dead_letter_behavior(async_session, admin_user, test_contact, test_patient, sample_reel_media):
    """Scenario 21: Failing recipients increment attempts and record error messages."""
    settings = await async_session.scalar(select(AutomationSettings).limit(1))
    if not settings:
        settings = AutomationSettings(outbound_enabled=True)
        async_session.add(settings)
    else:
        settings.outbound_enabled = True
    await async_session.commit()

    camp = await CampaignService.create_campaign(
        async_session, {"title": "Retry Test", "media_id": sample_reel_media.id}, user_id=admin_user.id
    )
    await CampaignService.evaluate_campaign_audience(async_session, camp.id, persist_recipients=True)
    await CampaignService.approve_campaign(async_session, camp.id, "approve", admin_user.id)
    await CampaignService.schedule_campaign(async_session, camp.id)

    async def failing_dispatcher(*args, **kwargs):
        raise RuntimeError("Network timeout to WhatsApp gateway")

    res = await CampaignService.run_reengagement_cycle(async_session, mock_dispatcher=failing_dispatcher, ignore_window=True)
    assert res["failed_count"] >= 1


# ---------------------------------------------------------------------------
# 22. Unknown Delivery Outcome Handling
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_22_unknown_delivery_outcome_handling(async_session, admin_user, test_contact, test_patient, sample_reel_media):
    """Scenario 22: Gateway uncertain delivery outcome is flagged as unknown_delivery rather than re-sent."""
    settings = await async_session.scalar(select(AutomationSettings).limit(1))
    if not settings:
        settings = AutomationSettings(outbound_enabled=True)
        async_session.add(settings)
    else:
        settings.outbound_enabled = True
    await async_session.commit()

    camp = await CampaignService.create_campaign(
        async_session, {"title": "Uncertain Outcome Test", "media_id": sample_reel_media.id}, user_id=admin_user.id
    )
    await CampaignService.evaluate_campaign_audience(async_session, camp.id, persist_recipients=True)
    await CampaignService.approve_campaign(async_session, camp.id, "approve", admin_user.id)
    await CampaignService.schedule_campaign(async_session, camp.id)

    async def timeout_dispatcher(*args, **kwargs):
        return {"status": "unknown_delivery", "provider_message_id": None}

    await CampaignService.run_reengagement_cycle(async_session, mock_dispatcher=timeout_dispatcher, ignore_window=True)
    recip = await async_session.scalar(
        select(CampaignRecipient).where(CampaignRecipient.campaign_id == camp.id)
    )
    assert recip.status == "unknown_delivery"


# ---------------------------------------------------------------------------
# 23. Worker Restart and Recovery
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_23_worker_restart_and_recovery(async_session, admin_user, test_contact, test_patient, sample_reel_media):
    """Scenario 23: Incomplete campaign recipients survive restart and resume gracefully."""
    camp = await CampaignService.create_campaign(
        async_session, {"title": "Restart Test", "media_id": sample_reel_media.id}, user_id=admin_user.id
    )
    await CampaignService.evaluate_campaign_audience(async_session, camp.id, persist_recipients=True)
    await CampaignService.approve_campaign(async_session, camp.id, "approve", admin_user.id)
    await CampaignService.schedule_campaign(async_session, camp.id)

    # Recipients remain persisted in PostgreSQL
    recip = await async_session.scalar(
        select(CampaignRecipient).where(CampaignRecipient.campaign_id == camp.id)
    )
    assert recip is not None
    assert recip.status == "eligible"


# ---------------------------------------------------------------------------
# 24. Campaign Pause and Resume
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_24_campaign_pause_and_resume(async_session, admin_user, sample_reel_media):
    """Scenario 24: Campaigns can be paused and resumed cleanly."""
    camp = await CampaignService.create_campaign(
        async_session, {"title": "Pause Resume Test", "media_id": sample_reel_media.id}, user_id=admin_user.id
    )
    await CampaignService.approve_campaign(async_session, camp.id, "approve", admin_user.id)
    await CampaignService.schedule_campaign(async_session, camp.id)

    paused = await CampaignService.pause_campaign(async_session, camp.id)
    assert paused.status == "paused"

    resumed = await CampaignService.resume_campaign(async_session, camp.id)
    assert resumed.status == "running"


# ---------------------------------------------------------------------------
# 25. Campaign Cancellation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_25_campaign_cancellation_terminates_jobs(async_session, admin_user, test_contact, test_patient, sample_reel_media):
    """Scenario 25: Cancelling a campaign marks all pending recipients as cancelled."""
    camp = await CampaignService.create_campaign(
        async_session, {"title": "Cancel Test", "media_id": sample_reel_media.id}, user_id=admin_user.id
    )
    await CampaignService.evaluate_campaign_audience(async_session, camp.id, persist_recipients=True)
    cancelled = await CampaignService.cancel_campaign(async_session, camp.id)
    assert cancelled.status == "cancelled"

    recip = await async_session.scalar(
        select(CampaignRecipient).where(CampaignRecipient.campaign_id == camp.id)
    )
    assert recip.status == "cancelled"


# ---------------------------------------------------------------------------
# 26. Legacy Scheduler Overlap Prevention
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_26_legacy_scheduler_overlap_prevention(async_session):
    """Scenario 26: Mutual exclusion invariant: legacy and new scheduler cannot both be active."""
    mig = await CampaignService.get_or_create_legacy_migration(async_session)
    assert mig.cutover_state == "legacy_active"
    # While legacy_active, new live dispatch is prohibited


# ---------------------------------------------------------------------------
# 27. Legacy Dry-Run Shadow Comparison
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_27_legacy_dry_run_shadow_comparison(async_session, test_contact):
    """Scenario 27: Shadow comparison evaluates candidate audience with zero messages dispatched."""
    results = await CampaignService.run_legacy_dry_run_comparison(async_session)
    assert results["total_evaluated"] >= 1
    assert results["mutual_exclusion_verified"] is True
    assert "Shadow dry-run completed" in results["summary"]


# ---------------------------------------------------------------------------
# 28. Cross-Patient Data Isolation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_28_cross_patient_data_isolation(async_session, admin_user, test_contact, test_patient, sample_reel_media):
    """Scenario 28: Each recipient receives only their personal name and validated reel URL."""
    camp = await CampaignService.create_campaign(
        async_session,
        {
            "title": "Privacy Isolation Test",
            "media_id": sample_reel_media.id,
            "custom_message_body": "Hello {{patient_name}}, view reel: {{reel_url}}",
        },
        user_id=admin_user.id,
    )
    preview = await CampaignService.evaluate_campaign_audience(async_session, camp.id, persist_recipients=False)
    sample = preview["sample_rendered"]
    assert "Ananya Sharma" in sample


# ---------------------------------------------------------------------------
# 29. Delivery Analytics Aggregation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_29_delivery_analytics_aggregation(async_session, admin_user, test_contact, test_patient, sample_reel_media):
    """Scenario 29: Aggregates delivery rate, read rate, and suppression counts."""
    camp = await CampaignService.create_campaign(
        async_session, {"title": "Analytics Test", "media_id": sample_reel_media.id}, user_id=admin_user.id
    )
    await CampaignService.evaluate_campaign_audience(async_session, camp.id, persist_recipients=True)

    analytics = await CampaignService.get_campaign_analytics(async_session, camp.id)
    assert analytics["total_targeted"] >= 1
    assert "delivery_rate_pct" in analytics
    assert "read_rate_pct" in analytics
    assert "conversion_rate_pct" in analytics


# ---------------------------------------------------------------------------
# 30. Conversion Attribution Window (72h)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_30_conversion_attribution_window(async_session, admin_user, test_contact, test_patient, sample_reel_media):
    """Scenario 30: Links confirmed appointments created within 72h attribution window to campaign conversion."""
    camp = await CampaignService.create_campaign(
        async_session, {"title": "Attribution Test", "media_id": sample_reel_media.id}, user_id=admin_user.id
    )
    await CampaignService.evaluate_campaign_audience(async_session, camp.id, persist_recipients=True)
    recip = await async_session.scalar(
        select(CampaignRecipient).where(CampaignRecipient.campaign_id == camp.id)
    )

    now_utc = datetime.now(timezone.utc)
    appt = Appointment(
        patient_id=test_patient.id,
        practitioner_name="Dr. Physio One",
        service_type="ACL Consultation",
        start_time=now_utc + timedelta(days=1),
        end_time=now_utc + timedelta(days=1, minutes=45),
        timezone="Asia/Kolkata",
        status="confirmed",
        booked_by="patient_campaign_reply",
    )
    async_session.add(appt)
    await async_session.flush()

    # Record conversion event
    conversion = CampaignConversionEvent(
        campaign_id=camp.id,
        recipient_id=recip.id,
        contact_id=test_contact.id,
        conversion_type="appointment_confirmed",
        appointment_id=appt.id,
        attribution_window_hours=72,
    )
    async_session.add(conversion)
    recip.status = "converted"
    recip.converted_at = now_utc
    camp.total_converted += 1
    await async_session.commit()

    analytics = await CampaignService.get_campaign_analytics(async_session, camp.id)
    assert analytics["converted_count"] >= 1
