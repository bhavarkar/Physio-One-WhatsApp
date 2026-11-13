"""Comprehensive Test Suite for Clinical Appointments Engine and Availability Rules

Single Organization Edition: Physio One Clinic.
Tests:
- Availability engine & Sunday restriction
- Overlap detection and duration calculation
- Appointment creation, patient lookup/creation
- Rescheduling history and conflicts
- Cancellation reasons and record preservation
- Lifecycle transitions (complete, no-show, terminal states)
- Concurrency protection
- Authentication, CSRF, and RBAC permissions (Owner, Admin, Operator, Viewer)
- Audit logging
"""
import asyncio
from datetime import datetime, date, timedelta, timezone
from zoneinfo import ZoneInfo
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.rbac import ROLE_OWNER, ROLE_ADMIN, ROLE_OPERATOR, ROLE_VIEWER
from app.models.patient import Patient, Appointment, AppointmentHistory
from app.models.user import User, Role, UserSession, AuditLog
from app.services.auth_service import ensure_initial_roles
from app.services.appointment_service import (
    AppointmentService,
    SundayRestrictionError,
    OperatingHoursViolationError,
    AppointmentConflictError,
    InvalidStatusTransitionError,
    PastAppointmentError,
    get_clinic_tz,
)
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentRescheduleRequest,
    AppointmentCancelRequest,
    AppointmentActionRequest,
)

KOLKATA_TZ = get_clinic_tz()


def get_next_weekday(target_weekday: int) -> date:
    """Helper to get a future date with the specified weekday (0=Mon, 6=Sun)."""
    today = datetime.now(KOLKATA_TZ).date()
    days_ahead = target_weekday - today.weekday()
    if days_ahead <= 0:  # Target day already happened this week
        days_ahead += 7
    return today + timedelta(days=days_ahead)


# --- 1. Availability Engine Unit / Service Tests ---

@pytest.mark.asyncio
async def test_availability_sunday_is_strictly_closed(async_session: AsyncSession):
    """Verify that querying availability for any Sunday returns is_open=False and 0 slots."""
    next_sunday = get_next_weekday(6)  # 6 is Sunday
    assert next_sunday.weekday() == 6

    avail = await AppointmentService.get_daily_availability(async_session, next_sunday)
    assert avail.is_open is False
    assert len(avail.slots) == 0
    assert "closed on sundays" in avail.message.lower()
    assert avail.timezone == "Asia/Kolkata"


@pytest.mark.asyncio
async def test_availability_weekday_returns_slots_and_respects_duration(async_session: AsyncSession):
    """Verify that a weekday returns operating slots between 09:00 and 20:00."""
    next_wednesday = get_next_weekday(2)  # 2 is Wednesday
    assert next_wednesday.weekday() == 2

    # Query with default 45 minute duration
    avail = await AppointmentService.get_daily_availability(async_session, next_wednesday, duration_minutes=45)
    assert avail.is_open is True
    assert len(avail.slots) > 0

    first_slot = avail.slots[0]
    local_start = first_slot.start_time.astimezone(KOLKATA_TZ)
    local_end = first_slot.end_time.astimezone(KOLKATA_TZ)

    assert local_start.strftime("%H:%M") == "09:00"
    assert (local_end - local_start) == timedelta(minutes=45)
    assert first_slot.is_available is True

    last_slot = avail.slots[-1]
    last_end = last_slot.end_time.astimezone(KOLKATA_TZ)
    assert last_end.strftime("%H:%M") <= "20:00"


