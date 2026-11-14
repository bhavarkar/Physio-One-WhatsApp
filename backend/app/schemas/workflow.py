"""Appointment AI Workflow Schemas and Validation Models.

Single Organization Edition: Physio One Clinic.
Defines structured schemas for intent detection, state machine lifecycle,
human approvals, automation policy settings, and workflow audit events.
"""
from enum import Enum
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class WorkflowIntent(str, Enum):
    """Supported appointment-related intents."""
    BOOK_APPOINTMENT = "book_appointment"
    CHECK_AVAILABILITY = "check_availability"
    RESCHEDULE_APPOINTMENT = "reschedule_appointment"
    CANCEL_APPOINTMENT = "cancel_appointment"
    CHECK_APPOINTMENT_STATUS = "check_appointment_status"
    REQUEST_HUMAN_ASSISTANCE = "request_human_assistance"


class WorkflowState(str, Enum):
    """Persistent state machine lifecycle states."""
    COLLECTING_INFORMATION = "collecting_information"
    CHECKING_AVAILABILITY = "checking_availability"
    AWAITING_SLOT_SELECTION = "awaiting_slot_selection"
    AWAITING_PATIENT_CONFIRMATION = "awaiting_patient_confirmation"
    AWAITING_STAFF_APPROVAL = "awaiting_staff_approval"
    READY_TO_COMMIT = "ready_to_commit"
    COMMITTING = "committing"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    FAILED = "failed"
    HUMAN_HANDOFF = "human_handoff"


class AutomationPolicyMode(str, Enum):
    """Clinic automation policy modes."""
    MODE_A_READ_ONLY = "mode_a_read_only"
    MODE_B_STAFF_APPROVAL = "mode_b_staff_approval"
    MODE_C_CONTROLLED_AUTOMATIC = "mode_c_controlled_automatic"


class ExtractedAppointmentIntent(BaseModel):
    """Structured extraction result from patient message."""
    intent: WorkflowIntent
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    target_date: Optional[str] = None  # YYYY-MM-DD
    preferred_time: Optional[str] = None  # e.g., "5:00 PM"
    service_type: Optional[str] = None
    practitioner_name: Optional[str] = None
    patient_name: Optional[str] = None
    patient_phone: Optional[str] = None
    appointment_id: Optional[str] = None
    cancellation_reason: Optional[str] = None
    reschedule_reason: Optional[str] = None
    is_explicit_confirmation: Optional[bool] = None  # True if "yes/confirm", False if "no/cancel"
    raw_entities: Dict[str, Any] = Field(default_factory=dict)


class WorkflowEventResponse(BaseModel):
    """Audit event for workflow timeline."""
    id: uuid.UUID
    workflow_id: uuid.UUID
    from_status: Optional[str] = None
    to_status: Optional[str] = None
    event_type: str
    actor_type: str
    actor_id: Optional[uuid.UUID] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AppointmentConfirmationResponse(BaseModel):
    """Confirmation request record."""
    id: uuid.UUID
    workflow_id: uuid.UUID
    confirmation_token: str
    summary_text: str
    slot_start: datetime
    slot_end: datetime
    is_confirmed: bool
    confirmed_at: Optional[datetime] = None
    expires_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class AppointmentApprovalRequestResponse(BaseModel):
    """Approval queue item response."""
    id: uuid.UUID
    workflow_id: uuid.UUID
    workflow_version: int
    operation: str
    status: str
    proposal_summary: Dict[str, Any] = Field(default_factory=dict)
    staff_id: Optional[uuid.UUID] = None
    decision_at: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AppointmentWorkflowResponse(BaseModel):
    """Detailed appointment workflow representation."""
    id: uuid.UUID
    conversation_id: uuid.UUID
    contact_id: uuid.UUID
    patient_id: Optional[uuid.UUID] = None
    patient_name: Optional[str] = None
    patient_phone: Optional[str] = None
    appointment_id: Optional[uuid.UUID] = None
    intent: str
    status: str
    workflow_version: int
    selected_slot_start: Optional[datetime] = None
    selected_slot_end: Optional[datetime] = None
    practitioner_name: str
    service_type: str
    duration_minutes: int
    collected_data: Dict[str, Any] = Field(default_factory=dict)
    proposed_changes: Dict[str, Any] = Field(default_factory=dict)
    confirmation_status: str
    confirmation_token: Optional[str] = None
    confirmation_requested_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None
    approval_status: str
    approved_by_id: Optional[uuid.UUID] = None
    approved_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    clarification_notes: Optional[str] = None
    expires_at: Optional[datetime] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    events: List[WorkflowEventResponse] = Field(default_factory=list)
    confirmations: List[AppointmentConfirmationResponse] = Field(default_factory=list)
    approval_requests: List[AppointmentApprovalRequestResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True


class AppointmentWorkflowListResponse(BaseModel):
    """Paginated list of appointment workflows."""
    items: List[AppointmentWorkflowResponse]
    total: int
    page: int
    page_size: int


class ApprovalActionRequest(BaseModel):
    """Staff action on a pending workflow approval request."""
    reason: Optional[str] = None
    notes: Optional[str] = None


class AppointmentWorkflowSettingsResponse(BaseModel):
    """System-wide workflow automation policy settings."""
    id: uuid.UUID
    policy_mode: str
    require_patient_confirmation: bool
    workflow_expiry_minutes: int
    confirmation_expiry_minutes: int
    max_reschedule_count: int
    allow_cancellation_within_hours: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AppointmentWorkflowSettingsUpdate(BaseModel):
    """Partial update schema for workflow automation policy settings."""
    policy_mode: Optional[AutomationPolicyMode] = None
    require_patient_confirmation: Optional[bool] = None
    workflow_expiry_minutes: Optional[int] = Field(default=None, ge=5, le=1440)
    confirmation_expiry_minutes: Optional[int] = Field(default=None, ge=1, le=120)
    max_reschedule_count: Optional[int] = Field(default=None, ge=1, le=10)
    allow_cancellation_within_hours: Optional[int] = Field(default=None, ge=0, le=72)
