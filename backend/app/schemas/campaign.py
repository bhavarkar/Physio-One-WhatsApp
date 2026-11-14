"""Pydantic v2 Schemas for Campaigns, Instagram Re-engagement, and YCloud Migration.

Single Organization Edition: Physio One Clinic.
"""
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, HttpUrl, ConfigDict


# ---------------------------------------------------------------------------
# Media Library Schemas
# ---------------------------------------------------------------------------

class CampaignMediaCreate(BaseModel):
    title: str = Field(..., min_length=2, max_length=150)
    caption: Optional[str] = None
    media_type: str = Field("instagram_reel", description="instagram_reel, video, image")
    storage_path: Optional[str] = None
    external_url: Optional[str] = Field(None, description="Validated external Instagram Reel or video URL")
    thumbnail_url: Optional[str] = None
    file_size_bytes: Optional[int] = None
    mime_type: Optional[str] = None
    tags: Optional[List[str]] = Field(default_factory=list)


class CampaignMediaUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=150)
    caption: Optional[str] = None
    external_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    tags: Optional[List[str]] = None
    is_active: Optional[bool] = None
    is_archived: Optional[bool] = None


class CampaignMediaResponse(BaseModel):
    id: uuid.UUID
    title: str
    caption: Optional[str] = None
    media_type: str
    storage_path: Optional[str] = None
    external_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    file_size_bytes: Optional[int] = None
    mime_type: Optional[str] = None
    tags: Optional[List[str]] = None
    is_active: bool
    is_archived: bool
    created_by_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CampaignMediaListResponse(BaseModel):
    items: List[CampaignMediaResponse]
    total: int


# ---------------------------------------------------------------------------
# Campaign Schemas
# ---------------------------------------------------------------------------

class CampaignCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=150)
    campaign_type: str = Field("instagram_reengagement", description="instagram_reengagement, service_announcement, promotional_broadcast, staff_broadcast")
    description: Optional[str] = None
    provider: str = Field("meta", description="meta or ycloud")
    target_audience_rules: Optional[Dict[str, Any]] = Field(
        default_factory=lambda: {
            "workflow": "instagram_reengagement",
            "interaction_window_hours": [24, 48],
            "require_no_future_appointment": True,
            "require_marketing_consent": True,
            "require_no_opt_out": True,
        }
    )
    template_name: Optional[str] = None
    template_id: Optional[uuid.UUID] = None
    custom_message_body: Optional[str] = None
    media_id: Optional[uuid.UUID] = None
    scheduled_for: Optional[datetime] = None
    execution_window_start: str = Field("09:00", pattern=r"^\d{2}:\d{2}$")
    execution_window_end: str = Field("21:00", pattern=r"^\d{2}:\d{2}$")
    rate_limit_per_minute: int = Field(30, ge=1, le=120)
    rate_limit_per_hour: int = Field(1000, ge=1, le=5000)
    batch_size: int = Field(25, ge=1, le=100)
    cooldown_days: int = Field(7, ge=0, le=90)


class CampaignUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=150)
    description: Optional[str] = None
    provider: Optional[str] = None
    target_audience_rules: Optional[Dict[str, Any]] = None
    template_name: Optional[str] = None
    template_id: Optional[uuid.UUID] = None
    custom_message_body: Optional[str] = None
    media_id: Optional[uuid.UUID] = None
    scheduled_for: Optional[datetime] = None
    execution_window_start: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    execution_window_end: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    rate_limit_per_minute: Optional[int] = Field(None, ge=1, le=120)
    rate_limit_per_hour: Optional[int] = Field(None, ge=1, le=5000)
    batch_size: Optional[int] = Field(None, ge=1, le=100)
    cooldown_days: Optional[int] = Field(None, ge=0, le=90)


class CampaignResponse(BaseModel):
    id: uuid.UUID
    title: str
    campaign_type: str
    description: Optional[str] = None
    provider: str
    status: str
    current_version: int
    is_approved: bool
    approved_by_id: Optional[uuid.UUID] = None
    approved_at: Optional[datetime] = None
    approved_version: Optional[int] = None
    approval_notes: Optional[str] = None
    target_audience_rules: Dict[str, Any]
    template_name: Optional[str] = None
    template_id: Optional[uuid.UUID] = None
    custom_message_body: Optional[str] = None
    media_id: Optional[uuid.UUID] = None
    scheduled_for: Optional[datetime] = None
    execution_window_start: str
    execution_window_end: str
    rate_limit_per_minute: int
    rate_limit_per_hour: int
    batch_size: int
    cooldown_days: int
    total_targeted: int
    total_sent: int
    total_delivered: int
    total_read: int
    total_replied: int
    total_converted: int
    total_suppressed: int
    total_failed: int
    created_by_id: Optional[uuid.UUID] = None
    error_message: Optional[str] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CampaignListResponse(BaseModel):
    items: List[CampaignResponse]
    total: int