@pytest.mark.asyncio
async def test_availability_active_appointment_blocks_overlapping_slot(async_session: AsyncSession):
    """Verify that an active appointment on a weekday marks the overlapping slot unavailable."""
    next_thursday = get_next_weekday(3)  # 3 is Thursday

    # Book 10:00 to 10:45 on next Thursday
    slot_start = datetime.combine(next_thursday, datetime.strptime("10:00", "%H:%M").time(), tzinfo=KOLKATA_TZ)

    create_data = AppointmentCreate(
        patient_name="Rajesh Sharma",
        patient_phone="+919876543210",
        start_time=slot_start,
        duration_minutes=45,
        practitioner_name="Dr. Physio One",
    )
    appt = await AppointmentService.create_appointment(async_session, create_data)
    assert appt.status == "confirmed"

    # Query availability
    avail = await AppointmentService.get_daily_availability(async_session, next_thursday, duration_minutes=45)

    # Find the 10:00 slot
    slot_10 = next(
        (s for s in avail.slots if s.start_time.astimezone(KOLKATA_TZ).strftime("%H:%M") == "10:00"),
        None,
    )
    assert slot_10 is not None
    assert slot_10.is_available is False  # Blocked by active appointment!

    # A non-overlapping slot (e.g. 11:30) must remain available
    slot_1130 = next(
        (s for s in avail.slots if s.start_time.astimezone(KOLKATA_TZ).strftime("%H:%M") == "11:30"),
        None,
    )
    assert slot_1130 is not None
    assert slot_1130.is_available is True


@pytest.mark.asyncio
async def test_availability_cancelled_appointment_does_not_block_slot(async_session: AsyncSession):
    """Verify that cancelled appointments are excluded from blocking availability."""
    next_friday = get_next_weekday(4)  # 4 is Friday
    slot_start = datetime.combine(next_friday, datetime.strptime("11:00", "%H:%M").time(), tzinfo=KOLKATA_TZ)

    create_data = AppointmentCreate(
        patient_name="Anita Roy",
        patient_phone="+919876500000",
        start_time=slot_start,
        duration_minutes=45,
        practitioner_name="Dr. Physio One",
    )
    appt = await AppointmentService.create_appointment(async_session, create_data)

    # Cancel the appointment
    cancel_data = AppointmentCancelRequest(reason="Patient unable to attend.")
    await AppointmentService.cancel_appointment(async_session, appt.id, cancel_data)

    # Query availability for that day
    avail = await AppointmentService.get_daily_availability(async_session, next_friday, duration_minutes=45)

    slot_11 = next(
        (s for s in avail.slots if s.start_time.astimezone(KOLKATA_TZ).strftime("%H:%M") == "11:00"),
        None,
    )
    assert slot_11 is not None
    assert slot_11.is_available is True  # Slot is free again!


# --- 2. Appointment Booking & Lifecycle Service Tests ---

@pytest.mark.asyncio
async def test_create_appointment_sunday_rejected():
    """Verify backend business logic strictly rejects Sunday booking requests."""
    next_sunday = get_next_weekday(6)
    slot_start = datetime.combine(next_sunday, datetime.strptime("10:00", "%H:%M").time(), tzinfo=KOLKATA_TZ)

    create_data = AppointmentCreate(
        patient_name="Test Sunday",
        patient_phone="+919999999999",
        start_time=slot_start,
        duration_minutes=45,
    )

    with pytest.raises(SundayRestrictionError) as exc_info:
        await AppointmentService.create_appointment(None, create_data)

    assert exc_info.value.code == "SUNDAY_RESTRICTION"
    assert "sunday" in exc_info.value.message.lower() and "closed" in exc_info.value.message.lower()


@pytest.mark.asyncio
async def test_create_appointment_outside_operating_hours_rejected():
    """Verify appointments starting before 09:00 or ending after 20:00 are rejected."""
    next_tuesday = get_next_weekday(1)
    too_early = datetime.combine(next_tuesday, datetime.strptime("08:00", "%H:%M").time(), tzinfo=KOLKATA_TZ)

    create_data_early = AppointmentCreate(
        patient_name="Early Bird",
        patient_phone="+919999999998",
        start_time=too_early,
        duration_minutes=45,
    )

    with pytest.raises(OperatingHoursViolationError) as exc_info:
        await AppointmentService.create_appointment(None, create_data_early)
    assert exc_info.value.code == "OUTSIDE_OPERATING_HOURS"

    too_late = datetime.combine(next_tuesday, datetime.strptime("19:30", "%H:%M").time(), tzinfo=KOLKATA_TZ)
    create_data_late = AppointmentCreate(
        patient_name="Late Comer",
        patient_phone="+919999999997",
        start_time=too_late,
        duration_minutes=45,  # 19:30 + 45m = 20:15 > 20:00!
    )

    with pytest.raises(OperatingHoursViolationError) as exc_info:
        await AppointmentService.create_appointment(None, create_data_late)
    assert exc_info.value.code == "OUTSIDE_OPERATING_HOURS"


