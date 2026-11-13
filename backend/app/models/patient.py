"""Patient Records, Consents, and Appointments Models

Single Organization Edition: Physio One Clinic.
"""
import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    String,
    Text,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin


class Patient(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Clinic patient record."""
    __tablename__ = "patients"

    contact_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("whatsapp_contacts.id", ondelete="SET NULL"),
        unique=True,
        nullable=True,
        index=True,
    )
    full_name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    phone_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    gender: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    primary_complaint: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    medical_history: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    emergency_contact: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    contact: Mapped[Optional["WhatsAppContact"]] = relationship(
        "WhatsAppContact", back_populates="patient"
    )
    consents: Mapped[List["PatientConsent"]] = relationship(
        "PatientConsent", back_populates="patient", cascade="all, delete-orphan"
    )
    appointments: Mapped[List["Appointment"]] = relationship(
        "Appointment", back_populates="patient", cascade="all, delete-orphan"
    )


class PatientConsent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Patient consent tracking for communications, marketing and records."""
    __tablename__ = "patient_consents"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    consent_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # whatsapp_communication, marketing_reengagement, treatment_records
    is_granted: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    patient: Mapped["Patient"] = relationship("Patient", back_populates="consents")


class Appointment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Clinic appointment booking record.
    
    Sunday restriction is authoritatively enforced in the Appointment business service,
    and additionally enforced via database check constraint in PostgreSQL migration.
    """
    __tablename__ = "appointments"
    __table_args__ = (
        Index("idx_appointment_time_status", "start_time", "end_time", "status"),
        Index("idx_appointment_patient_status", "patient_id", "status"),
    )

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    practitioner_name: Mapped[str] = mapped_column(
        String(100), default="Dr. Physio One", nullable=False
    )
    service_type: Mapped[str] = mapped_column(
        String(100), default="Initial Physiotherapy Assessment", nullable=False
    )
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Kolkata", nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), default="confirmed", nullable=False, index=True
    )  # pending, confirmed, completed, cancelled, no_show
    booked_by: Mapped[str] = mapped_column(
        String(30), default="deepti_agent", nullable=False
    )  # deepti_agent, staff, patient_online
    external_appointment_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    rescheduled_from_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True
    )
    cancellation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    patient: Mapped["Patient"] = relationship("Patient", back_populates="appointments")
    duration_minutes: Mapped[int] = mapped_column(Integer, default=45, nullable=False)
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    updated_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    history_entries: Mapped[List["AppointmentHistory"]] = relationship(
        "AppointmentHistory",
        back_populates="appointment",
        cascade="all, delete-orphan",
        order_by="AppointmentHistory.created_at.desc()",
    )
    created_by_user: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[created_by_id], lazy="joined"
    )
    updated_by_user: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[updated_by_id], lazy="joined"
    )
    rescheduled_from: Mapped[Optional["Appointment"]] = relationship(
        "Appointment", remote_side="Appointment.id", foreign_keys=[rescheduled_from_id]
    )


class AppointmentHistory(Base, UUIDPrimaryKeyMixin):
    """Audit history and lifecycle event tracking for appointments."""
    __tablename__ = "appointment_history"
    __table_args__ = (
        Index("idx_appointment_history_appt_created", "appointment_id", "created_at"),
    )

    appointment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # created, rescheduled, cancelled, completed, no_show, updated
    from_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    to_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    from_start_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    from_end_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    to_start_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    to_end_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    actor_type: Mapped[str] = mapped_column(
        String(30), default="staff", nullable=False
    )  # staff, patient, whatsapp, system, api
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    appointment: Mapped["Appointment"] = relationship("Appointment", back_populates="history_entries")
    actor_user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[actor_id], lazy="joined")


# Resolve forward references
from app.models.whatsapp import WhatsAppContact  # noqa: E402, F401
from app.models.user import User  # noqa: E402, F401