# ---------------------------------------------------------------------------
# Campaign Versioning & Approval Schemas
# ---------------------------------------------------------------------------

class CampaignVersionResponse(BaseModel):
    id: uuid.UUID
    campaign_id: uuid.UUID
    version_number: int
    snapshot: Dict[str, Any]
    created_by_id: Optional[uuid.UUID] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CampaignApprovalRequest(BaseModel):
    decision: str = Field(..., pattern=r"^(approve|reject)$")
    notes: Optional[str] = None


class CampaignApprovalResponse(BaseModel):
    id: uuid.UUID
    campaign_id: uuid.UUID
    campaign_version: int
    status: str
    reviewed_by_id: uuid.UUID
    decision_at: Optional[datetime] = None
    notes: Optional[str] = None
    snapshot: Dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Audience & Recipient Schemas
# ---------------------------------------------------------------------------

class CampaignAudienceResponse(BaseModel):
    id: uuid.UUID
    campaign_id: uuid.UUID
    name: str
    filter_criteria: Dict[str, Any]
    total_contacts_evaluated: int
    eligible_count: int
    excluded_count: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CampaignRecipientResponse(BaseModel):
    id: uuid.UUID
    campaign_id: uuid.UUID
    contact_id: uuid.UUID
    patient_id: Optional[uuid.UUID] = None
    status: str
    is_eligible: bool
    suppression_reason: Optional[str] = None
    suppression_details: Optional[Dict[str, Any]] = None
    scheduled_for: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    replied_at: Optional[datetime] = None
    converted_at: Optional[datetime] = None
    provider_message_id: Optional[str] = None
    idempotency_key: str
    rendered_message: Optional[str] = None
    delivery_attempts: int
    error_message: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CampaignRecipientListResponse(BaseModel):
    items: List[CampaignRecipientResponse]
    total: int


# ---------------------------------------------------------------------------
# Campaign Preview & Test Schemas
# ---------------------------------------------------------------------------

class CampaignPreviewResponse(BaseModel):
    campaign_id: uuid.UUID
    campaign_title: str
    version: int
    total_evaluated: int
    eligible_count: int
    suppressed_count: int
    suppression_breakdown: Dict[str, int]
    rendered_preview_sample: Optional[str] = None
    template_name: Optional[str] = None
    media_title: Optional[str] = None
    media_url: Optional[str] = None
    sending_window: str
    can_schedule: bool
    blocking_reasons: List[str]


# ---------------------------------------------------------------------------
# CSV Import Schemas
# ---------------------------------------------------------------------------

class CampaignImportResponse(BaseModel):
    total_rows: int
    accepted_count: int
    rejected_count: int
    duplicate_count: int
    created_contacts_count: int
    rejection_samples: List[Dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Analytics Schemas
# ---------------------------------------------------------------------------

class CampaignAnalyticsResponse(BaseModel):
    campaign_id: uuid.UUID
    title: str
    campaign_type: str
    status: str
    current_version: int
    total_targeted: int
    eligible_count: int
    suppressed_count: int
    scheduled_count: int
    sent_count: int
    delivered_count: int
    read_count: int
    replied_count: int
    converted_count: int
    failed_count: int
    delivery_rate_pct: float
    read_rate_pct: float
    reply_rate_pct: float
    conversion_rate_pct: float
    suppression_reasons: Dict[str, int]
    hourly_dispatch_breakdown: Dict[str, int]
    attribution_window_hours: int


# ---------------------------------------------------------------------------
# Legacy Workflow Migration Schemas
# ---------------------------------------------------------------------------

class LegacyMigrationStatusResponse(BaseModel):
    workflow_name: str
    provider: str
    cutover_state: str  # legacy_active, shadow_comparison, migration_ready, new_active, rolled_back
    legacy_trigger_info: Optional[Dict[str, Any]] = None
    shadow_run_results: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None
    activated_by_id: Optional[uuid.UUID] = None
    activated_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LegacyMigrationDryRunResponse(BaseModel):
    workflow_name: str
    evaluation_time: datetime
    legacy_criteria: Dict[str, Any]
    new_engine_criteria: Dict[str, Any]
    total_evaluated: int
    eligible_by_new_engine: int
    suppressed_by_new_engine: int
    suppression_breakdown: Dict[str, int]
    mutual_exclusion_verified: bool
    summary: str


class LegacyMigrationCutoverRequest(BaseModel):
    target_state: str = Field(..., pattern=r"^(legacy_active|shadow_comparison|migration_ready|new_active|rolled_back)$")
    notes: Optional[str] = None
