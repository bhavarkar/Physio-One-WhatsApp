"""Marketing, Instagram Re-engagement & Controlled WhatsApp Campaign Models.

Single Organization Edition: Physio One Clinic.
Supports Instagram reel re-engagement, legacy YCloud workflow migration,
campaign versioning, staff approvals, and delivery analytics.
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
    UniqueConstraint,
    Index,
    func,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin


class CampaignMedia(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Media library asset for Instagram Reels, videos, images, and clinical content."""
    __tablename__ = "campaign_media"
    __table_args__ = (
        Index("idx_campaign_media_type", "media_type", "is_active"),
    )

    title: Mapped[str] = mapped_column(String(150), nullable=False)
    caption: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    media_type: Mapped[str] = mapped_column(String(30), default="instagram_reel", nullable=False)  # instagram_reel, video, image
    storage_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    external_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # e.g. Instagram reel URL
    thumbnail_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tags: Mapped[Optional[List[str]]] = mapped_column(JSONB, default=list, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    creator: Mapped[Optional["User"]] = relationship("User", foreign_keys=[created_by_id])
    campaigns: Mapped[List["Campaign"]] = relationship("Campaign", back_populates="media")


class CampaignTemplate(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Template for broadcast campaigns (e.g. Instagram Reel re-engagement)."""
    __tablename__ = "campaign_templates"

    whatsapp_template_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("whatsapp_templates.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    reel_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    headline: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    body_template: Mapped[str] = mapped_column(Text, nullable=False)
    parameters: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    whatsapp_template: Mapped[Optional["WhatsAppTemplate"]] = relationship("WhatsAppTemplate")
    campaigns: Mapped[List["Campaign"]] = relationship("Campaign", back_populates="template")


class Campaign(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Broadcast campaign instance with scheduling, audience targeting, and approval versioning."""
    __tablename__ = "campaigns"
    __table_args__ = (
        Index("idx_campaign_status_schedule", "status", "scheduled_for"),
        Index("idx_campaign_type_status", "campaign_type", "status"),
    )

    campaign_template_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaign_templates.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    campaign_type: Mapped[str] = mapped_column(
        String(50), default="instagram_reengagement", nullable=False
    )  # instagram_reengagement, service_announcement, promotional_broadcast, staff_broadcast
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    provider: Mapped[str] = mapped_column(String(20), default="meta", nullable=False)  # meta, ycloud
    status: Mapped[str] = mapped_column(
        String(30), default="draft", nullable=False, index=True
    )  # draft, audience_prepared, preview_ready, awaiting_approval, approved, scheduled, running, paused, completed, cancelled, failed

    # Versioning & Approval
    current_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approved_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    approval_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Targeting & Template Rules
    target_audience_rules: Mapped[dict] = mapped_column(
        JSONB,
        default=lambda: {
            "workflow": "instagram_reengagement",
            "interaction_window_hours": [24, 48],
            "require_no_future_appointment": True,
            "require_marketing_consent": True,
            "require_no_opt_out": True,
        },
        nullable=False,
    )
    template_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    template_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("automation_message_templates.id", ondelete="SET NULL"), nullable=True
    )
    custom_message_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    media_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaign_media.id", ondelete="SET NULL"), nullable=True
    )

    # Scheduling & Window (Default 09:00 - 21:00 IST for Instagram re-engagement)
    scheduled_for: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_window_start: Mapped[str] = mapped_column(String(5), default="09:00", nullable=False)
    execution_window_end: Mapped[str] = mapped_column(String(5), default="21:00", nullable=False)

    # Rate Limiting & Throttling
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    rate_limit_per_hour: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    batch_size: Mapped[int] = mapped_column(Integer, default=25, nullable=False)
    cooldown_days: Mapped[int] = mapped_column(Integer, default=7, nullable=False)

    # Aggregate Metric Counters
    total_targeted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_sent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_delivered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_read: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_replied: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_converted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_suppressed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    template: Mapped[Optional["CampaignTemplate"]] = relationship("CampaignTemplate", back_populates="campaigns")
    media: Mapped[Optional["CampaignMedia"]] = relationship("CampaignMedia", back_populates="campaigns")
    creator: Mapped[Optional["User"]] = relationship("User", foreign_keys=[created_by_id])
    approver: Mapped[Optional["User"]] = relationship("User", foreign_keys=[approved_by_id])
    deliveries: Mapped[List["CampaignDelivery"]] = relationship(
        "CampaignDelivery", back_populates="campaign", cascade="all, delete-orphan"
    )
    recipients: Mapped[List["CampaignRecipient"]] = relationship(
        "CampaignRecipient", back_populates="campaign", cascade="all, delete-orphan"
    )
    versions: Mapped[List["CampaignVersion"]] = relationship(
        "CampaignVersion", back_populates="campaign", cascade="all, delete-orphan"
    )
    audiences: Mapped[List["CampaignAudience"]] = relationship(
        "CampaignAudience", back_populates="campaign", cascade="all, delete-orphan"
    )
    approvals: Mapped[List["CampaignApproval"]] = relationship(
        "CampaignApproval", back_populates="campaign", cascade="all, delete-orphan"
    )


class CampaignVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Immutable snapshot of a campaign version for audit and re-approval validation."""
    __tablename__ = "campaign_versions"
    __table_args__ = (
        UniqueConstraint("campaign_id", "version_number", name="uq_campaign_version"),
        Index("idx_campaign_version_lookup", "campaign_id", "version_number"),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="versions")
    creator: Mapped[Optional["User"]] = relationship("User")


class CampaignAudience(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Audience segment definition and evaluation metrics for a campaign."""
    __tablename__ = "campaign_audiences"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    filter_criteria: Mapped[dict] = mapped_column(JSONB, nullable=False)
    total_contacts_evaluated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    eligible_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    excluded_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="audiences")


class CampaignRecipient(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Authoritative per-recipient state, safety checks, and delivery tracking."""
    __tablename__ = "campaign_recipients"
    __table_args__ = (
        UniqueConstraint("campaign_id", "contact_id", name="uq_campaign_recipient_contact"),
        Index("idx_campaign_recipient_status", "status", "scheduled_for"),
        Index("idx_campaign_recipient_provider_msg", "provider_message_id"),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("whatsapp_contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    patient_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(30), default="pending", nullable=False, index=True
    )  # pending, eligible, queued, sending, sent, delivered, read, replied, converted, suppressed, failed, cancelled
    is_eligible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    suppression_reason: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    suppression_details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    scheduled_for: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    replied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    converted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_message_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)
    rendered_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    delivery_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="recipients")
    contact: Mapped["WhatsAppContact"] = relationship("WhatsAppContact")
    patient: Mapped[Optional["Patient"]] = relationship("Patient")
    events: Mapped[List["CampaignDeliveryEvent"]] = relationship(
        "CampaignDeliveryEvent", back_populates="recipient", cascade="all, delete-orphan"
    )


class CampaignApproval(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Staff approval or rejection record for a specific campaign version."""
    __tablename__ = "campaign_approvals"
    __table_args__ = (
        Index("idx_campaign_approval_version", "campaign_id", "campaign_version"),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), default="pending", nullable=False
    )  # pending, approved, rejected, invalidated
    reviewed_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    decision_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)

    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="approvals")
    reviewer: Mapped["User"] = relationship("User")


class CampaignDelivery(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Legacy delivery attempt and response tracking for backwards compatibility."""
    __tablename__ = "campaign_deliveries"
    __table_args__ = (
        UniqueConstraint("campaign_id", "contact_id", name="uq_campaign_recipient"),
        Index("idx_campaign_delivery_status", "status", "sent_at"),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("whatsapp_contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    is_eligible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    ineligibility_reason: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    delivery_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), default="pending", nullable=False, index=True
    )  # pending, sent, delivered, read, replied, failed, ineligible
    error_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="deliveries")
    contact: Mapped["WhatsAppContact"] = relationship("WhatsAppContact")


class CampaignDeliveryEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Detailed delivery event log from WhatsApp providers (queued, sent, delivered, read)."""
    __tablename__ = "campaign_delivery_events"
    __table_args__ = (
        Index("idx_delivery_event_recipient", "recipient_id", "event_type"),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaign_recipients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # queued, dispatched, accepted, delivered, read, failed, unknown_delivery
    provider: Mapped[str] = mapped_column(String(20), default="meta", nullable=False)
    provider_message_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    recipient: Mapped["CampaignRecipient"] = relationship("CampaignRecipient", back_populates="events")


class CampaignConversionEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Conversion tracking linking campaign dispatches to patient booking outcomes."""
    __tablename__ = "campaign_conversion_events"
    __table_args__ = (
        Index("idx_conversion_event_campaign", "campaign_id", "conversion_type"),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaign_recipients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("whatsapp_contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conversion_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # appointment_inquiry, appointment_confirmed, direct_reply, link_click
    appointment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True
    )
    attribution_window_hours: Mapped[int] = mapped_column(Integer, default=72, nullable=False)
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class LegacyWorkflowMigration(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Legacy YCloud/n8n re-engagement workflow migration and cutover state machine."""
    __tablename__ = "legacy_workflow_migrations"

    workflow_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(20), default="ycloud", nullable=False)
    cutover_state: Mapped[str] = mapped_column(
        String(50), default="legacy_active", nullable=False
    )  # legacy_active, shadow_comparison, migration_ready, new_active, rolled_back
    legacy_trigger_info: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    shadow_run_results: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    activated_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    activated_by: Mapped[Optional["User"]] = relationship("User")


# Resolve forward references
from app.models.user import User  # noqa: E402, F401
from app.models.patient import Patient, Appointment  # noqa: E402, F401
from app.models.whatsapp import WhatsAppContact, WhatsAppTemplate  # noqa: E402, F401
from app.models.followup import AutomationMessageTemplate  # noqa: E402, F401
