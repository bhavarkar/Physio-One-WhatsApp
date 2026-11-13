"""Automations, 3-Touch Follow-up Sequences, and Background Task Tracking

Single Organization Edition: Physio One Clinic.
"""
import uuid
from datetime import datetime
from typing import Optional
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
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin


class ScheduledFollowup(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Durable follow-up task tracking for 3-touch sequence."""
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


class AutomationRule(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Configurable automation rules for triggers and actions."""
    __tablename__ = "automation_rules"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    trigger_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # conversation_inactivity, campaign_reengagement, appointment_reminder
    condition_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


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
