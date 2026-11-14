"""Pydantic schemas for AI Providers, Agents, Versions, and Executions.

Single Organization Edition: Physio One Clinic.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
import uuid
from pydantic import BaseModel, Field


# ------------------------------------------------------------------------------
# Models
# ------------------------------------------------------------------------------
class AIModelResponse(BaseModel):
    id: uuid.UUID
    provider_id: uuid.UUID
    provider_name: str
    model_identifier: str
    display_name: str
    supports_tools: bool
    supports_vision: bool
    max_context_tokens: int
    created_at: datetime

    class Config:
        from_attributes = True


# ------------------------------------------------------------------------------
# Providers
# ------------------------------------------------------------------------------
class AIProviderResponse(BaseModel):
    id: uuid.UUID
    name: str
    base_url: str
    has_api_key: bool
    masked_api_key: str
    is_enabled: bool
    config: Optional[Dict[str, Any]] = None
    health_status: str
    last_validated_at: Optional[datetime] = None
    last_validation_result: Optional[Dict[str, Any]] = None
    models: List[AIModelResponse] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AIProviderCreate(BaseModel):
    name: str = Field(min_length=2, max_length=50)
    base_url: str = Field(min_length=5, max_length=255)
    api_key: str = Field(min_length=1)
    is_enabled: bool = True
    config: Optional[Dict[str, Any]] = None


class AIProviderUpdate(BaseModel):
    base_url: Optional[str] = Field(default=None, max_length=255)
    api_key: Optional[str] = None
    is_enabled: Optional[bool] = None
    config: Optional[Dict[str, Any]] = None


class AIProviderTestResponse(BaseModel):
    is_valid: bool
    status: str
    latency_ms: int
    error_message: Optional[str] = None
    detected_models: List[str] = []
    capabilities: Dict[str, bool] = {}
    details: Optional[Dict[str, Any]] = None


# ------------------------------------------------------------------------------
# Agents
# ------------------------------------------------------------------------------
class AIAgentResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    primary_model_id: uuid.UUID
    primary_model_identifier: str
    primary_provider_name: str
    fallback_model_id: Optional[uuid.UUID] = None
    fallback_model_identifier: Optional[str] = None
    fallback_provider_name: Optional[str] = None
    system_prompt: str
    temperature: float
    max_tokens: int
    supported_languages: List[str]
    allowed_tools: List[str]
    max_execution_steps: int
    execution_timeout_seconds: int
    context_budget_tokens: int
    current_version: int
    is_active: bool
    knowledge_base_id: Optional[uuid.UUID] = None
    rag_enabled: bool = False
    rag_similarity_threshold: float = 0.70
    rag_top_k: int = 3
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AIAgentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: Optional[str] = None
    primary_model_id: uuid.UUID
    fallback_model_id: Optional[uuid.UUID] = None
    system_prompt: str = Field(min_length=10)
    temperature: float = Field(default=0.20, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1000, ge=50, le=32000)
    supported_languages: List[str] = ["en", "hi", "hinglish"]
    allowed_tools: List[str] = ["check_availability", "find_patient"]
    max_execution_steps: int = Field(default=5, ge=1, le=20)
    execution_timeout_seconds: int = Field(default=60, ge=5, le=300)
    context_budget_tokens: int = Field(default=4000, ge=500, le=128000)
    is_active: bool = True
    knowledge_base_id: Optional[uuid.UUID] = None
    rag_enabled: bool = False
    rag_similarity_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    rag_top_k: int = Field(default=3, ge=1, le=10)


class AIAgentUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    description: Optional[str] = None
    primary_model_id: Optional[uuid.UUID] = None
    fallback_model_id: Optional[uuid.UUID] = None
    system_prompt: Optional[str] = Field(default=None, min_length=10)
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=50, le=32000)
    allowed_tools: Optional[List[str]] = None
    max_execution_steps: Optional[int] = Field(default=None, ge=1, le=20)
    execution_timeout_seconds: Optional[int] = Field(default=None, ge=5, le=300)
    context_budget_tokens: Optional[int] = Field(default=None, ge=500, le=128000)
    is_active: Optional[bool] = None
    knowledge_base_id: Optional[uuid.UUID] = None
    rag_enabled: Optional[bool] = None
    rag_similarity_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    rag_top_k: Optional[int] = Field(default=None, ge=1, le=10)
    change_summary: Optional[str] = Field(default=None, description="Reason for prompt/configuration update")


class AIAgentVersionResponse(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    version_number: int
    system_prompt: str
    temperature: float
    max_tokens: Optional[int] = None
    model_identifier: Optional[str] = None
    allowed_tools: Optional[List[str]] = None
    max_execution_steps: Optional[int] = None
    changed_by_user_id: Optional[uuid.UUID] = None
    change_summary: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AIAgentTestRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    allow_fallback: bool = False


class AIAgentTestResponse(BaseModel):
    session_id: str
    agent_id: str
    agent_name: str
    status: str
    response_text: str
    steps: List[Dict[str, Any]] = []
    tool_calls: List[Dict[str, Any]] = []
    rag_sources: List[Dict[str, Any]] = []
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    duration_ms: int
    model: str
    provider: str
    error_message: Optional[str] = None


# ------------------------------------------------------------------------------
# Executions and Sessions
# ------------------------------------------------------------------------------
class AgentExecutionStepResponse(BaseModel):
    step_number: int
    status: str
    response_text: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    input_tokens: int
    output_tokens: int
    duration_ms: int
    error_message: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AgentExecutionSessionResponse(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    agent_version_id: Optional[uuid.UUID] = None
    conversation_id: Optional[uuid.UUID] = None
    status: str
    total_input_tokens: int
    total_output_tokens: int
    total_execution_steps: int
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    created_at: datetime
    executions: List[AgentExecutionStepResponse] = []

    class Config:
        from_attributes = True


# ------------------------------------------------------------------------------
# Registered Tools
# ------------------------------------------------------------------------------
class RegisteredToolResponse(BaseModel):
    name: str
    description: str
    parameters_schema: Dict[str, Any]
    requires_permission: str
    is_mutation: bool
    is_idempotent: bool
    timeout_seconds: float
    is_enabled: bool
