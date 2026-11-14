"""Pydantic Schemas for Scheduled Automations, Rules, Templates, Jobs, and Settings.

Single Organization Edition: Physio One Clinic.
"""
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


# ---------------------------------------------------------------------------
# Message Templates
# ---------------------------------------------------------------------------

class AutomationMessageTemplateBase(BaseModel):
    name: str = Field(..., max_length=100)
    provider: str = Field("any", max_length=50)
    language: str = Field("en", max_length=20)
    category: str = Field("UTILITY", max_length=50)
    approval_status: str = Field("APPROVED", max_length=30)
    body: str
    variables: List[str] = Field(default_factory=list)
    version: int = 1
    is_active: bool = True


class AutomationMessageTemplateCreate(AutomationMessageTemplateBase):
    pass


class AutomationMessageTemplateUpdate(BaseModel):
    name: Optional[str] = None
    provider: Optional[str] = None
    language: Optional[str] = None
    category: Optional[str] = None
    approval_status: Optional[str] = None
    body: Optional[str] = None
    variables: Optional[List[str]] = None
    version: Optional[int] = None
    is_active: Optional[bool] = None


class AutomationMessageTemplateResponse(AutomationMessageTemplateBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AutomationMessageTemplateListResponse(BaseModel):
    items: List[AutomationMessageTemplateResponse]
    total: int


# ---------------------------------------------------------------------------
# Automation Rules
# ---------------------------------------------------------------------------

class AutomationRuleBase(BaseModel):
    name: str = Field(..., max_length=100)
    trigger_type: str = Field("appointment_reminder", max_length=50)
    condition_json: Dict[str, Any] = Field(default_factory=dict)
    action_type: str = Field("send_whatsapp_message", max_length=50)
    is_enabled: bool = False  # MANDATORY DEFAULT: False
    automation_type: str = Field("appointment_reminder", max_length=50)
    trigger_event: str = Field("appointment_confirmed", max_length=50)
    delay_minutes: int = 0
    business_hours_only: bool = True
    start_hour: str = Field("09:00", max_length=10)
    end_hour: str = Field("20:00", max_length=10)
    permitted_days: List[int] = Field(default_factory=lambda: [1, 2, 3, 4, 5, 6])
    timezone: str = Field("Asia/Kolkata", max_length=50)
    template_id: Optional[uuid.UUID] = None
    fallback_body: Optional[str] = None
    provider: str = Field("any", max_length=50)
    max_sends_per_contact: int = 1
    cooldown_hours: int = 24
    retry_policy: Dict[str, Any] = Field(default_factory=lambda: {"max_retries": 3, "backoff_minutes": 5})
    eligibility_filters: Dict[str, Any] = Field(default_factory=dict)


class AutomationRuleCreate(AutomationRuleBase):
    pass


class AutomationRuleUpdate(BaseModel):
    name: Optional[str] = None
    trigger_type: Optional[str] = None
    condition_json: Optional[Dict[str, Any]] = None
    action_type: Optional[str] = None
    is_enabled: Optional[bool] = None
    automation_type: Optional[str] = None
    trigger_event: Optional[str] = None
    delay_minutes: Optional[int] = None
    business_hours_only: Optional[bool] = None
    start_hour: Optional[str] = None
    end_hour: Optional[str] = None
    permitted_days: Optional[List[int]] = None
    timezone: Optional[str] = None
    template_id: Optional[uuid.UUID] = None
    fallback_body: Optional[str] = None
    provider: Optional[str] = None
    max_sends_per_contact: Optional[int] = None
    cooldown_hours: Optional[int] = None
    retry_policy: Optional[Dict[str, Any]] = None
    eligibility_filters: Optional[Dict[str, Any]] = None


class AutomationRuleResponse(AutomationRuleBase):
    id: uuid.UUID
    created_by_user_id: Optional[uuid.UUID] = None
    updated_by_user_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime
    template_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AutomationRuleListResponse(BaseModel):
    items: List[AutomationRuleResponse]
    total: int


# ---------------------------------------------------------------------------
# Scheduled Jobs
# ---------------------------------------------------------------------------

class AutomationScheduledJobCreate(BaseModel):
    """Staff-controlled individual scheduled follow-up."""
    contact_id: uuid.UUID
    conversation_id: Optional[uuid.UUID] = None
    appointment_id: Optional[uuid.UUID] = None
    scheduled_for: datetime
    message_text: Optional[str] = None
    template_id: Optional[uuid.UUID] = None
    reason: str = Field(..., max_length=200)
    assigned_staff_id: Optional[uuid.UUID] = None
    provider: str = "any"


class AutomationScheduledJobResponse(BaseModel):
    id: uuid.UUID
    rule_id: Optional[uuid.UUID] = None
    rule_name: Optional[str] = None
    automation_type: str
    contact_id: uuid.UUID
    contact_phone: Optional[str] = None
    contact_name: Optional[str] = None
    conversation_id: Optional[uuid.UUID] = None
    appointment_id: Optional[uuid.UUID] = None
    patient_id: Optional[uuid.UUID] = None
    scheduled_for: datetime
    status: str
    suppression_reason: Optional[str] = None
    suppression_details: Optional[Dict[str, Any]] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    rendered_message: Optional[str] = None
    template_id: Optional[uuid.UUID] = None
    template_name: Optional[str] = None
    provider: str
    provider_message_id: Optional[str] = None
    attempt_count: int
    max_attempts: int
    last_attempt_at: Optional[datetime] = None
    next_retry_at: Optional[datetime] = None
    idempotency_key: str
    assigned_staff_id: Optional[uuid.UUID] = None
    created_by_user_id: Optional[uuid.UUID] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AutomationScheduledJobListResponse(BaseModel):
    items: List[AutomationScheduledJobResponse]
    total: int


class JobCancelRequest(BaseModel):
    reason: str = Field("Cancelled by user", max_length=200)


class JobRetryRequest(BaseModel):
    reset_attempts: bool = True


# ---------------------------------------------------------------------------
# Execution and Suppression Logs
# ---------------------------------------------------------------------------

class AutomationExecutionLogResponse(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    rule_id: Optional[uuid.UUID] = None
    contact_id: uuid.UUID
    automation_type: str
    action: str
    status_before: Optional[str] = None
    status_after: Optional[str] = None
    provider: Optional[str] = None
    provider_message_id: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AutomationExecutionLogListResponse(BaseModel):
    items: List[AutomationExecutionLogResponse]
    total: int


class AutomationSuppressionLogResponse(BaseModel):
    id: uuid.UUID
    job_id: Optional[uuid.UUID] = None
    rule_id: Optional[uuid.UUID] = None
    contact_id: uuid.UUID
    reason: str
    details: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AutomationSuppressionLogListResponse(BaseModel):
    items: List[AutomationSuppressionLogResponse]
    total: int


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

class AutomationSettingsResponse(BaseModel):
    id: uuid.UUID
    outbound_enabled: bool  # MANDATORY DEFAULT: False
    default_timezone: str
    quiet_hours_start: str
    quiet_hours_end: str
    business_hours_start: str
    business_hours_end: str
    worker_scan_interval_seconds: int
    max_retries: int
    default_cooldown_hours: int
    rate_limit_per_minute: int
    emergency_stop: bool
    updated_by_user_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AutomationSettingsUpdate(BaseModel):
    outbound_enabled: Optional[bool] = None
    default_timezone: Optional[str] = None
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None
    business_hours_start: Optional[str] = None
    business_hours_end: Optional[str] = None
    worker_scan_interval_seconds: Optional[int] = None
    max_retries: Optional[int] = None
    default_cooldown_hours: Optional[int] = None
    rate_limit_per_minute: Optional[int] = None
    emergency_stop: Optional[bool] = None


# ---------------------------------------------------------------------------
# Testing & Shadow Preview
# ---------------------------------------------------------------------------

class AutomationTestRequest(BaseModel):
    rule_id: Optional[uuid.UUID] = None
    template_id: Optional[uuid.UUID] = None
    inline_body: Optional[str] = None
    contact_id: uuid.UUID
    appointment_id: Optional[uuid.UUID] = None
    mock_variables: Optional[Dict[str, str]] = None


class AutomationTestResponse(BaseModel):
    rendered_message: str
    eligible: bool
    suppression_reasons: List[str] = Field(default_factory=list)
    service_window_open: bool
    requires_approved_template: bool
    in_business_hours: bool
    in_quiet_hours: bool
    next_eligible_send_time: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Worker Response
# ---------------------------------------------------------------------------

class AutomationWorkerRunResponse(BaseModel):
    processed_count: int
    dispatched_count: int
    suppressed_count: int
    rescheduled_count: int
    failed_count: int
    recovered_leases_count: int
