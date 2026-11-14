"""Pydantic Schemas for Appointments and Availability Engine

Single Organization Edition: Physio One Clinic.
"""
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
import uuid
from pydantic import BaseModel, Field, ConfigDict, field_validator


class AppointmentStatus(str, Enum):
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class TimeSlot(BaseModel):
    """Individual availability slot."""
    start_time: datetime
    end_time: datetime
    is_available: bool
    practitioner_name: str = "Dr. Physio One"


class AvailabilityResponse(BaseModel):
    """Daily availability query response."""
    date: str
    is_open: bool
    operating_hours: Dict[str, str] = Field(
        default_factory=lambda: {"open": "09:00", "close": "20:00"}
    )
    timezone: str = "Asia/Kolkata"
    slots: List[TimeSlot] = Field(default_factory=list)
    message: Optional[str] = None


class AppointmentHistoryResponse(BaseModel):
    """Audit and lifecycle change event representation."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    appointment_id: uuid.UUID
    action: str
    from_status: Optional[str] = None
    to_status: Optional[str] = None
    from_start_time: Optional[datetime] = None
    from_end_time: Optional[datetime] = None
    to_start_time: Optional[datetime] = None
    to_end_time: Optional[datetime] = None
    reason: Optional[str] = None
    actor_type: str = "staff"
    actor_id: Optional[uuid.UUID] = None
    actor_name: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime


class AppointmentBase(BaseModel):
    """Common appointment properties."""
    practitioner_name: str = Field(default="Dr. Physio One", max_length=100)
    service_type: str = Field(
        default="Initial Physiotherapy Assessment", max_length=100
    )
    notes: Optional[str] = None


class AppointmentCreate(AppointmentBase):
    """Request payload to create a new appointment."""
    patient_id: Optional[uuid.UUID] = None
    patient_name: Optional[str] = Field(None, min_length=1, max_length=150)
    patient_phone: Optional[str] = Field(None, min_length=5, max_length=30)
    patient_email: Optional[str] = Field(None, max_length=255)
    
    start_time: datetime
    duration_minutes: int = Field(default=45, ge=15, le=240)
    booked_by: str = Field(default="dashboard", max_length=30)
    external_appointment_id: Optional[str] = Field(None, max_length=100)

    @field_validator("patient_phone")
    @classmethod
    def clean_phone(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        cleaned = "".join(ch for ch in v if ch.isalnum() or ch == "+")
        return cleaned


class AppointmentUpdate(BaseModel):
    """Request payload to update non-temporal details."""
    practitioner_name: Optional[str] = Field(None, max_length=100)
    service_type: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = None


class AppointmentRescheduleRequest(BaseModel):
    """Request payload to reschedule an existing appointment."""
    new_start_time: datetime
    duration_minutes: Optional[int] = Field(None, ge=15, le=240)
    reason: Optional[str] = Field(None, max_length=500)
    notes: Optional[str] = None


class AppointmentCancelRequest(BaseModel):
    """Request payload to cancel an appointment."""
    reason: str = Field(..., min_length=2, max_length=500)
    notes: Optional[str] = None


class AppointmentActionRequest(BaseModel):
    """Request payload for completion or no-show actions."""
    notes: Optional[str] = None


class AppointmentResponse(AppointmentBase):
    """Comprehensive appointment representation."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    patient_name: Optional[str] = None
    patient_phone: Optional[str] = None
    patient_email: Optional[str] = None
    start_time: datetime
    end_time: datetime
    duration_minutes: int
    timezone: str
    status: str
    booked_by: str
    external_appointment_id: Optional[str] = None
    rescheduled_from_id: Optional[uuid.UUID] = None
    created_by_id: Optional[uuid.UUID] = None
    updated_by_id: Optional[uuid.UUID] = None
    cancellation_reason: Optional[str] = None
    cancelled_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    history_entries: Optional[List[AppointmentHistoryResponse]] = None


class AppointmentListResponse(BaseModel):
    """Paginated appointment list response."""
    appointments: List[AppointmentResponse]
    total: int
    page: int
    page_size: int

