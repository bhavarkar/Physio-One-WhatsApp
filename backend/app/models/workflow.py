"""Appointment AI Workflows, State Machine, Approvals, and Idempotency Models.

Single Organization Edition: Physio One Clinic.
Provides persistent state machine tracking for controlled booking, rescheduling,
and cancellation workflows driven by Deepti AI Receptionist.
"""
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    String,
    Text,
    Boolean,
    Integer,
    DateTime,
    ForeignKey,
    Index,
    func,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin


class AppointmentAIWorkflow(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Persistent state machine workflow tracking an appointment booking, rescheduling, or cancellation lifecycle."""
    __tablename__ = "appointment_ai_workflows"
    __table_args__ = (
        Index("idx_workflow_conv_status", "conversation_id", "status"),
        Index("idx_workflow_contact_status", "contact_id", "status"),
        Index("idx_workflow_patient_status", "patient_id", "status"),
        Index("idx_workflow_status_expiry", "status", "expires_at"),
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("whatsapp_contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    patient_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="SET NULL"), nullable=True, index=True
    )
    appointment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True, index=True
    )

    intent: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # book_appointment | reschedule_appointment | cancel_appointment | check_availability | check_appointment_status | request_human_assistance
    status: Mapped[str] = mapped_column(
        String(40), default="collecting_information", nullable=False, index=True
    )  # collecting_information, checking_availability, awaiting_slot_selection, awaiting_patient_confirmation, awaiting_staff_approval, ready_to_commit, committing, confirmed, cancelled, expired, failed, human_handoff

    workflow_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    selected_slot_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    selected_slot_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    practitioner_name: Mapped[str] = mapped_column(String(100), default="Dr. Physio One", nullable=False)
    service_type: Mapped[str] = mapped_column(
        String(150), default="Initial Physiotherapy Assessment", nullable=False
    )
    duration_minutes: Mapped[int] = mapped_column(Integer, default=45, nullable=False)

    collected_data: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    proposed_changes: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    confirmation_status: Mapped[str] = mapped_column(
        String(30), default="pending", nullable=False
    )  # pending | confirmed | rejected | expired
    confirmation_token: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    confirmation_requested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    approval_status: Mapped[str] = mapped_column(
        String(30), default="not_required", nullable=False
    )  # not_required | pending | approved | rejected | clarification_requested
    approved_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    clarification_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    conversation: Mapped["Conversation"] = relationship("Conversation")
    contact: Mapped["WhatsAppContact"] = relationship("WhatsAppContact")
    patient: Mapped[Optional["Patient"]] = relationship("Patient")
    appointment: Mapped[Optional["Appointment"]] = relationship("Appointment", foreign_keys=[appointment_id])
    approved_by_user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[approved_by_id])

    events: Mapped[List["AppointmentWorkflowEvent"]] = relationship(
        "AppointmentWorkflowEvent", back_populates="workflow", cascade="all, delete-orphan", order_by="AppointmentWorkflowEvent.created_at.asc()"
    )
    confirmations: Mapped[List["AppointmentConfirmation"]] = relationship(
        "AppointmentConfirmation", back_populates="workflow", cascade="all, delete-orphan", order_by="AppointmentConfirmation.created_at.desc()"
    )
    approval_requests: Mapped[List["AppointmentApprovalRequest"]] = relationship(
        "AppointmentApprovalRequest", back_populates="workflow", cascade="all, delete-orphan", order_by="AppointmentApprovalRequest.created_at.desc()"
    )


class AppointmentWorkflowEvent(Base, UUIDPrimaryKeyMixin):
    """Audit event tracking each state transition and action in an appointment workflow."""
    __tablename__ = "appointment_workflow_events"
    __table_args__ = (
        Index("idx_wf_event_workflow_created", "workflow_id", "created_at"),
    )

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointment_ai_workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    to_status: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    actor_type: Mapped[str] = mapped_column(String(30), default="deepti_agent", nullable=False)  # deepti_agent, patient, staff, system
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    payload: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    workflow: Mapped["AppointmentAIWorkflow"] = relationship("AppointmentAIWorkflow", back_populates="events")
    actor_user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[actor_id])


class AppointmentConfirmation(Base, UUIDPrimaryKeyMixin):
    """Record of an explicit appointment confirmation request issued to a patient."""
    __tablename__ = "appointment_confirmations"
    __table_args__ = (
        Index("idx_confirmation_workflow_token", "workflow_id", "confirmation_token"),
    )

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointment_ai_workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    confirmation_token: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    slot_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    slot_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    workflow: Mapped["AppointmentAIWorkflow"] = relationship("AppointmentAIWorkflow", back_populates="confirmations")


class AppointmentApprovalRequest(Base, UUIDPrimaryKeyMixin):
    """Human approval queue record for proposed appointment mutations under Mode B."""
    __tablename__ = "appointment_approval_requests"
    __table_args__ = (
        Index("idx_approval_workflow_status", "workflow_id", "status"),
        Index("idx_approval_status_created", "status", "created_at"),
    )

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointment_ai_workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workflow_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    operation: Mapped[str] = mapped_column(String(40), nullable=False)  # booking | reschedule | cancellation
    status: Mapped[str] = mapped_column(
        String(30), default="pending", nullable=False, index=True
    )  # pending | approved | rejected | clarification_requested | superseded
    proposal_summary: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    staff_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decision_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    workflow: Mapped["AppointmentAIWorkflow"] = relationship("AppointmentAIWorkflow", back_populates="approval_requests")
    staff_user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[staff_id])


class AppointmentOperationIdempotency(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Strict once-and-only-once execution key for appointment mutations."""
    __tablename__ = "appointment_operation_idempotency"

    idempotency_key: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointment_ai_workflows.id", ondelete="CASCADE"), nullable=False
    )
    operation: Mapped[str] = mapped_column(String(40), nullable=False)  # create | reschedule | cancel
    status: Mapped[str] = mapped_column(
        String(30), default="pending", nullable=False
    )  # pending | in_progress | completed | failed
    result: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)


class AppointmentWorkflowSettings(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """System-wide configuration for appointment automation and staff approval policies."""
    __tablename__ = "appointment_workflow_settings"

    policy_mode: Mapped[str] = mapped_column(
        String(40), default="mode_a_read_only", nullable=False
    )  # mode_a_read_only | mode_b_staff_approval | mode_c_controlled_automatic (MANDATORY DEFAULT: mode_a_read_only)
    require_patient_confirmation: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    workflow_expiry_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    confirmation_expiry_minutes: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    max_reschedule_count: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    allow_cancellation_within_hours: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


# Forward references
from app.models.whatsapp import Conversation, WhatsAppContact  # noqa: E402, F401
from app.models.patient import Patient, Appointment  # noqa: E402, F401
from app.models.user import User  # noqa: E402, F401
