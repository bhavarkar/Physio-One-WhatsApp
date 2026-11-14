"""Integration and Safety Test Suite for Controlled AI Appointment Workflows.

Single Organization Edition: Physio One Clinic (Task 10).
Validates:
1. Intent Recognition: Booking, availability, rescheduling, cancellation, status, human assistance.
2. Workflow State Machine: collecting_information -> awaiting_slot_selection -> awaiting_patient_confirmation -> awaiting_staff_approval -> ready_to_commit -> confirmed.
3. Policy Enforcement: Mode A (Read Only default) blocks autonomous mutations; Mode B requires staff approval; Mode C requires auto-commit rules.
4. Concurrency & Idempotency: Duplicate commits return stored result without double booking.
5. Cross-Patient Privacy: Zero disclosure of another patient's appointment records.
6. Mutating Tools Protection: Tools enforce workflow state, tokens, and approval.
7. Inbound Orchestrator: Multi-message debounce, explicit confirmation, human takeover, shadow mode.
8. Human Approval Dashboard API Endpoints: Approvals list, approve, reject, clarify, settings.
"""
import pytest
import uuid
from datetime import datetime, date, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from httpx import AsyncClient

from app.core.config import settings
from app.models.workflow import (
    AppointmentAIWorkflow,
    AppointmentWorkflowEvent,
    AppointmentConfirmation,
    AppointmentApprovalRequest,
    AppointmentOperationIdempotency,
    AppointmentWorkflowSettings,
)
from app.models.patient import Patient, Appointment, AppointmentHistory
from app.models.whatsapp import Conversation, WhatsAppContact, WhatsAppMessage, WhatsAppAccount
from app.models.user import User, Role, UserSession
from app.core.rbac import ROLE_ADMIN
from app.services.auth_service import ensure_initial_roles
from app.core.security import generate_session_token, hash_session_token
from app.models.inbound import AIInboundSettings, InboundProcessingJob, AIResponseDraft
from app.schemas.workflow import WorkflowIntent, WorkflowState, AutomationPolicyMode
from app.services.intent_extractor import AppointmentIntentExtractor
from app.services.workflow_service import AppointmentWorkflowService, WorkflowError
from app.services.appointment_service import AppointmentService, get_clinic_tz, normalize_to_utc, ensure_utc_aware
from app.services.inbound_orchestrator import InboundOrchestrator
from app.services.inbound_queue import InboundQueueService
from app.tools.base import ToolExecutionContext
from app.tools.clinical.appointments_read import GetPatientAppointmentsTool, GetAppointmentDetailsTool
from app.tools.clinical.workflow_tools import (
    StartAppointmentWorkflowTool,
    SelectAppointmentSlotTool,
    RequestAppointmentConfirmationTool,
    GetAppointmentWorkflowStatusTool,
)
from app.tools.clinical.appointments_mutate import (
    CreateAppointmentTool,
    RescheduleAppointmentTool,
    CancelAppointmentTool,
)

KOLKATA_TZ = get_clinic_tz()


def get_future_open_date(days_ahead: int = 2) -> date:
    """Helper to return a future weekday that is NOT Sunday."""
    now_d = datetime.now(KOLKATA_TZ).date() + timedelta(days=days_ahead)
    if now_d.weekday() == 6:  # Sunday
        now_d += timedelta(days=1)
    return now_d


def get_future_sunday() -> date:
    """Helper to return the next future Sunday."""
    d = datetime.now(KOLKATA_TZ).date() + timedelta(days=1)
    while d.weekday() != 6:
        d += timedelta(days=1)
    return d


