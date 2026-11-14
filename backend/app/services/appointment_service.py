"""Clinical Appointments and Availability Engine Service

Single Organization Edition: Physio One Clinic.
Implements:
- ACID-safe scheduling and concurrency locking
- Hard Sunday restriction in Asia/Kolkata timezone
- Operating hours boundary enforcement (09:00 - 20:00 IST)
- Overlap detection and conflict rejection
- Strict lifecycle state machine
- Full audit event and rescheduling history logging
"""
import uuid
import asyncio
from datetime import datetime, date, time, timedelta, timezone
from typing import Optional, List, Dict, Any, Tuple
from zoneinfo import ZoneInfo
from sqlalchemy import select, func, and_, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.models.patient import Patient, Appointment, AppointmentHistory
from app.models.user import User, AuditLog
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentUpdate,
    AppointmentRescheduleRequest,
    AppointmentCancelRequest,
    AppointmentActionRequest,
    AppointmentResponse,
    AppointmentHistoryResponse,
    AppointmentListResponse,
    TimeSlot,
    AvailabilityResponse,
    AppointmentStatus,
)


# --- Domain Exceptions ---

class AppointmentServiceError(Exception):
    """Base exception for appointment service errors."""
    def __init__(self, message: str, code: str = "APPOINTMENT_ERROR", details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}


