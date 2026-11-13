"""AI Agents, Models, Providers, Tool Definitions and Executions

Supports provider-independent LLM gateway with prompt versioning.
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
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    primary_model: Mapped["AIModel"] = relationship("AIModel", foreign_keys=[primary_model_id])
    fallback_model: Mapped[Optional["AIModel"]] = relationship("AIModel", foreign_keys=[fallback_model_id])
    versions: Mapped[List["AIAgentVersion"]] = relationship(
        "AIAgentVersion", back_populates="agent", cascade="all, delete-orphan"
    )
    executions: Mapped[List["AIToolExecution"]] = relationship("AIToolExecution", back_populates="agent")


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
    changed_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    change_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    agent: Mapped["AIAgent"] = relationship("AIAgent", back_populates="versions")


class AIToolDefinition(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Tool specification callable by AI agents."""
    __tablename__ = "ai_tool_definitions"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    parameters_schema: Mapped[dict] = mapped_column(JSONB, nullable=False)
    requires_permission: Mapped[str] = mapped_column(String(50), default="appointments:create", nullable=False)
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