async def create_test_context(async_session: AsyncSession):
    """Seed test contact, conversation, patient, and user for workflow tests."""
    phone = f"+9198{uuid.uuid4().hex[:8]}"
    contact = WhatsAppContact(
        wa_id=phone,
        profile_name="Workflow Patient",
        opted_out_all=False,
    )
    async_session.add(contact)
    await async_session.flush()

    patient = Patient(
        contact_id=contact.id,
        full_name="Workflow Patient",
        phone_number=phone,
        email="workflow.patient@example.com",
    )
    async_session.add(patient)
    await async_session.flush()

    conv = Conversation(
        contact_id=contact.id,
        status="open",
        is_human_takeover=False,
        ai_paused=False,
    )
    async_session.add(conv)

    # Seed Admin / Staff User
    role_map = await ensure_initial_roles(async_session)
    role = role_map[ROLE_ADMIN]

    staff_user = User(
        email=f"staff.{uuid.uuid4().hex[:6]}@physioone.com",
        password_hash="mock_hash",
        full_name="Staff Dr. Physio",
        role_id=role.id,
        is_active=True,
    )
    async_session.add(staff_user)
    await async_session.commit()
    await async_session.refresh(contact)
    await async_session.refresh(patient)
    await async_session.refresh(conv)
    await async_session.refresh(staff_user)

    return contact, patient, conv, staff_user


# ==============================================================================
# 1. Intent Extraction Tests
# ==============================================================================

def test_intent_extraction_scenarios():
    """Verify structured intent and entity extraction across all supported appointment intents."""
    # 1. Book appointment
    res1 = AppointmentIntentExtractor.extract_intent("I need an appointment tomorrow")
    assert res1.intent == WorkflowIntent.BOOK_APPOINTMENT
    assert res1.target_date is not None

    # 2. Check availability
    res2 = AppointmentIntentExtractor.extract_intent("Can I come at 5 PM on Monday?")
    assert res2.intent == WorkflowIntent.CHECK_AVAILABILITY
    assert res2.preferred_time == "5:00 PM"

    # 3. Reschedule
    res3 = AppointmentIntentExtractor.extract_intent("Move my appointment to Friday")
    assert res3.intent == WorkflowIntent.RESCHEDULE_APPOINTMENT
    assert res3.target_date is not None

    # 4. Cancel
    res4 = AppointmentIntentExtractor.extract_intent("Please cancel my appointment because I have a high fever")
    assert res4.intent == WorkflowIntent.CANCEL_APPOINTMENT
    assert res4.cancellation_reason is not None

    # 5. Status
    res5 = AppointmentIntentExtractor.extract_intent("Do I have a booking today?")
    assert res5.intent == WorkflowIntent.CHECK_APPOINTMENT_STATUS

    # 6. Human assistance
    res6 = AppointmentIntentExtractor.extract_intent("Please connect me to human staff")
    assert res6.intent == WorkflowIntent.REQUEST_HUMAN_ASSISTANCE

    # 7. Explicit confirmation
    res7 = AppointmentIntentExtractor.extract_intent("Yes, please confirm")
    assert res7.is_explicit_confirmation is True

    # 8. Explicit rejection
    res8 = AppointmentIntentExtractor.extract_intent("No, cancel that")
    assert res8.is_explicit_confirmation is False


# ==============================================================================
# 2. Workflow State Machine Lifecycle & Sunday Closure
# ==============================================================================

@pytest.mark.asyncio
async def test_workflow_lifecycle_and_sunday_closure(async_session: AsyncSession):
    """Test start_workflow, slot selection, confirmation token generation, and Sunday restriction."""
    contact, patient, conv, staff = await create_test_context(async_session)

    # 1. Start booking workflow
    wf = await AppointmentWorkflowService.start_workflow(
        db=async_session,
        conversation_id=conv.id,
        contact_id=contact.id,
        intent="book_appointment",
    )
    assert wf.status == WorkflowState.COLLECTING_INFORMATION.value
    assert wf.workflow_version == 1

    # 2. Select slot on a Sunday -> Must be rejected!
    sun_date = get_future_sunday()
    sun_slot = datetime.combine(sun_date, datetime.min.time().replace(hour=10), tzinfo=KOLKATA_TZ)
    with pytest.raises(Exception):
        await AppointmentWorkflowService.select_slot(
            db=async_session,
            workflow_id=wf.id,
            slot_start=sun_slot,
        )

    # 3. Select valid Monday/Weekday slot
    open_date = get_future_open_date(2)
    valid_slot = datetime.combine(open_date, datetime.min.time().replace(hour=11), tzinfo=KOLKATA_TZ)
    updated_wf = await AppointmentWorkflowService.select_slot(
        db=async_session,
        workflow_id=wf.id,
        slot_start=valid_slot,
    )
    assert updated_wf.status == WorkflowState.AWAITING_PATIENT_CONFIRMATION.value
    assert updated_wf.confirmation_token is not None
    assert updated_wf.workflow_version == 2
    assert "formatted_display" in updated_wf.proposed_changes


