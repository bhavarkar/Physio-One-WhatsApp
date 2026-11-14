"""AI Agents, Models, Providers, Tool Definitions, Executions, and Usage Tracking

Supports provider-independent LLM gateway with prompt versioning and runtime sessions.
"""
import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    String,
    Text,
    Integer,
    Numeric,
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


class AIProvider(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """LLM Provider Configuration (Muse, OpenAI, Anthropic, Custom)."""
    __tablename__ = "ai_providers"

    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    base_url: Mapped[str] = mapped_column(String(255), nullable=False)
    api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    health_status: Mapped[str] = mapped_column(String(20), default="healthy", nullable=False)
    last_validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_validation_result: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    models: Mapped[List["AIModel"]] = relationship(
        "AIModel", back_populates="provider", cascade="all, delete-orphan"
    )


class AIModel(Base, UUIDPrimaryKeyMixin):
    """Specific model available under a provider."""
    __tablename__ = "ai_models"
    __table_args__ = (
        UniqueConstraint("provider_id", "model_identifier", name="uq_provider_model_identifier"),
    )

    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_providers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model_identifier: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    supports_tools: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    supports_vision: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    max_context_tokens: Mapped[int] = mapped_column(Integer, default=8192, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    provider: Mapped["AIProvider"] = relationship("AIProvider", back_populates="models")


class AIAgent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Configurable AI Agent runtime instance."""
    __tablename__ = "ai_agents"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    primary_model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_models.id", ondelete="RESTRICT"), nullable=False
    )
    fallback_model_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_models.id", ondelete="SET NULL"), nullable=True
    )
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    temperature: Mapped[float] = mapped_column(Numeric(3, 2), default=0.20, nullable=False)
    max_tokens: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    supported_languages: Mapped[list] = mapped_column(
        JSONB, default=lambda: ["en", "hi", "hinglish"], nullable=False
    )
    allowed_tools: Mapped[list] = mapped_column(
        JSONB, default=list, nullable=False
    )
    max_execution_steps: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    execution_timeout_seconds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    context_budget_tokens: Mapped[int] = mapped_column(Integer, default=4000, nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    primary_model: Mapped["AIModel"] = relationship("AIModel", foreign_keys=[primary_model_id])
    fallback_model: Mapped[Optional["AIModel"]] = relationship("AIModel", foreign_keys=[fallback_model_id])
    versions: Mapped[List["AIAgentVersion"]] = relationship(
        "AIAgentVersion", back_populates="agent", cascade="all, delete-orphan"
    )
    executions: Mapped[List["AIToolExecution"]] = relationship("AIToolExecution", back_populates="agent")
    sessions: Mapped[List["AIAgentSession"]] = relationship("AIAgentSession", back_populates="agent")


class AIAgentVersion(Base, UUIDPrimaryKeyMixin):
    """Historical versioning of AI Agent system prompts and configurations."""
    __tablename__ = "ai_agent_versions"
    __table_args__ = (
        UniqueConstraint("agent_id", "version_number", name="uq_agent_version_number"),
    )

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    temperature: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)
    max_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    model_identifier: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    allowed_tools: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    max_execution_steps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    changed_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    change_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    agent: Mapped["AIAgent"] = relationship("AIAgent", back_populates="versions")


class AIAgentSession(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Agent execution session tracking multi-step tool calls, tokens, and status."""
    __tablename__ = "ai_agent_sessions"
    __table_args__ = (
        Index("idx_agent_session_agent_status", "agent_id", "status"),
        Index("idx_agent_session_created", "created_at"),
    )

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_agent_versions.id", ondelete="SET NULL"), nullable=True
    )
    conversation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )  # pending, running, completed, failed, cancelled
    session_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    total_input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_execution_steps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    agent: Mapped["AIAgent"] = relationship("AIAgent", back_populates="sessions")
    agent_version: Mapped[Optional["AIAgentVersion"]] = relationship("AIAgentVersion")
    executions: Mapped[List["AIAgentExecution"]] = relationship(
        "AIAgentExecution", back_populates="session", cascade="all, delete-orphan"
    )
    usage_logs: Mapped[List["LLMUsageLog"]] = relationship(
        "LLMUsageLog", back_populates="session", cascade="all, delete-orphan"
    )


class AIAgentExecution(Base, UUIDPrimaryKeyMixin):
    """Individual step executed during an agent session."""
    __tablename__ = "ai_agent_executions"
    __table_args__ = (
        Index("idx_agent_exec_session_step", "session_id", "step_number"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_agent_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_agents.id", ondelete="SET NULL"), nullable=True
    )
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    prompt_messages: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    response_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tool_calls: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped["AIAgentSession"] = relationship("AIAgentSession", back_populates="executions")


class LLMUsageLog(Base, UUIDPrimaryKeyMixin):
    """Telemetry and token expenditure accounting for every LLM call."""
    __tablename__ = "llm_usage_logs"
    __table_args__ = (
        Index("idx_llm_usage_created", "created_at"),
        Index("idx_llm_usage_provider_model", "provider_name", "model_identifier"),
    )

    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_agent_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_agents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    provider_name: Mapped[str] = mapped_column(String(50), nullable=False)
    model_identifier: Mapped[str] = mapped_column(String(100), nullable=False)
    request_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    response_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost: Mapped[Optional[float]] = mapped_column(Numeric(10, 6), nullable=True)
    is_success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    error_category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    tool_call_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped[Optional["AIAgentSession"]] = relationship("AIAgentSession", back_populates="usage_logs")


class AIToolDefinition(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Tool specification callable by AI agents."""
    __tablename__ = "ai_tool_definitions"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    parameters_schema: Mapped[dict] = mapped_column(JSONB, nullable=False)
    requires_permission: Mapped[str] = mapped_column(String(50), default="appointments:read", nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AIToolExecution(Base, UUIDPrimaryKeyMixin):
    """Execution audit trail of every tool call invoked by AI agents."""
    __tablename__ = "ai_tool_executions"
    __table_args__ = (
        Index("idx_tool_exec_conv_status", "conversation_id", "status"),
        Index("idx_tool_exec_tool_created", "tool_name", "created_at"),
    )

    conversation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_agents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_agent_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    arguments: Mapped[dict] = mapped_column(JSONB, nullable=False)
    result: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # success, failed, rejected_by_rule
    execution_duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    agent: Mapped[Optional["AIAgent"]] = relationship("AIAgent", back_populates="executions")


# Resolve forward references
from app.models.user import User  # noqa: E402, F401
from app.models.whatsapp import Conversation  # noqa: E402, F401