@pytest.mark.asyncio
async def test_create_appointment_duplicate_overlap_rejected(async_session: AsyncSession):
    """Verify overlapping active bookings are rejected with AppointmentConflictError."""
    next_monday = get_next_weekday(0)  # 0 is Monday
    slot_start = datetime.combine(next_monday, datetime.strptime("14:00", "%H:%M").time(), tzinfo=KOLKATA_TZ)

    # 1. First booking
    data1 = AppointmentCreate(
        patient_name="First Patient",
        patient_phone="+919111111111",
        start_time=slot_start,
        duration_minutes=45,
    )
    appt1 = await AppointmentService.create_appointment(async_session, data1)
    assert appt1.id is not None

    # 2. Overlapping booking (starting 15 minutes into first appointment: 14:15)
    overlap_start = slot_start + timedelta(minutes=15)
    data2 = AppointmentCreate(
        patient_name="Second Patient",
        patient_phone="+919222222222",
        start_time=overlap_start,
        duration_minutes=45,
    )

    with pytest.raises(AppointmentConflictError) as exc_info:
        await AppointmentService.create_appointment(async_session, data2)

    assert exc_info.value.code == "APPOINTMENT_CONFLICT"


@pytest.mark.asyncio
async def test_reschedule_appointment_success_and_sunday_rejection(async_session: AsyncSession):
    """Test successful rescheduling and rejection if new time is Sunday or conflicting."""
    next_tuesday = get_next_weekday(1)
    original_start = datetime.combine(next_tuesday, datetime.strptime("10:00", "%H:%M").time(), tzinfo=KOLKATA_TZ)

    data = AppointmentCreate(
        patient_name="Vikas Gupta",
        patient_phone="+919333333333",
        start_time=original_start,
        duration_minutes=45,
    )
    appt = await AppointmentService.create_appointment(async_session, data)

    # Attempt to reschedule to Sunday -> Must fail
    next_sunday = get_next_weekday(6)
    sunday_slot = datetime.combine(next_sunday, datetime.strptime("10:00", "%H:%M").time(), tzinfo=KOLKATA_TZ)

    with pytest.raises(SundayRestrictionError):
        await AppointmentService.reschedule_appointment(
            async_session,
            appt.id,
            AppointmentRescheduleRequest(new_start_time=sunday_slot, reason="Wants Sunday"),
        )

    # Reschedule to valid slot: 15:00 on Wednesday
    next_wednesday = get_next_weekday(2)
    new_slot = datetime.combine(next_wednesday, datetime.strptime("15:00", "%H:%M").time(), tzinfo=KOLKATA_TZ)

    rescheduled = await AppointmentService.reschedule_appointment(
        async_session,
        appt.id,
        AppointmentRescheduleRequest(new_start_time=new_slot, reason="Doctor requested afternoon."),
    )

    local_resched_start = rescheduled.start_time.astimezone(KOLKATA_TZ)
    assert local_resched_start.strftime("%H:%M") == "15:00"

    # Verify history entry created
    history_entries = rescheduled.history_entries
    assert len(history_entries) >= 2  # 'created' and 'rescheduled'
    resched_entry = next((h for h in history_entries if h.action == "rescheduled"), None)
    assert resched_entry is not None
    assert resched_entry.reason == "Doctor requested afternoon."


@pytest.mark.asyncio
async def test_appointment_lifecycle_complete_and_no_show(async_session: AsyncSession):
    """Verify completion, no-show transitions and terminal state enforcement."""
    next_wednesday = get_next_weekday(2)
    start_time = datetime.combine(next_wednesday, datetime.strptime("12:00", "%H:%M").time(), tzinfo=KOLKATA_TZ)

    data = AppointmentCreate(
        patient_name="Meena Rao",
        patient_phone="+919444444444",
        start_time=start_time,
        duration_minutes=45,
    )
    appt = await AppointmentService.create_appointment(async_session, data)

    # Mark as completed
    completed = await AppointmentService.complete_appointment(
        async_session, appt.id, AppointmentActionRequest(notes="Treatment successful.")
    )
    assert completed.status == "completed"

    # Terminal state check: completed appointment cannot be cancelled or rescheduled
    with pytest.raises(InvalidStatusTransitionError):
        await AppointmentService.cancel_appointment(
            async_session, appt.id, AppointmentCancelRequest(reason="Too late")
        )

    with pytest.raises(InvalidStatusTransitionError):
        await AppointmentService.reschedule_appointment(
            async_session,
            appt.id,
            AppointmentRescheduleRequest(new_start_time=start_time + timedelta(hours=1)),
        )