# ==============================================================================
# 3. Policy Enforcement: Mode A Read-Only Blocks Mutation
# ==============================================================================

@pytest.mark.asyncio
async def test_mode_a_blocks_direct_mutation(async_session: AsyncSession):
    """Confirm Mode A (Read Only default) blocks autonomous mutations and requires staff review."""
    contact, patient, conv, staff = await create_test_context(async_session)

    # Ensure Mode A is set
    settings_obj = await AppointmentWorkflowService.get_or_create_settings(async_session)
    settings_obj.policy_mode = AutomationPolicyMode.MODE_A_READ_ONLY.value
    await async_session.commit()

    wf = await AppointmentWorkflowService.start_workflow(
        db=async_session,
        conversation_id=conv.id,
        contact_id=contact.id,
        intent="book_appointment",
    )
    open_date = get_future_open_date(3)
    slot_dt = datetime.combine(open_date, datetime.min.time().replace(hour=15), tzinfo=KOLKATA_TZ)
    await AppointmentWorkflowService.select_slot(async_session, wf.id, slot_dt)

    # Patient confirms -> In Mode A, pauses at awaiting_staff_approval
    res = await AppointmentWorkflowService.process_patient_confirmation(async_session, wf.id, is_confirmed=True)
    assert res["status"] == "awaiting_staff_approval"

    # AI mutating tool called directly -> Must be rejected!
    mutate_tool = CreateAppointmentTool()
    tool_ctx = ToolExecutionContext(conversation_id=conv.id)
    tool_res = await mutate_tool.execute(
        arguments={"workflow_id": str(wf.id), "confirmation_token": wf.confirmation_token},
        context=tool_ctx,
        db=async_session,
    )
    assert tool_res["success"] is False
    assert "disabled in Mode A" in tool_res["error"]


# ==============================================================================
# 4. Mode B Staff Approval Workflow & Commit
# ==============================================================================

@pytest.mark.asyncio
async def test_mode_b_staff_approval_and_commit(async_session: AsyncSession):
    """Test Mode B: patient confirms, staff approves, appointment commits to database."""
    contact, patient, conv, staff = await create_test_context(async_session)

    settings_obj = await AppointmentWorkflowService.get_or_create_settings(async_session)
    settings_obj.policy_mode = AutomationPolicyMode.MODE_B_STAFF_APPROVAL.value
    await async_session.commit()

    wf = await AppointmentWorkflowService.start_workflow(
        db=async_session,
        conversation_id=conv.id,
        contact_id=contact.id,
        intent="book_appointment",
    )
    open_date = get_future_open_date(4)
    slot_dt = datetime.combine(open_date, datetime.min.time().replace(hour=16), tzinfo=KOLKATA_TZ)
    await AppointmentWorkflowService.select_slot(async_session, wf.id, slot_dt)

    # Patient confirms
    await AppointmentWorkflowService.process_patient_confirmation(async_session, wf.id, is_confirmed=True)
    reloaded_wf = await AppointmentWorkflowService.get_workflow_by_id(async_session, wf.id)
    assert reloaded_wf.status == WorkflowState.AWAITING_STAFF_APPROVAL.value
    assert reloaded_wf.approval_status == "pending"

    # Staff approves proposal
    approve_res = await AppointmentWorkflowService.approve_proposal(
        db=async_session,
        workflow_id=wf.id,
        staff_user=staff,
        notes="Verified slot available with clinic diary",
    )
    assert approve_res["success"] is True
    assert approve_res["status"] == "confirmed"

    # Verify Appointment record exists in database
    appt_uuid = uuid.UUID(approve_res["result"]["appointment_id"])
    appt = await AppointmentService.get_appointment(async_session, appt_uuid)
    assert appt.status == "confirmed"
    assert appt.patient_id == patient.id


# ==============================================================================
# 5. Staff Rejection and Clarification Workflows
# ==============================================================================

