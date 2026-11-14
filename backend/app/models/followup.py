"""Automations, 3-Touch Follow-up Sequences, and Background Task Tracking

Single Organization Edition: Physio One Clinic.
Includes comprehensive scheduled automation rules, jobs, execution logs,
suppression records, templates, settings, and contact cooldowns.
"""
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    String,
    Text,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin


class ScheduledFollowup(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Legacy/compatibility follow-up task tracking for 3-touch sequence."""
    __tablename__ = "scheduled_followups"
    __table_args__ = (
        Index("idx_followup_status_schedule", "status", "scheduled_for"),
        Index("idx_followup_conv_touch", "conversation_id", "touch_stage"),
    )

    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("whatsapp_contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    touch_stage: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 (2h), 2 (24h), 3 (48h)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(30), default="scheduled", nullable=False, index=True
    )  # scheduled, sent, cancelled, suppressed, failed
    suppression_reason: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )  # opt_out, booked_appointment, human_takeover, outside_business_hours
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_message_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("whatsapp_messages.id", ondelete="SET NULL"), nullable=True
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="scheduled_followups")
    contact: Mapped["WhatsAppContact"] = relationship("WhatsAppContact")


class AutomationMessageTemplate(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Reusable approved or internal WhatsApp message templates."""
    __tablename__ = "automation_message_templates"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), default="any", nullable=False)  # meta, ycloud, any
    language: Mapped[str] = mapped_column(String(20), default="en", nullable=False)
    category: Mapped[str] = mapped_column(String(50), default="UTILITY", nullable=False)  # UTILITY, MARKETING, AUTHENTICATION
    approval_status: Mapped[str] = mapped_column(String(30), default="APPROVED", nullable=False)  # APPROVED, PENDING, REJECTED, DRAFT
    body: Mapped[str] = mapped_column(Text, nullable=False)
    variables: Mapped[List[str]] = mapped_column(JSONB, default=list, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    rules: Mapped[List["AutomationRule"]] = relationship("AutomationRule", back_populates="template")


class AutomationRule(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Configurable automation rules for scheduled triggers and actions."""
    __tablename__ = "automation_rules"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    trigger_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # conversation_inactivity, campaign_reengagement, appointment_reminder, appointment_followup, etc.
    condition_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    action_type: Mapped[str] = mapped_column(String(50), default="send_whatsapp_message", nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # MANDATORY DEFAULT: False

    # Enhanced Task 11 Configuration Fields
    automation_type: Mapped[str] = mapped_column(
        String(50), default="appointment_reminder", nullable=False, index=True
    )  # appointment_reminder, appointment_followup, inactivity_followup, noshow_followup, staff_scheduled
    trigger_event: Mapped[str] = mapped_column(
        String(50), default="appointment_confirmed", nullable=False, index=True
    )  # appointment_confirmed, appointment_rescheduled, appointment_cancelled, appointment_completed, appointment_noshow, conversation_inactivity, manual_schedule
    delay_minutes: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )  # negative for before (e.g. -1440 for 24h before), positive for after
    business_hours_only: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    start_hour: Mapped[str] = mapped_column(String(10), default="09:00", nullable=False)
    end_hour: Mapped[str] = mapped_column(String(10), default="20:00", nullable=False)
    permitted_days: Mapped[List[int]] = mapped_column(JSONB, default=[1, 2, 3, 4, 5, 6], nullable=False)  # 1-6 Mon-Sat (Sunday=7 excluded)
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Kolkata", nullable=False)
    template_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("automation_message_templates.id", ondelete="SET NULL"), nullable=True
    )
    fallback_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    provider: Mapped[str] = mapped_column(String(50), default="any", nullable=False)
    max_sends_per_contact: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    cooldown_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    retry_policy: Mapped[dict] = mapped_column(
        JSONB, default=lambda: {"max_retries": 3, "backoff_minutes": 5}, nullable=False
    )
    eligibility_filters: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    template: Mapped[Optional["AutomationMessageTemplate"]] = relationship("AutomationMessageTemplate", back_populates="rules")
    scheduled_jobs: Mapped[List["AutomationScheduledJob"]] = relationship("AutomationScheduledJob", back_populates="rule")


class AutomationScheduledJob(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Durable PostgreSQL store for scheduled automation jobs."""
    __tablename__ = "automation_scheduled_jobs"
    __table_args__ = (
        Index("idx_auto_jobs_status_scheduled", "status", "scheduled_for"),
        Index("idx_auto_jobs_appt_status", "appointment_id", "status"),
        Index("idx_auto_jobs_conv_status", "conversation_id", "status"),
        Index("idx_auto_jobs_contact_type", "contact_id", "automation_type"),
    )

    rule_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("automation_rules.id", ondelete="SET NULL"), nullable=True, index=True
    )
    automation_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("whatsapp_contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conversation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    appointment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    patient_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="SET NULL"), nullable=True, index=True
    )
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(30), default="scheduled", nullable=False, index=True
    )  # scheduled, eligible, queued, processing, sent, delivered, read, failed, cancelled, suppressed, unknown_delivery
    suppression_reason: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    suppression_details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    rendered_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    template_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("automation_message_templates.id", ondelete="SET NULL"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(50), default="any", nullable=False)
    provider_message_id: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(150), unique=True, index=True, nullable=False)
    assigned_staff_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    rule: Mapped[Optional["AutomationRule"]] = relationship("AutomationRule", back_populates="scheduled_jobs")
    contact: Mapped["WhatsAppContact"] = relationship("WhatsAppContact")
    conversation: Mapped[Optional["Conversation"]] = relationship("Conversation")
    appointment: Mapped[Optional["Appointment"]] = relationship("Appointment")
    patient: Mapped[Optional["Patient"]] = relationship("Patient")
    template: Mapped[Optional["AutomationMessageTemplate"]] = relationship("AutomationMessageTemplate")
    execution_logs: Mapped[List["AutomationExecutionLog"]] = relationship(
        "AutomationExecutionLog", back_populates="job", cascade="all, delete-orphan"
    )
    suppression_logs: Mapped[List["AutomationSuppressionLog"]] = relationship(
        "AutomationSuppressionLog", back_populates="job", cascade="all, delete-orphan"
    )


class AutomationExecutionLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Audit log of automation job lifecycle transitions and delivery attempts."""
    __tablename__ = "automation_execution_logs"
    __table_args__ = (
        Index("idx_auto_exec_job", "job_id", "created_at"),
        Index("idx_auto_exec_contact", "contact_id", "created_at"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("automation_scheduled_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("automation_rules.id", ondelete="SET NULL"), nullable=True, index=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("whatsapp_contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    automation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)  # scheduled, evaluated, dispatched, retrying, cancelled, suppressed, failed, delivered
    status_before: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    status_after: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    provider_message_id: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    job: Mapped["AutomationScheduledJob"] = relationship("AutomationScheduledJob", back_populates="execution_logs")
    rule: Mapped[Optional["AutomationRule"]] = relationship("AutomationRule")
    contact: Mapped["WhatsAppContact"] = relationship("WhatsAppContact")


class AutomationSuppressionLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Structured audit trail of suppressed automations with explicit reasons."""
    __tablename__ = "automation_suppression_logs"
    __table_args__ = (
        Index("idx_auto_suppress_contact", "contact_id", "created_at"),
        Index("idx_auto_suppress_reason", "reason", "created_at"),
    )

    job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("automation_scheduled_jobs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    rule_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("automation_rules.id", ondelete="SET NULL"), nullable=True, index=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("whatsapp_contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reason: Mapped[str] = mapped_column(String(100), nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    job: Mapped[Optional["AutomationScheduledJob"]] = relationship("AutomationScheduledJob", back_populates="suppression_logs")
    rule: Mapped[Optional["AutomationRule"]] = relationship("AutomationRule")
    contact: Mapped["WhatsAppContact"] = relationship("WhatsAppContact")


class AutomationSettings(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Global configuration, kill switches, and quiet-hour policies for automations."""
    __tablename__ = "automation_settings"

    outbound_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # MANDATORY DEFAULT: False
    default_timezone: Mapped[str] = mapped_column(String(50), default="Asia/Kolkata", nullable=False)
    quiet_hours_start: Mapped[str] = mapped_column(String(10), default="21:00", nullable=False)
    quiet_hours_end: Mapped[str] = mapped_column(String(10), default="09:00", nullable=False)
    business_hours_start: Mapped[str] = mapped_column(String(10), default="09:00", nullable=False)
    business_hours_end: Mapped[str] = mapped_column(String(10), default="20:00", nullable=False)
    worker_scan_interval_seconds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    default_cooldown_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    emergency_stop: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class AutomationContactCooldown(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Deduplication and cooldown tracking per contact per automation type."""
    __tablename__ = "automation_contact_cooldowns"
    __table_args__ = (
        Index("idx_auto_cooldown_contact_type", "contact_id", "automation_type"),
        Index("idx_auto_cooldown_expires", "expires_at"),
    )

    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("whatsapp_contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    automation_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    last_sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class BackgroundJob(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Durable state tracking for background jobs (Cloud Tasks / Celery)."""
    __tablename__ = "background_jobs"
    __table_args__ = (
        Index("idx_bg_jobs_status_sched", "status", "scheduled_at"),
    )

    job_type: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )  # followup_eval, campaign_dispatch, media_transcription, summary_generation
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), default="queued", nullable=False, index=True
    )  # queued, processing, completed, failed
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# Resolve forward references
from app.models.whatsapp import Conversation, WhatsAppContact, WhatsAppMessage  # noqa: E402, F401
from app.models.patient import Patient, Appointment  # noqa: E402, F401
from app.models.user import User  # noqa: E402, F401
