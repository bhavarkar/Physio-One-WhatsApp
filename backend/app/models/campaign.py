"""Marketing & Instagram Re-engagement Campaign Models

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
    UniqueConstraint,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin


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
    """Broadcast campaign instance with scheduling and audience targeting."""
    __tablename__ = "campaigns"
    __table_args__ = (
        Index("idx_campaign_status_schedule", "status", "scheduled_for"),
    )

    campaign_template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaign_templates.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    provider: Mapped[str] = mapped_column(String(20), default="meta", nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), default="draft", nullable=False, index=True
    )  # draft, scheduled, active, paused, completed, cancelled
    target_audience_rules: Mapped[dict] = mapped_column(
        JSONB,
        default=lambda: {
            "workflow": "instagram_reengagement",
            "interaction_window_hours": [24, 48],
            "require_no_future_appointment": True,
            "require_no_opt_out": True,
        },
        nullable=False,
    )
    scheduled_for: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_window_start: Mapped[str] = mapped_column(String(5), default="09:00", nullable=False)
    execution_window_end: Mapped[str] = mapped_column(String(5), default="21:00", nullable=False)
    total_targeted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_sent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_delivered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_replied: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    template: Mapped["CampaignTemplate"] = relationship("CampaignTemplate", back_populates="campaigns")
    deliveries: Mapped[List["CampaignDelivery"]] = relationship(
        "CampaignDelivery", back_populates="campaign", cascade="all, delete-orphan"
    )


class CampaignDelivery(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Delivery attempt and response tracking for an individual recipient."""
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


# Resolve forward references
from app.models.whatsapp import WhatsAppContact, WhatsAppTemplate  # noqa: E402, F401