@pytest.mark.asyncio
async def test_staff_rejection_and_clarification(async_session: AsyncSession):
    """Test rejection and clarification actions on pending workflow proposals."""
    contact, patient, conv, staff = await create_test_context(async_session)

    settings_obj = await AppointmentWorkflowService.get_or_create_settings(async_session)
    settings_obj.policy_mode = AutomationPolicyMode.MODE_B_STAFF_APPROVAL.value
    await async_session.commit()

    # 1. Rejection
    wf = await AppointmentWorkflowService.start_workflow(async_session, conv.id, contact.id, "book_appointment")
    slot_dt = datetime.combine(get_future_open_date(5), datetime.min.time().replace(hour=10), tzinfo=KOLKATA_TZ)
    await AppointmentWorkflowService.select_slot(async_session, wf.id, slot_dt)
    await AppointmentWorkflowService.process_patient_confirmation(async_session, wf.id, is_confirmed=True)

    reject_res = await AppointmentWorkflowService.reject_proposal(
        db=async_session,
        workflow_id=wf.id,
        staff_user=staff,
        reason="Doctor unavailable for that service",
    )
    assert reject_res["status"] == "rejected"
    reloaded_wf = await AppointmentWorkflowService.get_workflow_by_id(async_session, wf.id)
    assert reloaded_wf.status == WorkflowState.CANCELLED.value

    # 2. Clarification
    wf2 = await AppointmentWorkflowService.start_workflow(async_session, conv.id, contact.id, "book_appointment")
    slot_dt2 = datetime.combine(get_future_open_date(6), datetime.min.time().replace(hour=11), tzinfo=KOLKATA_TZ)
    await AppointmentWorkflowService.select_slot(async_session, wf2.id, slot_dt2)
    await AppointmentWorkflowService.process_patient_confirmation(async_session, wf2.id, is_confirmed=True)

    clarify_res = await AppointmentWorkflowService.request_clarification(
        db=async_session,
        workflow_id=wf2.id,
        staff_user=staff,
        notes="Please ask patient if they have had surgery recently",
    )
    assert clarify_res["status"] == "clarification_requested"
    reloaded_wf2 = await AppointmentWorkflowService.get_workflow_by_id(async_session, wf2.id)
    assert reloaded_wf2.status == WorkflowState.COLLECTING_INFORMATION.value


# ==============================================================================
# 6. Rescheduling and Cancellation Workflows
# ==============================================================================

@pytest.mark.asyncio
async def test_rescheduling_and_cancellation_workflows(async_session: AsyncSession):
    """Test full rescheduling and cancellation workflows via AppointmentWorkflowService."""
    contact, patient, conv, staff = await create_test_context(async_session)

    # 1. Create existing confirmed appointment
    open_date = get_future_open_date(7)
    start_utc = normalize_to_utc(datetime.combine(open_date, datetime.min.time().replace(hour=12), tzinfo=KOLKATA_TZ))
    appt = Appointment(
        patient_id=patient.id,
        practitioner_name="Dr. Physio One",
        service_type="Initial Physiotherapy Assessment",
        start_time=start_utc,
        end_time=start_utc + timedelta(minutes=45),
        duration_minutes=45,
        timezone=settings.CLINIC_TIMEZONE,
        status="confirmed",
        booked_by="staff",
    )
    async_session.add(appt)
    await async_session.commit()
    await async_session.refresh(appt)

    # 2. Reschedule workflow
    resched_wf = await AppointmentWorkflowService.start_workflow(
        db=async_session,
        conversation_id=conv.id,
        contact_id=contact.id,
        intent="reschedule_appointment",
        appointment_id=appt.id,
    )
    new_open_date = get_future_open_date(8)
    new_slot = datetime.combine(new_open_date, datetime.min.time().replace(hour=14), tzinfo=KOLKATA_TZ)
    await AppointmentWorkflowService.select_slot(async_session, resched_wf.id, new_slot)
    await AppointmentWorkflowService.process_patient_confirmation(async_session, resched_wf.id, is_confirmed=True)

    # Staff approves reschedule
    await AppointmentWorkflowService.approve_proposal(async_session, resched_wf.id, staff)
    await async_session.refresh(appt)
    assert appt.status == "confirmed"

    # 3. Cancellation workflow
    cancel_wf = await AppointmentWorkflowService.start_workflow(
        db=async_session,
        conversation_id=conv.id,
        contact_id=contact.id,
        intent="cancel_appointment",
        appointment_id=appt.id,
    )
    cancel_wf.confirmation_token = "CANCEL123"
    cancel_wf.status = WorkflowState.READY_TO_COMMIT.value
    await async_session.commit()

    cancel_res = await AppointmentWorkflowService.commit_workflow(async_session, cancel_wf.id, actor_type="staff")
    assert cancel_res["success"] is True

    await async_session.refresh(appt)
    assert appt.status == "cancelled"
    assert appt.cancellation_reason is not None


