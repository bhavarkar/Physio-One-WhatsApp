"""WhatsApp Messaging, Accounts, Webhooks, and Ingress Models

Supports both Meta WhatsApp Cloud API and YCloud providers.
"""
import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Index,
    func,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin


class WhatsAppAccount(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """WhatsApp Provider Account configuration (Meta or YCloud)."""
    __tablename__ = "whatsapp_accounts"

    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="meta", index=True)
    account_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone_number_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    business_account_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    display_phone_number: Mapped[str] = mapped_column(String(30), nullable=False)
    webhook_verify_token: Mapped[str] = mapped_column(String(255), nullable=False)
    access_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    secret_key_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    provider_config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class WhatsAppContact(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Contact record identified by phone number."""
    __tablename__ = "whatsapp_contacts"

    wa_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    profile_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    opted_out_marketing: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    opted_out_all: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_active_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    conversations: Mapped[List["Conversation"]] = relationship(
        "Conversation", back_populates="contact", cascade="all, delete-orphan"
    )
    messages: Mapped[List["WhatsAppMessage"]] = relationship("WhatsAppMessage", back_populates="contact")
    patient: Mapped[Optional["Patient"]] = relationship("Patient", back_populates="contact", uselist=False)


class Conversation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Active or historical conversation thread with a contact."""
    __tablename__ = "conversations"

    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("whatsapp_contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(30), default="open", nullable=False, index=True)
    is_human_takeover: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    takeover_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    takeover_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ai_paused: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ai_paused_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    active_agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    contact: Mapped["WhatsAppContact"] = relationship("WhatsAppContact", back_populates="conversations")
    messages: Mapped[List["WhatsAppMessage"]] = relationship(
        "WhatsAppMessage", back_populates="conversation", cascade="all, delete-orphan"
    )
    summaries: Mapped[List["ConversationSummary"]] = relationship(
        "ConversationSummary", back_populates="conversation", cascade="all, delete-orphan"
    )
    scheduled_followups: Mapped[List["ScheduledFollowup"]] = relationship(
        "ScheduledFollowup", back_populates="conversation"
    )


class WhatsAppMessage(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Individual inbound or outbound WhatsApp message."""
    __tablename__ = "whatsapp_messages"
    __table_args__ = (
        UniqueConstraint("provider", "provider_message_id", name="uq_provider_message_id"),
        Index("idx_message_conversation_created", "conversation_id", "created_at"),
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("whatsapp_contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(20), default="meta", nullable=False, index=True)
    provider_message_id: Mapped[str] = mapped_column(String(150), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False, index=True)  # inbound | outbound
    message_type: Mapped[str] = mapped_column(
        String(20), default="text", nullable=False
    )  # text, image, audio, video, document, interactive, template
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    media_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    media_mime_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    voice_transcription: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="received", nullable=False, index=True
    )  # received, sent, delivered, read, failed
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")
    contact: Mapped["WhatsAppContact"] = relationship("WhatsAppContact", back_populates="messages")


class WebhookEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Deduplication and audit log of incoming webhooks from Meta/YCloud."""
    __tablename__ = "webhook_events"
    __table_args__ = (
        UniqueConstraint("provider", "event_id", name="uq_provider_event_id"),
        Index("idx_webhook_events_status", "status", "created_at"),
    )

    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    event_id: Mapped[str] = mapped_column(String(150), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="received", nullable=False
    )  # received, processed, failed, ignored
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class MessageDebounce(Base, UUIDPrimaryKeyMixin):
    """Fast message debouncing persistence."""
    __tablename__ = "message_debounce"
    __table_args__ = (
        Index("idx_debounce_lookup", "contact_wa_id", "message_hash", "expires_at"),
    )

    contact_wa_id: Mapped[str] = mapped_column(String(50), nullable=False)
    message_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WhatsAppTemplate(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """WhatsApp Message Templates for marketing and utility messages."""
    __tablename__ = "whatsapp_templates"
    __table_args__ = (
        UniqueConstraint("provider", "name", "language", name="uq_template_provider_name_lang"),
    )

    provider: Mapped[str] = mapped_column(String(50), default="meta", nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)  # MARKETING, UTILITY, AUTHENTICATION
    language: Mapped[str] = mapped_column(String(10), default="en", nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)  # APPROVED, PENDING, REJECTED
    header_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    body_template: Mapped[str] = mapped_column(Text, nullable=False)
    variables: Mapped[Optional[list]] = mapped_column(JSONB, default=list, nullable=True)


# Forward references resolved in app.models
from app.models.patient import Patient  # noqa: E402, F401
from app.models.memory import ConversationSummary  # noqa: E402, F401
from app.models.followup import ScheduledFollowup  # noqa: E402, F401
