"""Clinical Appointments API Endpoints

Single Organization Edition: Physio One Clinic.
RBAC permissions:
- appointments:read (Owner, Admin, Operator, Viewer)
- appointments:create (Owner, Admin, Operator)
- appointments:update (Owner, Admin, Operator)
- appointments:cancel (Owner, Admin, Operator)
- appointments:complete (Owner, Admin, Operator)
- appointments:no_show (Owner, Admin, Operator)
"""
from datetime import date, datetime
from typing import Optional, List
import uuid
from fastapi import APIRouter, Depends, Request, Query, status, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import get_current_user, require_permission
from app.models.user import User
from app.models.patient import Appointment, AppointmentHistory
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentUpdate,
    AppointmentRescheduleRequest,
    AppointmentCancelRequest,
    AppointmentActionRequest,
    AppointmentResponse,
    AppointmentHistoryResponse,
    AppointmentListResponse,
    AvailabilityResponse,
)
from app.services.appointment_service import (
    AppointmentService,
    AppointmentServiceError,
    SundayRestrictionError,
    OperatingHoursViolationError,
    PastAppointmentError,
    AppointmentConflictError,
    InvalidStatusTransitionError,
    AppointmentNotFoundError,
    PatientNotFoundError,
)

router = APIRouter(prefix="/appointments", tags=["Clinical Appointments"])


def serialize_history_entry(entry: AppointmentHistory) -> AppointmentHistoryResponse:
    """Format single history log entry."""
    actor_name = entry.actor_user.full_name if entry.actor_user else None
    return AppointmentHistoryResponse(
        id=entry.id,
        appointment_id=entry.appointment_id,
        action=entry.action,
        from_status=entry.from_status,
        to_status=entry.to_status,
        from_start_time=entry.from_start_time,
        from_end_time=entry.from_end_time,
        to_start_time=entry.to_start_time,
        to_end_time=entry.to_end_time,
        reason=entry.reason,
        actor_type=entry.actor_type,
        actor_id=entry.actor_id,
        actor_name=actor_name,
        notes=entry.notes,
        created_at=entry.created_at,
    )


def serialize_appointment(appt: Appointment) -> AppointmentResponse:
    """Serialize Appointment SQLAlchemy model to typed Pydantic response."""
    patient_name = appt.patient.full_name if appt.patient else None
    patient_phone = appt.patient.phone_number if appt.patient else None
    patient_email = appt.patient.email if appt.patient else None

    history_list = None
    if appt.history_entries is not None:
        history_list = [serialize_history_entry(h) for h in appt.history_entries]

    start_utc = appt.start_time if appt.start_time.tzinfo else appt.start_time.replace(tzinfo=timezone.utc)
    end_utc = appt.end_time if appt.end_time.tzinfo else appt.end_time.replace(tzinfo=timezone.utc)
    cancelled_utc = (
        appt.cancelled_at
        if (appt.cancelled_at is None or appt.cancelled_at.tzinfo)
        else appt.cancelled_at.replace(tzinfo=timezone.utc)
    )

    return AppointmentResponse(
        id=appt.id,
        patient_id=appt.patient_id,
        patient_name=patient_name,
        patient_phone=patient_phone,
        patient_email=patient_email,
        practitioner_name=appt.practitioner_name,
        service_type=appt.service_type,
        start_time=start_utc,
        end_time=end_utc,
        duration_minutes=appt.duration_minutes,
        timezone=appt.timezone,
        status=appt.status,
        booked_by=appt.booked_by,
        external_appointment_id=appt.external_appointment_id,
        rescheduled_from_id=appt.rescheduled_from_id,
        created_by_id=appt.created_by_id,
        updated_by_id=appt.updated_by_id,
        cancellation_reason=appt.cancellation_reason,
        cancelled_at=cancelled_utc,
        notes=appt.notes,
        created_at=appt.created_at,
        updated_at=appt.updated_at,
        history_entries=history_list,
    )


def translate_service_error(exc: AppointmentServiceError) -> HTTPException:
    """Map domain service errors to HTTP exceptions with structured error details."""
    status_code = status.HTTP_400_BAD_REQUEST
    if isinstance(exc, (SundayRestrictionError, OperatingHoursViolationError, PastAppointmentError)):
        status_code = getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422)
    elif isinstance(exc, (AppointmentConflictError, InvalidStatusTransitionError)):
        status_code = status.HTTP_409_CONFLICT
    elif isinstance(exc, (AppointmentNotFoundError, PatientNotFoundError)):
        status_code = status.HTTP_404_NOT_FOUND

    return HTTPException(
        status_code=status_code,
        detail={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
            "message": exc.message,
        },
    )


# --- 1. Availability Query ---

