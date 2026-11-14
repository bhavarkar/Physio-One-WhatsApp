"""Inbound Conversation Orchestration, Debounce Queue, Handoff, and Draft Models.

Single Organization Edition: Physio One Clinic.
Provides durable PostgreSQL queue tracking for inbound messages, debouncing bursts,
storing AI drafts (in shadow mode), auditing human takeovers, and outbound idempotency.
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
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin


class InboundProcessingJob(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Durable queue job for aggregating and processing inbound WhatsApp messages."""
    __tablename__ = "inbound_processing_jobs"
    __table_args__ = (
        Index("idx_inbound_jobs_status_scheduled", "status", "scheduled_at"),
        Index("idx_inbound_jobs_conversation", "conversation_id", "status"),
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("whatsapp_contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), default="pending", nullable=False, index=True
    )  # pending, debouncing, processing, completed, failed, cancelled
    aggregated_message_ids: Mapped[List[str]] = mapped_column(JSONB, default=list, nullable=False)
    aggregated_text: Mapped[str] = mapped_column(Text, nullable=False)
    debounce_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    locked_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    conversation: Mapped["Conversation"] = relationship("Conversation")
    contact: Mapped["WhatsAppContact"] = relationship("WhatsAppContact")


class AIInboundSettings(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Configuration for inbound WhatsApp AI orchestration and safety controls."""
    __tablename__ = "ai_inbound_settings"

    account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("whatsapp_accounts.id", ondelete="CASCADE"), nullable=True, unique=True
    )
    ai_mode: Mapped[str] = mapped_column(
        String(20), default="disabled", nullable=False
    )  # disabled | shadow | live (MANDATORY DEFAULT: disabled)
    active_agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_agents.id", ondelete="SET NULL"), nullable=True
    )
    debounce_seconds: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    max_ai_steps: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    processing_timeout_seconds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    opt_out_keywords: Mapped[List[str]] = mapped_column(
        JSONB,
        default=lambda: ["stop", "unsubscribe", "cancel messages", "optout", "opt out"],
        nullable=False,
    )
    emergency_keywords: Mapped[List[str]] = mapped_column(
        JSONB,
        default=lambda: ["emergency", "ambulance", "severe pain", "bleeding", "chest pain", "unconscious"],
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    account: Mapped[Optional["WhatsAppAccount"]] = relationship("WhatsAppAccount")
    agent: Mapped[Optional["AIAgent"]] = relationship("AIAgent")


class ConversationHandoff(Base, UUIDPrimaryKeyMixin):
    """Immutable audit trail of staff takeovers, AI pauses, and patient opt-outs."""
    __tablename__ = "conversation_handoffs"
    __table_args__ = (
        Index("idx_handoff_conversation_created", "conversation_id", "created_at"),
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(
        String(30), nullable=False, index=True
    )  # human_takeover | human_assigned | ai_paused | ai_resumed | opt_out_triggered | emergency_detected
    from_state: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    to_state: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    actor_type: Mapped[str] = mapped_column(String(20), default="staff", nullable=False)  # staff | patient | system
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    conversation: Mapped["Conversation"] = relationship("Conversation")
    actor: Mapped[Optional["User"]] = relationship("User")


class AIResponseDraft(Base, UUIDPrimaryKeyMixin):
    """AI generated response drafts persisted during shadow/disabled mode or pre-dispatch."""
    __tablename__ = "ai_response_drafts"
    __table_args__ = (
        Index("idx_draft_conversation_created", "conversation_id", "created_at"),
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_agent_sessions.id", ondelete="SET NULL"), nullable=True
    )
    agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_agents.id", ondelete="SET NULL"), nullable=True
    )
    inbound_job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inbound_processing_jobs.id", ondelete="SET NULL"), nullable=True
    )
    aggregated_inbound_text: Mapped[str] = mapped_column(Text, nullable=False)
    draft_text: Mapped[str] = mapped_column(Text, nullable=False)
    ai_mode: Mapped[str] = mapped_column(String(20), default="shadow", nullable=False)  # disabled | shadow | live
    dispatched: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    outbound_message_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("whatsapp_messages.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    conversation: Mapped["Conversation"] = relationship("Conversation")
    session: Mapped[Optional["AIAgentSession"]] = relationship("AIAgentSession")
    agent: Mapped[Optional["AIAgent"]] = relationship("AIAgent")
    outbound_message: Mapped[Optional["WhatsAppMessage"]] = relationship("WhatsAppMessage")


class OutboundIdempotencyKey(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Guarantees strict once-and-only-once dispatch of outbound WhatsApp replies."""
    __tablename__ = "outbound_idempotency_keys"

    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("whatsapp_messages.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )  # pending | in_flight | sent | failed
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_message_id: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)


# Forward references resolved in app.models
from app.models.whatsapp import Conversation, WhatsAppContact, WhatsAppMessage, WhatsAppAccount  # noqa: E402, F401
from app.models.ai import AIAgent, AIAgentSession  # noqa: E402, F401
from app.models.user import User  # noqa: E402, F401