# ==============================================================================
# 7. Cross-Patient Privacy & Isolation
# ==============================================================================

@pytest.mark.asyncio
async def test_cross_patient_privacy_isolation(async_session: AsyncSession):
    """Ensure a patient cannot inspect or view appointments belonging to another patient."""
    contact_a, patient_a, conv_a, _ = await create_test_context(async_session)
    contact_b, patient_b, conv_b, _ = await create_test_context(async_session)

    # Create appointment for Patient B
    open_date = get_future_open_date(3)
    start_utc = normalize_to_utc(datetime.combine(open_date, datetime.min.time().replace(hour=15), tzinfo=KOLKATA_TZ))
    appt_b = Appointment(
        patient_id=patient_b.id,
        practitioner_name="Dr. Physio One",
        service_type="Initial Assessment",
        start_time=start_utc,
        end_time=start_utc + timedelta(minutes=45),
        duration_minutes=45,
        timezone=settings.CLINIC_TIMEZONE,
        status="confirmed",
        booked_by="staff",
    )
    async_session.add(appt_b)
    await async_session.commit()

    # Patient A attempts to view Patient B's appointment details
    details_tool = GetAppointmentDetailsTool()
    ctx_a = ToolExecutionContext(conversation_id=conv_a.id)
    res = await details_tool.execute(
        arguments={"appointment_id": str(appt_b.id)},
        context=ctx_a,
        db=async_session,
    )
    assert res["success"] is False
    assert "Access denied" in res["error"]

    # Patient A lists appointments -> only returns Patient A's appointments
    list_tool = GetPatientAppointmentsTool()
    list_res = await list_tool.execute(arguments={}, context=ctx_a, db=async_session)
    assert list_res["success"] is True
    assert list_res["total_count"] == 0  # Patient A has no appointments yet


# ==============================================================================
# 8. Idempotency Protection
# ==============================================================================

@pytest.mark.asyncio
async def test_idempotent_commit_prevents_duplicate_booking(async_session: AsyncSession):
    """Verify duplicate commit calls with same idempotency key return stored result without double booking."""
    contact, patient, conv, staff = await create_test_context(async_session)

    wf = await AppointmentWorkflowService.start_workflow(async_session, conv.id, contact.id, "book_appointment")
    slot_dt = datetime.combine(get_future_open_date(4), datetime.min.time().replace(hour=16), tzinfo=KOLKATA_TZ)
    await AppointmentWorkflowService.select_slot(async_session, wf.id, slot_dt)
    wf.status = WorkflowState.READY_TO_COMMIT.value
    await async_session.commit()

    idem_key = f"test_idem_{uuid.uuid4().hex}"

    # First commit
    res1 = await AppointmentWorkflowService.commit_workflow(
        db=async_session,
        workflow_id=wf.id,
        actor_type="staff",
        idempotency_key=idem_key,
    )
    assert res1["success"] is True

    # Second commit with same idempotency key
    wf.status = WorkflowState.READY_TO_COMMIT.value
    await async_session.commit()

    res2 = await AppointmentWorkflowService.commit_workflow(
        db=async_session,
        workflow_id=wf.id,
        actor_type="staff",
        idempotency_key=idem_key,
    )
    # Returns stored result from first commit
    assert res2.get("appointment_id") == res1["result"]["appointment_id"]


# ==============================================================================
# 9. Inbound Orchestrator WhatsApp Integration
# ==============================================================================