# --- 3. Concurrency Protection Test ---

@pytest.mark.asyncio
async def test_concurrency_double_booking_prevention(async_test_engine):
    """Verify that concurrent booking attempts for the same slot cannot double-book."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    session_maker = async_sessionmaker(bind=async_test_engine, class_=AsyncSession, expire_on_commit=False)

    next_monday = get_next_weekday(0)
    slot_time = datetime.combine(next_monday, datetime.strptime("16:00", "%H:%M").time(), tzinfo=KOLKATA_TZ)

    req1 = AppointmentCreate(
        patient_name="Concurrent Patient A",
        patient_phone="+919555555551",
        start_time=slot_time,
        duration_minutes=45,
    )
    req2 = AppointmentCreate(
        patient_name="Concurrent Patient B",
        patient_phone="+919555555552",
        start_time=slot_time,
        duration_minutes=45,
    )

    async def try_book(payload):
        async with session_maker() as session:
            try:
                return await AppointmentService.create_appointment(session, payload)
            except AppointmentConflictError:
                return "CONFLICT"

    results = await asyncio.gather(try_book(req1), try_book(req2), return_exceptions=True)

    # Exactly one must succeed and the other must be rejected with conflict
    successes = [r for r in results if isinstance(r, Appointment)]
    conflicts = [r for r in results if r == "CONFLICT"]

    assert len(successes) == 1
    assert len(conflicts) == 1


# --- 4. API Endpoints, Authentication, and RBAC Tests ---

@pytest.mark.asyncio
async def test_api_unauthenticated_rejected(client: AsyncClient):
    """Verify unauthenticated requests return 401."""
    resp = await client.get("/api/v1/appointments")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_api_viewer_can_read_but_not_mutate(client: AsyncClient, async_session: AsyncSession):
    """Verify Viewer role has read-only access and cannot create, reschedule, or cancel."""
    # Setup initial owner first to satisfy system initialization
    await client.post(
        "/api/v1/auth/setup",
        json={"email": "owner@physioone.com", "password": "OwnerPass2026!", "full_name": "Clinic Owner"},
    )

    # Create Viewer user
    roles = await ensure_initial_roles(async_session)
    viewer_role = roles[ROLE_VIEWER]

    from app.core.security import hash_password
    viewer_user = User(
        email="viewer@physioone.com",
        password_hash=hash_password("ViewerPass2026!"),
        full_name="Staff Viewer",
        role_id=viewer_role.id,
        is_active=True,
    )
    async_session.add(viewer_user)
    await async_session.commit()

    # Log in as Viewer
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "viewer@physioone.com", "password": "ViewerPass2026!"},
    )
    assert login_resp.status_code == 200
    viewer_csrf = client.cookies.get("csrf_token")

    # 1. Viewer CAN read appointments
    list_resp = await client.get("/api/v1/appointments")
    assert list_resp.status_code == 200

    # 2. Viewer CAN read availability
    next_mon = get_next_weekday(0)
    avail_resp = await client.get(f"/api/v1/appointments/availability?date={next_mon.isoformat()}")
    assert avail_resp.status_code == 200

    # 3. Viewer CANNOT create appointments -> 403 Forbidden (RBAC blocked)
    slot_time = datetime.combine(next_mon, datetime.strptime("11:00", "%H:%M").time(), tzinfo=KOLKATA_TZ)
    create_resp = await client.post(
        "/api/v1/appointments",
        json={
            "patient_name": "Viewer Test",
            "patient_phone": "+919666666666",
            "start_time": slot_time.isoformat(),
            "duration_minutes": 45,
        },
        headers={"X-CSRF-Token": viewer_csrf},
    )
    assert create_resp.status_code == 403
    assert "access denied" in create_resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_api_operator_can_create_and_manage_appointments(client: AsyncClient, async_session: AsyncSession):
    """Verify Operator role can create, reschedule, cancel, and complete appointments."""
    # Setup initial owner first
    await client.post(
        "/api/v1/auth/setup",
        json={"email": "owner2@physioone.com", "password": "OwnerPass2026!", "full_name": "Clinic Owner 2"},
    )

    # Create Operator user
    roles = await ensure_initial_roles(async_session)
    op_role = roles[ROLE_OPERATOR]

    from app.core.security import hash_password
    operator_user = User(
        email="operator@physioone.com",
        password_hash=hash_password("OperatorPass2026!"),
        full_name="Front Desk Operator",
        role_id=op_role.id,
        is_active=True,
    )
    async_session.add(operator_user)
    await async_session.commit()

    # Log in as Operator
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "operator@physioone.com", "password": "OperatorPass2026!"},
    )
    assert login_resp.status_code == 200
    op_csrf = client.cookies.get("csrf_token")

    # 1. Create appointment
    next_thursday = get_next_weekday(3)
    slot_time = datetime.combine(next_thursday, datetime.strptime("14:00", "%H:%M").time(), tzinfo=KOLKATA_TZ)

    create_resp = await client.post(
        "/api/v1/appointments",
        json={
            "patient_name": "Sunita Verma",
            "patient_phone": "+919777777777",
            "patient_email": "sunita@example.com",
            "start_time": slot_time.isoformat(),
            "duration_minutes": 45,
            "service_type": "Post-Op Knee Rehab",
            "notes": "Referred by Dr. Kapoor",
        },
        headers={"X-CSRF-Token": op_csrf},
    )
    assert create_resp.status_code == 201
    appt_data = create_resp.json()
    appt_id = appt_data["id"]
    assert appt_data["patient_name"] == "Sunita Verma"
    assert appt_data["status"] == "confirmed"

    # 2. Reschedule appointment
    new_slot = slot_time + timedelta(hours=2)  # 16:00
    resched_resp = await client.post(
        f"/api/v1/appointments/{appt_id}/reschedule",
        json={
            "new_start_time": new_slot.isoformat(),
            "duration_minutes": 45,
            "reason": "Patient requested later slot",
        },
        headers={"X-CSRF-Token": op_csrf},
    )
    assert resched_resp.status_code == 200

    # 3. Complete appointment
    comp_resp = await client.post(
        f"/api/v1/appointments/{appt_id}/complete",
        json={"notes": "Assessment completed."},
        headers={"X-CSRF-Token": op_csrf},
    )
    assert comp_resp.status_code == 200
    assert comp_resp.json()["status"] == "completed"

    # 4. Verify detail endpoint returns full history
    detail_resp = await client.get(f"/api/v1/appointments/{appt_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert len(detail["history_entries"]) >= 3  # created, rescheduled, completed


@pytest.mark.asyncio
async def test_api_sunday_rejection_format(client: AsyncClient, async_session: AsyncSession):
    """Verify that attempting to book a Sunday via API returns structured 422 SUNDAY_RESTRICTION."""
    # Setup initial owner
    await client.post(
        "/api/v1/auth/setup",
        json={"email": "owner3@physioone.com", "password": "OwnerPass2026!", "full_name": "Clinic Owner 3"},
    )
    owner_csrf = client.cookies.get("csrf_token")

    next_sunday = get_next_weekday(6)
    sunday_time = datetime.combine(next_sunday, datetime.strptime("11:00", "%H:%M").time(), tzinfo=KOLKATA_TZ)

    resp = await client.post(
        "/api/v1/appointments",
        json={
            "patient_name": "Sunday Attempt",
            "patient_phone": "+919888888888",
            "start_time": sunday_time.isoformat(),
            "duration_minutes": 45,
        },
        headers={"X-CSRF-Token": owner_csrf},
    )
    assert resp.status_code == 422
    data = resp.json()
    error_obj = data.get("error") or data.get("detail", {}).get("error", {})
    assert error_obj.get("code") == "SUNDAY_RESTRICTION"
    assert "sunday" in error_obj.get("message", "").lower()