@router.get("/availability", response_model=AvailabilityResponse)
async def get_availability(
    date: date = Query(..., description="Target date in YYYY-MM-DD format"),
    duration_minutes: int = Query(45, ge=15, le=240, description="Duration in minutes"),
    practitioner_name: str = Query("Dr. Physio One", description="Practitioner name"),
    current_user: User = Depends(require_permission("appointments", "read")),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve available appointment slots for a given date in Physio One timezone."""
    try:
        return await AppointmentService.get_daily_availability(
            db,
            target_date=date,
            duration_minutes=duration_minutes,
            practitioner_name=practitioner_name,
        )
    except AppointmentServiceError as exc:
        raise translate_service_error(exc)


# --- 2. List Appointments ---

@router.get("", response_model=AppointmentListResponse)
async def list_appointments(
    date_from: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    status: Optional[str] = Query(None, description="Filter by appointment status"),
    patient_id: Optional[uuid.UUID] = Query(None, description="Filter by patient ID"),
    practitioner_name: Optional[str] = Query(None, description="Filter by practitioner"),
    search: Optional[str] = Query(None, description="Search by patient name, phone, or notes"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("start_time", pattern="^(start_time|created_at|status)$"),
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    current_user: User = Depends(require_permission("appointments", "read")),
    db: AsyncSession = Depends(get_db),
):
    """List clinical appointments with filters and pagination."""
    appts, total = await AppointmentService.list_appointments(
        db,
        date_from=date_from,
        date_to=date_to,
        status=status,
        patient_id=patient_id,
        practitioner_name=practitioner_name,
        search=search,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return AppointmentListResponse(
        appointments=[serialize_appointment(a) for a in appts],
        total=total,
        page=page,
        page_size=page_size,
    )


# --- 3. Create Appointment ---

@router.post("", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
async def create_appointment(
    payload: AppointmentCreate,
    request: Request,
    current_user: User = Depends(require_permission("appointments", "create")),
    db: AsyncSession = Depends(get_db),
):
    """Book a new clinical appointment."""
    client_ip = request.client.host if request.client else None
    try:
        appt = await AppointmentService.create_appointment(
            db,
            data=payload,
            current_user=current_user,
            actor_type="staff",
            ip_address=client_ip,
        )
        return serialize_appointment(appt)
    except AppointmentServiceError as exc:
        raise translate_service_error(exc)


# --- 4. Get Appointment Detail ---

@router.get("/{appointment_id}", response_model=AppointmentResponse)
async def get_appointment(
    appointment_id: uuid.UUID,
    current_user: User = Depends(require_permission("appointments", "read")),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve appointment details including full audit and rescheduling history."""
    try:
        appt = await AppointmentService.get_appointment(db, appointment_id)
        return serialize_appointment(appt)
    except AppointmentServiceError as exc:
        raise translate_service_error(exc)


# --- 5. Update Appointment Details ---

@router.patch("/{appointment_id}", response_model=AppointmentResponse)
async def update_appointment_details(
    appointment_id: uuid.UUID,
    payload: AppointmentUpdate,
    request: Request,
    current_user: User = Depends(require_permission("appointments", "update")),
    db: AsyncSession = Depends(get_db),
):
    """Update non-temporal appointment fields (practitioner, service type, notes)."""
    client_ip = request.client.host if request.client else None
    try:
        appt = await AppointmentService.update_appointment(
            db,
            appointment_id=appointment_id,
            data=payload,
            current_user=current_user,
            ip_address=client_ip,
        )
        return serialize_appointment(appt)
    except AppointmentServiceError as exc:
        raise translate_service_error(exc)


# --- 6. Reschedule Appointment ---

@router.post("/{appointment_id}/reschedule", response_model=AppointmentResponse)
async def reschedule_appointment(
    appointment_id: uuid.UUID,
    payload: AppointmentRescheduleRequest,
    request: Request,
    current_user: User = Depends(require_permission("appointments", "update")),
    db: AsyncSession = Depends(get_db),
):
    """Reschedule an active appointment to a new time slot."""
    client_ip = request.client.host if request.client else None
    try:
        appt = await AppointmentService.reschedule_appointment(
            db,
            appointment_id=appointment_id,
            data=payload,
            current_user=current_user,
            actor_type="staff",
            ip_address=client_ip,
        )
        return serialize_appointment(appt)
    except AppointmentServiceError as exc:
        raise translate_service_error(exc)


# --- 7. Cancel Appointment ---

@router.post("/{appointment_id}/cancel", response_model=AppointmentResponse)
async def cancel_appointment(
    appointment_id: uuid.UUID,
    payload: AppointmentCancelRequest,
    request: Request,
    current_user: User = Depends(require_permission("appointments", "cancel")),
    db: AsyncSession = Depends(get_db),
):
    """Cancel an appointment and record cancellation reason."""
    client_ip = request.client.host if request.client else None
    try:
        appt = await AppointmentService.cancel_appointment(
            db,
            appointment_id=appointment_id,
            data=payload,
            current_user=current_user,
            actor_type="staff",
            ip_address=client_ip,
        )
        return serialize_appointment(appt)
    except AppointmentServiceError as exc:
        raise translate_service_error(exc)


# --- 8. Complete Appointment ---

@router.post("/{appointment_id}/complete", response_model=AppointmentResponse)
async def complete_appointment(
    appointment_id: uuid.UUID,
    payload: AppointmentActionRequest,
    request: Request,
    current_user: User = Depends(require_permission("appointments", "complete")),
    db: AsyncSession = Depends(get_db),
):
    """Mark an appointment as completed."""
    client_ip = request.client.host if request.client else None
    try:
        appt = await AppointmentService.complete_appointment(
            db,
            appointment_id=appointment_id,
            data=payload,
            current_user=current_user,
            actor_type="staff",
            ip_address=client_ip,
        )
        return serialize_appointment(appt)
    except AppointmentServiceError as exc:
        raise translate_service_error(exc)


# --- 9. Mark No-Show ---

@router.post("/{appointment_id}/no-show", response_model=AppointmentResponse)
async def mark_appointment_no_show(
    appointment_id: uuid.UUID,
    payload: AppointmentActionRequest,
    request: Request,
    current_user: User = Depends(require_permission("appointments", "no_show")),
    db: AsyncSession = Depends(get_db),
):
    """Mark an appointment as a no-show."""
    client_ip = request.client.host if request.client else None
    try:
        appt = await AppointmentService.mark_no_show(
            db,
            appointment_id=appointment_id,
            data=payload,
            current_user=current_user,
            actor_type="staff",
            ip_address=client_ip,
        )
        return serialize_appointment(appt)
    except AppointmentServiceError as exc:
        raise translate_service_error(exc)