class SundayRestrictionError(AppointmentServiceError):
    """Raised when an operation violates the Physio One Sunday closure policy."""
    def __init__(self, message: str = "Appointments cannot be scheduled on Sundays. Physio One is closed.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="SUNDAY_RESTRICTION", details=details)


class OperatingHoursViolationError(AppointmentServiceError):
    """Raised when an appointment falls outside clinic operating hours."""
    def __init__(self, message: str = "Appointment time falls outside operating hours (09:00 - 20:00 IST).", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="OUTSIDE_OPERATING_HOURS", details=details)


class PastAppointmentError(AppointmentServiceError):
    """Raised when an appointment is requested in the past."""
    def __init__(self, message: str = "Cannot schedule an appointment in the past.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="PAST_APPOINTMENT_ERROR", details=details)


class AppointmentConflictError(AppointmentServiceError):
    """Raised when an overlapping appointment exists for the requested slot."""
    def __init__(self, message: str = "The requested time slot conflicts with an existing appointment.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="APPOINTMENT_CONFLICT", details=details)


class InvalidStatusTransitionError(AppointmentServiceError):
    """Raised when an appointment status transition is prohibited."""
    def __init__(self, message: str = "Invalid appointment status transition.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="INVALID_STATUS_TRANSITION", details=details)


class AppointmentNotFoundError(AppointmentServiceError):
    """Raised when an appointment is not found."""
    def __init__(self, message: str = "Appointment not found.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="APPOINTMENT_NOT_FOUND", details=details)


class PatientNotFoundError(AppointmentServiceError):
    """Raised when a patient record is not found."""
    def __init__(self, message: str = "Patient record not found.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="PATIENT_NOT_FOUND", details=details)


# --- Time & Operating Hours Helpers ---

def get_clinic_tz():
    """Return the configured clinic business timezone with Windows fallback."""
    try:
        return ZoneInfo(settings.CLINIC_TIMEZONE)
    except Exception:
        if settings.CLINIC_TIMEZONE in ("Asia/Kolkata", "Asia/Calcutta", "IST"):
            return timezone(timedelta(hours=5, minutes=30), name="Asia/Kolkata")
        return timezone.utc


def ensure_utc_aware(dt: datetime) -> datetime:
    """Ensure datetime has timezone.utc (especially when reloaded from SQLite)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def normalize_to_clinic_tz(dt: datetime) -> datetime:
    """Ensure datetime is timezone-aware and converted to clinic timezone."""
    clinic_tz = get_clinic_tz()
    aware_dt = ensure_utc_aware(dt)
    return aware_dt.astimezone(clinic_tz)


def normalize_to_utc(dt: datetime) -> datetime:
    """Normalize any datetime to UTC timezone-aware."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=get_clinic_tz())
    return dt.astimezone(timezone.utc)


def is_sunday_in_clinic_tz(dt: datetime) -> bool:
    """Check if the given datetime falls on a Sunday in the clinic timezone."""
    local_dt = normalize_to_clinic_tz(dt)
    return local_dt.weekday() == 6  # 6 is Sunday in Python datetime.weekday()


def parse_time_str(time_str: str) -> time:
    """Parse HH:MM string to time object."""
    parts = [int(p) for p in time_str.split(":")]
    return time(parts[0], parts[1])


def validate_operating_rules(start_dt: datetime, end_dt: datetime, allow_past: bool = False) -> None:
    """Validate clinic operating hours, Sunday restriction, and past time."""
    local_start = normalize_to_clinic_tz(start_dt)
    local_end = normalize_to_clinic_tz(end_dt)

    if local_start >= local_end:
        raise AppointmentServiceError(
            "Appointment start time must be before end time.",
            code="INVALID_TIME_RANGE",
            details={"start_time": local_start.isoformat(), "end_time": local_end.isoformat()},
        )

    # 1. Critical Sunday restriction
    if local_start.weekday() == 6 or local_end.weekday() == 6:
        raise SundayRestrictionError(
            details={
                "requested_date": local_start.date().isoformat(),
                "weekday": "Sunday",
                "clinic_timezone": settings.CLINIC_TIMEZONE,
            }
        )

    # 2. Operating hours check (09:00 - 20:00)
    open_t = parse_time_str(settings.CLINIC_OPEN_TIME)
    close_t = parse_time_str(settings.CLINIC_CLOSE_TIME)

    if local_start.date() != local_end.date():
        raise OperatingHoursViolationError(
            "Appointments cannot span multiple calendar days.",
            details={"start_date": local_start.date().isoformat(), "end_date": local_end.date().isoformat()},
        )

    if local_start.time() < open_t or local_end.time() > close_t:
        raise OperatingHoursViolationError(
            f"Appointment must be within clinic hours ({settings.CLINIC_OPEN_TIME} to {settings.CLINIC_CLOSE_TIME} {settings.CLINIC_TIMEZONE}).",
            details={
                "start_time": local_start.strftime("%H:%M"),
                "end_time": local_end.strftime("%H:%M"),
                "clinic_open": settings.CLINIC_OPEN_TIME,
                "clinic_close": settings.CLINIC_CLOSE_TIME,
            },
        )

    # 3. Prevent past appointments
    if not allow_past:
        now_clinic = datetime.now(get_clinic_tz())
        if local_start < now_clinic:
            raise PastAppointmentError(
                details={"requested_start": local_start.isoformat(), "current_time": now_clinic.isoformat()}
            )


# --- Concurrency & Advisory Lock Helper ---

_booking_locks: Dict[str, asyncio.Lock] = {}
_booking_lock_mutex = asyncio.Lock()


async def get_booking_lock(key: str) -> asyncio.Lock:
    """Get or create an in-process lock for serializing slot bookings."""
    async with _booking_lock_mutex:
        if key not in _booking_locks:
            _booking_locks[key] = asyncio.Lock()
        return _booking_locks[key]


async def acquire_concurrency_lock(db: AsyncSession, practitioner_name: str, booking_date: date) -> None:
    """Acquire a transaction-level advisory lock when running on PostgreSQL."""
    try:
        bind = db.bind
        if bind and bind.dialect.name == "postgresql":
            lock_key = f"physio:appt:{practitioner_name}:{booking_date.isoformat()}"
            await db.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                {"lock_key": lock_key},
            )
    except Exception:
        # Fall back gracefully in SQLite or other non-Postgres environments
        pass


# --- Appointment Service Class ---

class AppointmentService:
    """Authoritative business service for appointments and availability."""

    @staticmethod
    async def get_daily_availability(
        db: AsyncSession,
        target_date: date,
        duration_minutes: int = 45,
        practitioner_name: str = "Dr. Physio One",
    ) -> AvailabilityResponse:
        """Calculate and return available booking slots for a given date."""
        clinic_tz = get_clinic_tz()
        open_t = parse_time_str(settings.CLINIC_OPEN_TIME)
        close_t = parse_time_str(settings.CLINIC_CLOSE_TIME)

        # Check Sunday restriction
        if target_date.weekday() == 6:
            return AvailabilityResponse(
                date=target_date.isoformat(),
                is_open=False,
                operating_hours={"open": settings.CLINIC_OPEN_TIME, "close": settings.CLINIC_CLOSE_TIME},
                timezone=settings.CLINIC_TIMEZONE,
                slots=[],
                message="Physio One is strictly closed on Sundays. No appointments are available.",
            )

        # Retrieve active appointments on this date
        day_start = datetime.combine(target_date, time(0, 0, 0), tzinfo=clinic_tz)
        day_end = datetime.combine(target_date, time(23, 59, 59), tzinfo=clinic_tz)

        day_start_utc = day_start.astimezone(timezone.utc)
        day_end_utc = day_end.astimezone(timezone.utc)

        stmt = (
            select(Appointment)
            .where(
                Appointment.practitioner_name == practitioner_name,
                Appointment.status.not_in(["cancelled", "no_show"]),
                Appointment.start_time < day_end_utc,
                Appointment.end_time > day_start_utc,
            )
            .order_by(Appointment.start_time.asc())
        )
        existing_appointments = (await db.scalars(stmt)).all()

        # Generate candidate slots
        slots: List[TimeSlot] = []
        current_dt = datetime.combine(target_date, open_t, tzinfo=clinic_tz)
        day_close_dt = datetime.combine(target_date, close_t, tzinfo=clinic_tz)
        now_clinic = datetime.now(clinic_tz)

        slot_delta = timedelta(minutes=duration_minutes)

        while current_dt + slot_delta <= day_close_dt:
            slot_start = current_dt
            slot_end = current_dt + slot_delta
            slot_start_utc = slot_start.astimezone(timezone.utc)
            slot_end_utc = slot_end.astimezone(timezone.utc)

            # Check if slot is in the past
            is_past = slot_start < now_clinic

            # Check overlap against existing active bookings
            is_conflict = False
            for appt in existing_appointments:
                appt_start = ensure_utc_aware(appt.start_time)
                appt_end = ensure_utc_aware(appt.end_time)
                if slot_start_utc < appt_end and slot_end_utc > appt_start:
                    is_conflict = True
                    break

            is_available = (not is_past) and (not is_conflict)

            slots.append(
                TimeSlot(
                    start_time=slot_start,
                    end_time=slot_end,
                    is_available=is_available,
                    practitioner_name=practitioner_name,
                )
            )

            # Advance by standard 30-minute interval (or shorter if duration < 30)
            step_minutes = min(30, duration_minutes)
            current_dt += timedelta(minutes=step_minutes)

        return AvailabilityResponse(
            date=target_date.isoformat(),
            is_open=True,
            operating_hours={"open": settings.CLINIC_OPEN_TIME, "close": settings.CLINIC_CLOSE_TIME},
            timezone=settings.CLINIC_TIMEZONE,
            slots=slots,
            message=None,
        )

    @staticmethod
    async def create_appointment(
        db: AsyncSession,
        data: AppointmentCreate,
        current_user: Optional[User] = None,
        actor_type: str = "staff",
        ip_address: Optional[str] = None,
    ) -> Appointment:
        """Create a new appointment with concurrency lock, overlap check, and Sunday validation."""
        start_utc = normalize_to_utc(data.start_time)
        end_utc = start_utc + timedelta(minutes=data.duration_minutes)

        # Validate operating hours, Sunday restriction, and past time
        validate_operating_rules(start_utc, end_utc)

        local_date = normalize_to_clinic_tz(start_utc).date()
        lock_key = f"{data.practitioner_name}:{local_date.isoformat()}"
        lock = await get_booking_lock(lock_key)

        async with lock:
            # 1. Acquire transaction concurrency lock
            await acquire_concurrency_lock(db, data.practitioner_name, local_date)

            # 2. Check for overlapping active appointments
            overlap_stmt = (
                select(Appointment)
                .where(
                    Appointment.practitioner_name == data.practitioner_name,
                    Appointment.status.not_in(["cancelled", "no_show"]),
                    Appointment.start_time < end_utc,
                    Appointment.end_time > start_utc,
                )
            )
            existing = (await db.scalars(overlap_stmt)).first()
            if existing:
                raise AppointmentConflictError(
                    details={
                        "practitioner_name": data.practitioner_name,
                        "conflict_start": existing.start_time.isoformat(),
                        "conflict_end": existing.end_time.isoformat(),
                    }
                )

            # 3. Resolve or create Patient
            patient_id = data.patient_id
            if not patient_id:
                if not data.patient_name or not data.patient_phone:
                    raise AppointmentServiceError(
                        "Either patient_id or both patient_name and patient_phone must be provided.",
                        code="MISSING_PATIENT_INFO",
                    )
                
                # Lookup existing patient by phone
                p_stmt = select(Patient).where(Patient.phone_number == data.patient_phone)
                existing_patient = (await db.scalars(p_stmt)).first()
                if existing_patient:
                    patient_id = existing_patient.id
                else:
                    new_patient = Patient(
                        full_name=data.patient_name,
                        phone_number=data.patient_phone,
                        email=data.patient_email,
                    )
                    db.add(new_patient)
                    await db.flush()
                    patient_id = new_patient.id
            else:
                patient_check = await db.scalar(select(Patient).where(Patient.id == patient_id))
                if not patient_check:
                    raise PatientNotFoundError(details={"patient_id": str(patient_id)})

            # 4. Create Appointment record
            creator_id = current_user.id if current_user else None

            appointment = Appointment(
                patient_id=patient_id,
                practitioner_name=data.practitioner_name,
                service_type=data.service_type,
                start_time=start_utc,
                end_time=end_utc,
                duration_minutes=data.duration_minutes,
                timezone=settings.CLINIC_TIMEZONE,
                status=AppointmentStatus.CONFIRMED.value,
                booked_by=data.booked_by or "dashboard",
                external_appointment_id=data.external_appointment_id,
                created_by_id=creator_id,
                notes=data.notes,
            )
            db.add(appointment)
            await db.flush()

            # 5. Create AppointmentHistory record
            history = AppointmentHistory(
                appointment_id=appointment.id,
                action="created",
                from_status=None,
                to_status=appointment.status,
                to_start_time=start_utc,
                to_end_time=end_utc,
                actor_type=actor_type,
                actor_id=creator_id,
                notes=f"Appointment booked by {data.booked_by}.",
            )
            db.add(history)

            # 6. Create AuditLog record
            audit = AuditLog(
                user_id=creator_id,
                action="appointment.create",
                resource_type="appointment",
                resource_id=str(appointment.id),
                ip_address=ip_address,
                payload={
                    "patient_id": str(patient_id),
                    "practitioner": data.practitioner_name,
                    "start_time": start_utc.isoformat(),
                    "end_time": end_utc.isoformat(),
                    "duration_minutes": data.duration_minutes,
                    "booked_by": data.booked_by,
                },
            )
            db.add(audit)

            try:
                await db.commit()
            except IntegrityError as exc:
                await db.rollback()
                raise AppointmentConflictError(
                    "Appointment booking failed due to a concurrent conflict.",
                    details={"error": str(exc.orig if hasattr(exc, "orig") else exc)},
                )

        # Refresh with eager loads for clean response serialization
        return await AppointmentService.get_appointment(db, appointment.id)

    @staticmethod
    async def get_appointment(db: AsyncSession, appointment_id: uuid.UUID) -> Appointment:
        """Fetch appointment with patient, history, and user relationships."""
        stmt = (
            select(Appointment)
            .options(
                joinedload(Appointment.patient),
                selectinload(Appointment.history_entries).joinedload(AppointmentHistory.actor_user),
                joinedload(Appointment.created_by_user),
                joinedload(Appointment.updated_by_user),
            )
            .where(Appointment.id == appointment_id)
            .execution_options(populate_existing=True)
        )
        appointment = (await db.scalars(stmt)).first()
        if not appointment:
            raise AppointmentNotFoundError(details={"appointment_id": str(appointment_id)})
        
        appointment.start_time = ensure_utc_aware(appointment.start_time)
        appointment.end_time = ensure_utc_aware(appointment.end_time)
        if appointment.cancelled_at:
            appointment.cancelled_at = ensure_utc_aware(appointment.cancelled_at)
        return appointment

    @staticmethod
    async def list_appointments(
        db: AsyncSession,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        status: Optional[str] = None,
        patient_id: Optional[uuid.UUID] = None,
        practitioner_name: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "start_time",
        sort_order: str = "asc",
    ) -> Tuple[List[Appointment], int]:
        """List appointments with comprehensive filtering, search, and pagination."""
        clinic_tz = get_clinic_tz()
        query = select(Appointment).join(Appointment.patient).options(
            joinedload(Appointment.patient),
            selectinload(Appointment.history_entries),
        )

        filters = []
        if date_from:
            from_dt = datetime.combine(date_from, time(0, 0, 0), tzinfo=clinic_tz).astimezone(timezone.utc)
            filters.append(Appointment.start_time >= from_dt)
        if date_to:
            to_dt = datetime.combine(date_to, time(23, 59, 59), tzinfo=clinic_tz).astimezone(timezone.utc)
            filters.append(Appointment.start_time <= to_dt)
        if status:
            filters.append(Appointment.status == status)
        if patient_id:
            filters.append(Appointment.patient_id == patient_id)
        if practitioner_name:
            filters.append(Appointment.practitioner_name == practitioner_name)
        if search:
            s = f"%{search.strip()}%"
            filters.append(
                or_(
                    Patient.full_name.ilike(s),
                    Patient.phone_number.ilike(s),
                    Appointment.service_type.ilike(s),
                    Appointment.notes.ilike(s),
                )
            )

        if filters:
            query = query.where(and_(*filters))

        # Total count
        count_stmt = select(func.count(Appointment.id)).join(Appointment.patient)
        if filters:
            count_stmt = count_stmt.where(and_(*filters))
        total = (await db.scalar(count_stmt)) or 0

        # Sorting
        sort_col = getattr(Appointment, sort_by, Appointment.start_time)
        if sort_order.lower() == "desc":
            query = query.order_by(sort_col.desc())
        else:
            query = query.order_by(sort_col.asc())

        # Pagination
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        appointments = (await db.scalars(query)).all()
        return list(appointments), total

    @staticmethod
    async def reschedule_appointment(
        db: AsyncSession,
        appointment_id: uuid.UUID,
        data: AppointmentRescheduleRequest,
        current_user: Optional[User] = None,
        actor_type: str = "staff",
        ip_address: Optional[str] = None,
    ) -> Appointment:
        """Reschedule an existing active appointment."""
        appointment = await AppointmentService.get_appointment(db, appointment_id)

        # Allowed state check: only scheduled or confirmed can be rescheduled
        if appointment.status in [
            AppointmentStatus.CANCELLED.value,
            AppointmentStatus.COMPLETED.value,
            AppointmentStatus.NO_SHOW.value,
        ]:
            raise InvalidStatusTransitionError(
                f"Cannot reschedule an appointment in '{appointment.status}' status.",
                details={"appointment_id": str(appointment_id), "current_status": appointment.status},
            )

        duration = data.duration_minutes or appointment.duration_minutes
        new_start_utc = normalize_to_utc(data.new_start_time)
        new_end_utc = new_start_utc + timedelta(minutes=duration)

        # Validate operating hours, Sunday restriction, and past time
        validate_operating_rules(new_start_utc, new_end_utc)

        local_date = normalize_to_clinic_tz(new_start_utc).date()
        lock_key = f"{appointment.practitioner_name}:{local_date.isoformat()}"
        lock = await get_booking_lock(lock_key)

        async with lock:
            # 1. Acquire transaction concurrency lock
            await acquire_concurrency_lock(db, appointment.practitioner_name, local_date)

            # 2. Check for overlapping active appointments (excluding current appointment)
            overlap_stmt = (
                select(Appointment)
                .where(
                    Appointment.id != appointment_id,
                    Appointment.practitioner_name == appointment.practitioner_name,
                    Appointment.status.not_in(["cancelled", "no_show"]),
                    Appointment.start_time < new_end_utc,
                    Appointment.end_time > new_start_utc,
                )
            )
            existing = (await db.scalars(overlap_stmt)).first()
            if existing:
                raise AppointmentConflictError(
                    details={
                        "practitioner_name": appointment.practitioner_name,
                        "conflict_start": existing.start_time.isoformat(),
                        "conflict_end": existing.end_time.isoformat(),
                    }
                )

            old_start = appointment.start_time
            old_end = appointment.end_time
            user_id = current_user.id if current_user else None

            # 3. Create AppointmentHistory record
            history = AppointmentHistory(
                appointment_id=appointment.id,
                action="rescheduled",
                from_status=appointment.status,
                to_status=appointment.status,
                from_start_time=old_start,
                from_end_time=old_end,
                to_start_time=new_start_utc,
                to_end_time=new_end_utc,
                reason=data.reason,
                actor_type=actor_type,
                actor_id=user_id,
                notes=data.notes,
            )
            db.add(history)

            # 4. Update Appointment
            appointment.start_time = new_start_utc
            appointment.end_time = new_end_utc
            appointment.duration_minutes = duration
            appointment.updated_by_id = user_id
            if data.notes:
                appointment.notes = f"{appointment.notes}\n{data.notes}" if appointment.notes else data.notes

            # 5. Record AuditLog
            audit = AuditLog(
                user_id=user_id,
                action="appointment.reschedule",
                resource_type="appointment",
                resource_id=str(appointment.id),
                ip_address=ip_address,
                payload={
                    "old_start": old_start.isoformat(),
                    "new_start": new_start_utc.isoformat(),
                    "duration_minutes": duration,
                    "reason": data.reason,
                },
            )
            db.add(audit)

            try:
                await db.commit()
            except IntegrityError as exc:
                await db.rollback()
                raise AppointmentConflictError(
                    "Rescheduling failed due to a concurrent conflict.",
                    details={"error": str(exc.orig if hasattr(exc, "orig") else exc)},
                )

        return await AppointmentService.get_appointment(db, appointment.id)

    @staticmethod
    async def cancel_appointment(
        db: AsyncSession,
        appointment_id: uuid.UUID,
        data: AppointmentCancelRequest,
        current_user: Optional[User] = None,
        actor_type: str = "staff",
        ip_address: Optional[str] = None,
    ) -> Appointment:
        """Cancel an appointment and record cancellation history."""
        appointment = await AppointmentService.get_appointment(db, appointment_id)

        if appointment.status == AppointmentStatus.CANCELLED.value:
            raise InvalidStatusTransitionError(
                "Appointment is already cancelled.",
                details={"appointment_id": str(appointment_id), "current_status": appointment.status},
            )
        if appointment.status == AppointmentStatus.COMPLETED.value:
            raise InvalidStatusTransitionError(
                "Completed appointments cannot be cancelled.",
                details={"appointment_id": str(appointment_id), "current_status": appointment.status},
            )

        old_status = appointment.status
        user_id = current_user.id if current_user else None
        now_utc = datetime.now(timezone.utc)

        # 1. Update Appointment
        appointment.status = AppointmentStatus.CANCELLED.value
        appointment.cancellation_reason = data.reason
        appointment.cancelled_at = now_utc
        appointment.updated_by_id = user_id
        if data.notes:
            appointment.notes = f"{appointment.notes}\nCancellation Note: {data.notes}" if appointment.notes else data.notes

        # 2. Record History
        history = AppointmentHistory(
            appointment_id=appointment.id,
            action="cancelled",
            from_status=old_status,
            to_status=AppointmentStatus.CANCELLED.value,
            from_start_time=appointment.start_time,
            from_end_time=appointment.end_time,
            to_start_time=appointment.start_time,
            to_end_time=appointment.end_time,
            reason=data.reason,
            actor_type=actor_type,
            actor_id=user_id,
            notes=data.notes,
        )
        db.add(history)

        # 3. Record AuditLog
        audit = AuditLog(
            user_id=user_id,
            action="appointment.cancel",
            resource_type="appointment",
            resource_id=str(appointment.id),
            ip_address=ip_address,
            payload={"reason": data.reason, "from_status": old_status},
        )
        db.add(audit)

        await db.commit()
        return await AppointmentService.get_appointment(db, appointment.id)

    @staticmethod
    async def complete_appointment(
        db: AsyncSession,
        appointment_id: uuid.UUID,
        data: AppointmentActionRequest,
        current_user: Optional[User] = None,
        actor_type: str = "staff",
        ip_address: Optional[str] = None,
    ) -> Appointment:
        """Mark an appointment as completed."""
        appointment = await AppointmentService.get_appointment(db, appointment_id)

        if appointment.status in [
            AppointmentStatus.COMPLETED.value,
            AppointmentStatus.CANCELLED.value,
            AppointmentStatus.NO_SHOW.value,
        ]:
            raise InvalidStatusTransitionError(
                f"Cannot mark appointment as completed from status '{appointment.status}'.",
                details={"appointment_id": str(appointment_id), "current_status": appointment.status},
            )

        old_status = appointment.status
        user_id = current_user.id if current_user else None

        appointment.status = AppointmentStatus.COMPLETED.value
        appointment.updated_by_id = user_id
        if data.notes:
            appointment.notes = f"{appointment.notes}\nCompletion Note: {data.notes}" if appointment.notes else data.notes

        history = AppointmentHistory(
            appointment_id=appointment.id,
            action="completed",
            from_status=old_status,
            to_status=AppointmentStatus.COMPLETED.value,
            from_start_time=appointment.start_time,
            from_end_time=appointment.end_time,
            to_start_time=appointment.start_time,
            to_end_time=appointment.end_time,
            actor_type=actor_type,
            actor_id=user_id,
            notes=data.notes,
        )
        db.add(history)

        audit = AuditLog(
            user_id=user_id,
            action="appointment.complete",
            resource_type="appointment",
            resource_id=str(appointment.id),
            ip_address=ip_address,
            payload={"from_status": old_status},
        )
        db.add(audit)

        await db.commit()
        return await AppointmentService.get_appointment(db, appointment.id)

    @staticmethod
    async def mark_no_show(
        db: AsyncSession,
        appointment_id: uuid.UUID,
        data: AppointmentActionRequest,
        current_user: Optional[User] = None,
        actor_type: str = "staff",
        ip_address: Optional[str] = None,
    ) -> Appointment:
        """Mark an appointment as a no-show."""
        appointment = await AppointmentService.get_appointment(db, appointment_id)

        if appointment.status in [
            AppointmentStatus.COMPLETED.value,
            AppointmentStatus.CANCELLED.value,
            AppointmentStatus.NO_SHOW.value,
        ]:
            raise InvalidStatusTransitionError(
                f"Cannot mark appointment as no-show from status '{appointment.status}'.",
                details={"appointment_id": str(appointment_id), "current_status": appointment.status},
            )

        old_status = appointment.status
        user_id = current_user.id if current_user else None

        appointment.status = AppointmentStatus.NO_SHOW.value
        appointment.updated_by_id = user_id
        if data.notes:
            appointment.notes = f"{appointment.notes}\nNo-show Note: {data.notes}" if appointment.notes else data.notes

        history = AppointmentHistory(
            appointment_id=appointment.id,
            action="no_show",
            from_status=old_status,
            to_status=AppointmentStatus.NO_SHOW.value,
            from_start_time=appointment.start_time,
            from_end_time=appointment.end_time,
            to_start_time=appointment.start_time,
            to_end_time=appointment.end_time,
            actor_type=actor_type,
            actor_id=user_id,
            notes=data.notes,
        )
        db.add(history)

        audit = AuditLog(
            user_id=user_id,
            action="appointment.no_show",
            resource_type="appointment",
            resource_id=str(appointment.id),
            ip_address=ip_address,
            payload={"from_status": old_status},
        )
        db.add(audit)

        await db.commit()
        return await AppointmentService.get_appointment(db, appointment.id)

    @staticmethod
    async def update_appointment(
        db: AsyncSession,
        appointment_id: uuid.UUID,
        data: AppointmentUpdate,
        current_user: Optional[User] = None,
        ip_address: Optional[str] = None,
    ) -> Appointment:
        """Update non-temporal appointment details (practitioner, service type, notes)."""
        appointment = await AppointmentService.get_appointment(db, appointment_id)
        user_id = current_user.id if current_user else None

        changes: Dict[str, Any] = {}
        if data.practitioner_name is not None and data.practitioner_name != appointment.practitioner_name:
            changes["practitioner_name"] = data.practitioner_name
            appointment.practitioner_name = data.practitioner_name
        if data.service_type is not None and data.service_type != appointment.service_type:
            changes["service_type"] = data.service_type
            appointment.service_type = data.service_type
        if data.notes is not None:
            changes["notes"] = data.notes
            appointment.notes = data.notes

        if changes:
            appointment.updated_by_id = user_id
            history = AppointmentHistory(
                appointment_id=appointment.id,
                action="updated",
                actor_type="staff",
                actor_id=user_id,
                notes=f"Updated fields: {', '.join(changes.keys())}",
            )
            db.add(history)

            audit = AuditLog(
                user_id=user_id,
                action="appointment.update",
                resource_type="appointment",
                resource_id=str(appointment.id),
                ip_address=ip_address,
                payload=changes,
            )
            db.add(audit)

            await db.commit()

        return await AppointmentService.get_appointment(db, appointment.id)
