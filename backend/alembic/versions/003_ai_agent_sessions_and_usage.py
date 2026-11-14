"""add ai agent sessions, executions, llm usage logs and agent runtime configurations

Revision ID: 003_ai_agent_sessions_and_usage
Revises: 002_appointment_history_and_rules
Create Date: 2026-11-14 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "003_ai_agent_sessions_and_usage"
down_revision: Union[str, None] = "002_appointment_history_and_rules"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Alter ai_providers: add health_status, last_validated_at, last_validation_result
    op.add_column(
        "ai_providers",
        sa.Column(
            "health_status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'healthy'"),
        ),
    )
    op.add_column(
        "ai_providers",
        sa.Column(
            "last_validated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "ai_providers",
        sa.Column(
            "last_validation_result",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )

    # 2. Alter ai_agents: add runtime configuration columns
    op.add_column(
        "ai_agents",
        sa.Column(
            "allowed_tools",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "ai_agents",
        sa.Column(
            "max_execution_steps",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("5"),
        ),
    )
    op.add_column(
        "ai_agents",
        sa.Column(
            "execution_timeout_seconds",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("60"),
        ),
    )
    op.add_column(
        "ai_agents",
        sa.Column(
            "context_budget_tokens",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("4000"),
        ),
    )
    op.add_column(
        "ai_agents",
        sa.Column(
            "current_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )

    # 3. Alter ai_agent_versions: add versioned parameters
    op.add_column(
        "ai_agent_versions",
        sa.Column("allowed_tools", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "ai_agent_versions",
        sa.Column("max_execution_steps", sa.Integer(), nullable=True),
    )
    op.add_column(
        "ai_agent_versions",
        sa.Column("max_tokens", sa.Integer(), nullable=True),
    )
    op.add_column(
        "ai_agent_versions",
        sa.Column("model_identifier", sa.String(length=100), nullable=True),
    )

    # 4. Create ai_agent_sessions table
    op.create_table(
        "ai_agent_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_agent_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("session_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("total_input_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_output_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_execution_steps", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_agent_session_agent_id", "ai_agent_sessions", ["agent_id"])
    op.create_index("idx_agent_session_conversation_id", "ai_agent_sessions", ["conversation_id"])
    op.create_index("idx_agent_session_agent_status", "ai_agent_sessions", ["agent_id", "status"])
    op.create_index("idx_agent_session_created", "ai_agent_sessions", ["created_at"])

    # 5. Create ai_agent_executions table
    op.create_table(
        "ai_agent_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_agent_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("step_number", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("prompt_messages", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column("tool_calls", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_agent_exec_session_id", "ai_agent_executions", ["session_id"])
    op.create_index("idx_agent_exec_session_step", "ai_agent_executions", ["session_id", "step_number"])

    # 6. Create llm_usage_logs table
    op.create_table(
        "llm_usage_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_agent_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("provider_name", sa.String(length=50), nullable=False),
        sa.Column("model_identifier", sa.String(length=100), nullable=False),
        sa.Column("request_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("response_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("estimated_cost", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("is_success", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("error_category", sa.String(length=50), nullable=True),
        sa.Column("tool_call_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_llm_usage_session_id", "llm_usage_logs", ["session_id"])
    op.create_index("idx_llm_usage_agent_id", "llm_usage_logs", ["agent_id"])
    op.create_index("idx_llm_usage_created", "llm_usage_logs", ["created_at"])
    op.create_index("idx_llm_usage_provider_model", "llm_usage_logs", ["provider_name", "model_identifier"])

    # 7. Add session_id to ai_tool_executions
    op.add_column(
        "ai_tool_executions",
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_agent_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("idx_tool_exec_session_id", "ai_tool_executions", ["session_id"])


def downgrade() -> None:
    op.drop_index("idx_tool_exec_session_id", table_name="ai_tool_executions")
    op.drop_column("ai_tool_executions", "session_id")

    op.drop_table("llm_usage_logs")
    op.drop_table("ai_agent_executions")
    op.drop_table("ai_agent_sessions")

    op.drop_column("ai_agent_versions", "model_identifier")
    op.drop_column("ai_agent_versions", "max_tokens")
    op.drop_column("ai_agent_versions", "max_execution_steps")
    op.drop_column("ai_agent_versions", "allowed_tools")

    op.drop_column("ai_agents", "current_version")
    op.drop_column("ai_agents", "context_budget_tokens")
    op.drop_column("ai_agents", "execution_timeout_seconds")
    op.drop_column("ai_agents", "max_execution_steps")
    op.drop_column("ai_agents", "allowed_tools")

    op.drop_column("ai_providers", "last_validation_result")
    op.drop_column("ai_providers", "last_validated_at")
    op.drop_column("ai_providers", "health_status")
