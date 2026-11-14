"""add inbound processing queue, ai inbound settings, conversation handoffs, ai response drafts, and outbound idempotency

Revision ID: 005_inbound_ai_orchestration
Revises: 004_knowledge_base_pgvector_rag
Create Date: 2026-11-14 21:25:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "005_inbound_ai_orchestration"
down_revision: Union[str, None] = "004_knowledge_base_pgvector_rag"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_type = postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36)
    json_type = postgresql.JSONB if is_postgres else sa.JSON
    now_fn = sa.text("now()") if is_postgres else sa.text("CURRENT_TIMESTAMP")
    bool_true = sa.text("true") if is_postgres else sa.text("1")
    bool_false = sa.text("false") if is_postgres else sa.text("0")

    # 1. inbound_processing_jobs
    op.create_table(
        "inbound_processing_jobs",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column(
            "conversation_id",
            uuid_type,
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "contact_id",
            uuid_type,
            sa.ForeignKey("whatsapp_contacts.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("aggregated_message_ids", json_type, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("aggregated_text", sa.Text(), nullable=False),
        sa.Column("debounce_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("locked_by", sa.String(100), nullable=True),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now_fn, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now_fn, nullable=False),
    )
    op.create_index(
        "idx_inbound_jobs_status_scheduled",
        "inbound_processing_jobs",
        ["status", "scheduled_at"],
    )
    op.create_index(
        "idx_inbound_jobs_conversation",
        "inbound_processing_jobs",
        ["conversation_id", "status"],
    )

    # 2. ai_inbound_settings
    op.create_table(
        "ai_inbound_settings",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column(
            "account_id",
            uuid_type,
            sa.ForeignKey("whatsapp_accounts.id", ondelete="CASCADE"),
            nullable=True,
            unique=True,
        ),
        sa.Column("ai_mode", sa.String(20), nullable=False, server_default=sa.text("'disabled'")),
        sa.Column(
            "active_agent_id",
            uuid_type,
            sa.ForeignKey("ai_agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("debounce_seconds", sa.Integer(), nullable=False, server_default=sa.text("5")),
        sa.Column("max_ai_steps", sa.Integer(), nullable=False, server_default=sa.text("5")),
        sa.Column("processing_timeout_seconds", sa.Integer(), nullable=False, server_default=sa.text("60")),
        sa.Column(
            "opt_out_keywords",
            json_type,
            nullable=False,
            server_default=sa.text(
                '\'["stop", "unsubscribe", "cancel messages", "optout", "opt out"]\''
            ),
        ),
        sa.Column(
            "emergency_keywords",
            json_type,
            nullable=False,
            server_default=sa.text(
                '\'["emergency", "ambulance", "severe pain", "bleeding", "chest pain", "unconscious"]\''
            ),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=bool_true),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now_fn, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now_fn, nullable=False),
    )

    # 3. conversation_handoffs
    op.create_table(
        "conversation_handoffs",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column(
            "conversation_id",
            uuid_type,
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("action", sa.String(30), nullable=False, index=True),
        sa.Column("from_state", sa.String(30), nullable=True),
        sa.Column("to_state", sa.String(30), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("actor_type", sa.String(20), nullable=False, server_default=sa.text("'staff'")),
        sa.Column(
            "actor_id",
            uuid_type,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now_fn, nullable=False),
    )
    op.create_index(
        "idx_handoff_conversation_created",
        "conversation_handoffs",
        ["conversation_id", "created_at"],
    )

    # 4. ai_response_drafts
    op.create_table(
        "ai_response_drafts",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column(
            "conversation_id",
            uuid_type,
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "session_id",
            uuid_type,
            sa.ForeignKey("ai_agent_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "agent_id",
            uuid_type,
            sa.ForeignKey("ai_agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "inbound_job_id",
            uuid_type,
            sa.ForeignKey("inbound_processing_jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("aggregated_inbound_text", sa.Text(), nullable=False),
        sa.Column("draft_text", sa.Text(), nullable=False),
        sa.Column("ai_mode", sa.String(20), nullable=False, server_default=sa.text("'shadow'")),
        sa.Column("dispatched", sa.Boolean(), nullable=False, server_default=bool_false),
        sa.Column(
            "outbound_message_id",
            uuid_type,
            sa.ForeignKey("whatsapp_messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now_fn, nullable=False),
    )
    op.create_index(
        "idx_draft_conversation_created",
        "ai_response_drafts",
        ["conversation_id", "created_at"],
    )

    # 5. outbound_idempotency_keys
    op.create_table(
        "outbound_idempotency_keys",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("idempotency_key", sa.String(120), nullable=False, unique=True, index=True),
        sa.Column(
            "conversation_id",
            uuid_type,
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            uuid_type,
            sa.ForeignKey("whatsapp_messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("provider_message_id", sa.String(150), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now_fn, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now_fn, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("outbound_idempotency_keys")
    op.drop_table("ai_response_drafts")
    op.drop_table("conversation_handoffs")
    op.drop_table("ai_inbound_settings")
    op.drop_table("inbound_processing_jobs")
