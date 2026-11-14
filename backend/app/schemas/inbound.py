"""Pydantic schemas for Inbound AI Orchestration, Live Inbox, and Safety Controls.

Single Organization Edition: Physio One Clinic.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field


class ConversationMessageResponse(BaseModel):
    id: UUID
    provider: str
    direction: str  # inbound | outbound
    message_type: str
    body: Optional[str] = None
    media_url: Optional[str] = None
    media_mime_type: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AIResponseDraftResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    session_id: Optional[UUID] = None
    agent_id: Optional[UUID] = None
    inbound_job_id: Optional[UUID] = None
    aggregated_inbound_text: str
    draft_text: str
    ai_mode: str
    dispatched: bool
    outbound_message_id: Optional[UUID] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationHandoffResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    action: str
    from_state: Optional[str] = None
    to_state: Optional[str] = None
    reason: Optional[str] = None
    actor_type: str
    actor_id: Optional[UUID] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationListItemResponse(BaseModel):
    id: UUID
    contact_id: UUID
    contact_name: Optional[str] = None
    contact_phone: str
    status: str
    is_human_takeover: bool
    ai_paused: bool
    opted_out: bool
    last_message_at: Optional[datetime] = None
    last_message_body: Optional[str] = None
    last_message_direction: Optional[str] = None
    unread_count: int = 0
    pending_draft_count: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationDetailResponse(BaseModel):
    id: UUID
    contact_id: UUID
    contact_name: Optional[str] = None
    contact_phone: str
    status: str
    is_human_takeover: bool
    ai_paused: bool
    opted_out: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    messages: List[ConversationMessageResponse] = Field(default_factory=list)
    drafts: List[AIResponseDraftResponse] = Field(default_factory=list)
    handoffs: List[ConversationHandoffResponse] = Field(default_factory=list)


class ConversationReplyRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    takeover: bool = Field(True, description="Automatically mark conversation as human takeover")


class ConversationActionRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=500)


class AIInboundSettingsResponse(BaseModel):
    id: UUID
    account_id: Optional[UUID] = None
    ai_mode: str  # disabled | shadow | live
    active_agent_id: Optional[UUID] = None
    active_agent_name: Optional[str] = None
    debounce_seconds: int
    max_ai_steps: int
    processing_timeout_seconds: int
    opt_out_keywords: List[str]
    emergency_keywords: List[str]
    is_active: bool
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AIInboundSettingsUpdateRequest(BaseModel):
    ai_mode: Optional[str] = Field(
        None, description="Operating mode: 'disabled' (default), 'shadow' (draft only), or 'live' (autonomous WhatsApp dispatch)"
    )
    active_agent_id: Optional[UUID] = None
    debounce_seconds: Optional[int] = Field(None, ge=1, le=60)
    max_ai_steps: Optional[int] = Field(None, ge=1, le=20)
    processing_timeout_seconds: Optional[int] = Field(None, ge=10, le=300)
    opt_out_keywords: Optional[List[str]] = None
    emergency_keywords: Optional[List[str]] = None
    is_active: Optional[bool] = None