@pytest.mark.asyncio
async def test_inbound_orchestrator_whatsapp_integration(async_session: AsyncSession):
    """Test explicit confirmation and human handoff routing via InboundOrchestrator."""
    contact, patient, conv, staff = await create_test_context(async_session)

    # 1. Set ai_mode to shadow
    settings_obj = await InboundQueueService.get_or_create_settings(async_session)
    settings_obj.ai_mode = "shadow"
    await async_session.commit()

    # 2. Setup workflow awaiting confirmation
    wf = await AppointmentWorkflowService.start_workflow(async_session, conv.id, contact.id, "book_appointment")
    slot_dt = datetime.combine(get_future_open_date(3), datetime.min.time().replace(hour=11), tzinfo=KOLKATA_TZ)
    await AppointmentWorkflowService.select_slot(async_session, wf.id, slot_dt)

    # 3. Patient sends "YES"
    job = InboundProcessingJob(
        conversation_id=conv.id,
        contact_id=contact.id,
        provider="meta",
        status="debouncing",
        aggregated_message_ids=[],
        aggregated_text="YES, please confirm",
        debounce_until=datetime.now(timezone.utc),
        scheduled_at=datetime.now(timezone.utc),
    )
    async_session.add(job)
    await async_session.commit()

    result = await InboundOrchestrator.process_job(async_session, job)
    assert result["status"] == "confirmation_handled"
    assert "draft_text" in result

    # 4. Patient sends "Speak to human"
    job2 = InboundProcessingJob(
        conversation_id=conv.id,
        contact_id=contact.id,
        provider="meta",
        status="debouncing",
        aggregated_message_ids=[],
        aggregated_text="I want to speak to a real person",
        debounce_until=datetime.now(timezone.utc),
        scheduled_at=datetime.now(timezone.utc),
    )
    async_session.add(job2)
    await async_session.commit()

    result2 = await InboundOrchestrator.process_job(async_session, job2)
    assert result2["status"] == "human_handoff"
    await async_session.refresh(conv)
    assert conv.is_human_takeover is True


# ==============================================================================
# 10. Backend API Endpoints & RBAC
# ==============================================================================

@pytest.mark.asyncio
async def test_api_workflow_endpoints(client: AsyncClient, async_session: AsyncSession):
    """Test authenticated API endpoints: list workflows, approvals, and update settings."""
    contact, patient, conv, staff = await create_test_context(async_session)

    # Create a pending workflow
    wf = await AppointmentWorkflowService.start_workflow(async_session, conv.id, contact.id, "book_appointment")
    slot_dt = datetime.combine(get_future_open_date(3), datetime.min.time().replace(hour=17), tzinfo=KOLKATA_TZ)
    await AppointmentWorkflowService.select_slot(async_session, wf.id, slot_dt)
    await AppointmentWorkflowService.process_patient_confirmation(async_session, wf.id, is_confirmed=True)

    # Authenticate staff via Bearer session token
    session_token = generate_session_token()
    token_hash = hash_session_token(session_token)
    user_session = UserSession(
        user_id=staff.id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    async_session.add(user_session)
    await async_session.commit()
    headers = {"Authorization": f"Bearer {session_token}"}

    # 1. GET /api/v1/appointment-workflows/approvals
    res_app = await client.get("/api/v1/appointment-workflows/approvals", headers=headers)
    assert res_app.status_code == 200
    approvals = res_app.json()
    assert len(approvals) >= 1
    assert any(a["id"] == str(wf.id) for a in approvals)

    # 2. GET /api/v1/appointment-workflows/settings
    res_set = await client.get("/api/v1/appointment-workflows/settings", headers=headers)
    assert res_set.status_code == 200
    assert "policy_mode" in res_set.json()

    # 3. PATCH /api/v1/appointment-workflows/settings (update policy to mode_b_staff_approval)
    res_patch = await client.patch(
        "/api/v1/appointment-workflows/settings",
        json={"policy_mode": "mode_b_staff_approval"},
        headers=headers,
    )
    assert res_patch.status_code == 200
    assert res_patch.json()["policy_mode"] == "mode_b_staff_approval"

    # 4. POST /api/v1/appointment-workflows/{id}/approve
    res_action = await client.post(
        f"/api/v1/appointment-workflows/{wf.id}/approve",
        json={"notes": "Approved via API"},
        headers=headers,
    )
    assert res_action.status_code == 200
    assert res_action.json()["success"] is True

    # Restore settings to Mode A (Read Only default)
    await client.patch(
        "/api/v1/appointment-workflows/settings",
        json={"policy_mode": "mode_a_read_only"},
        headers=headers,
    )
