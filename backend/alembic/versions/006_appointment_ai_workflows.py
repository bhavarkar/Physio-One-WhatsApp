"""add appointment ai workflows, state machine, confirmations, approvals, and idempotency

Revision ID: 006_appointment_ai_workflows
Revises: 005_inbound_ai_orchestration
Create Date: 2026-11-14 22:15:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "006_appointment_ai_workflows"
down_revision: Union[str, None] = "005_inbound_ai_orchestration"
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

    # 1. appointment_ai_workflows
    op.create_table(
        "appointment_ai_workflows",
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
        sa.Column(
            "patient_id",
            uuid_type,
            sa.ForeignKey("patients.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "appointment_id",
            uuid_type,
            sa.ForeignKey("appointments.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("intent", sa.String(50), nullable=False, index=True),
        sa.Column("status", sa.String(40), nullable=False, server_default=sa.text("'collecting_information'"), index=True),
        sa.Column("workflow_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("selected_slot_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("selected_slot_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("practitioner_name", sa.String(100), nullable=False, server_default=sa.text("'Dr. Physio One'")),
        sa.Column("service_type", sa.String(150), nullable=False, server_default=sa.text("'Initial Physiotherapy Assessment'")),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default=sa.text("45")),
        sa.Column("collected_data", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("proposed_changes", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("confirmation_status", sa.String(30), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("confirmation_token", sa.String(64), nullable=True, index=True),
        sa.Column("confirmation_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approval_status", sa.String(30), nullable=False, server_default=sa.text("'not_required'")),
        sa.Column(
            "approved_by_id",
            uuid_type,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("clarification_notes", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now_fn, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now_fn, nullable=False),
    )
    op.create_index(
        "idx_workflow_conv_status",
        "appointment_ai_workflows",
        ["conversation_id", "status"],
    )
    op.create_index(
        "idx_workflow_contact_status",
        "appointment_ai_workflows",
        ["contact_id", "status"],
    )
    op.create_index(
        "idx_workflow_patient_status",
        "appointment_ai_workflows",
        ["patient_id", "status"],
    )
    op.create_index(
        "idx_workflow_status_expiry",
        "appointment_ai_workflows",
        ["status", "expires_at"],
    )

    # 2. appointment_workflow_events
    op.create_table(
        "appointment_workflow_events",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column(
            "workflow_id",
            uuid_type,
            sa.ForeignKey("appointment_ai_workflows.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("from_status", sa.String(40), nullable=True),
        sa.Column("to_status", sa.String(40), nullable=True),
        sa.Column("event_type", sa.String(50), nullable=False, index=True),
        sa.Column("actor_type", sa.String(30), nullable=False, server_default=sa.text("'deepti_agent'")),
        sa.Column(
            "actor_id",
            uuid_type,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("payload", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now_fn, nullable=False, index=True),
    )
    op.create_index(
        "idx_wf_event_workflow_created",
        "appointment_workflow_events",
        ["workflow_id", "created_at"],
    )

    # 3. appointment_confirmations
    op.create_table(
        "appointment_confirmations",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column(
            "workflow_id",
            uuid_type,
            sa.ForeignKey("appointment_ai_workflows.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("confirmation_token", sa.String(64), nullable=False, index=True),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("slot_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("slot_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_confirmed", sa.Boolean(), nullable=False, server_default=bool_false),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now_fn, nullable=False),
    )
    op.create_index(
        "idx_confirmation_workflow_token",
        "appointment_confirmations",
        ["workflow_id", "confirmation_token"],
    )

    # 4. appointment_approval_requests
    op.create_table(
        "appointment_approval_requests",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column(
            "workflow_id",
            uuid_type,
            sa.ForeignKey("appointment_ai_workflows.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("workflow_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("operation", sa.String(40), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default=sa.text("'pending'"), index=True),
        sa.Column("proposal_summary", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column(
            "staff_id",
            uuid_type,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("decision_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now_fn, nullable=False, index=True),
    )
    op.create_index(
        "idx_approval_workflow_status",
        "appointment_approval_requests",
        ["workflow_id", "status"],
    )
    op.create_index(
        "idx_approval_status_created",
        "appointment_approval_requests",
        ["status", "created_at"],
    )

    # 5. appointment_operation_idempotency
    op.create_table(
        "appointment_operation_idempotency",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("idempotency_key", sa.String(150), nullable=False, unique=True, index=True),
        sa.Column(
            "workflow_id",
            uuid_type,
            sa.ForeignKey("appointment_ai_workflows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("operation", sa.String(40), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("result", json_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now_fn, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now_fn, nullable=False),
    )

    # 6. appointment_workflow_settings
    op.create_table(
        "appointment_workflow_settings",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("policy_mode", sa.String(40), nullable=False, server_default=sa.text("'mode_a_read_only'")),
        sa.Column("require_patient_confirmation", sa.Boolean(), nullable=False, server_default=bool_true),
        sa.Column("workflow_expiry_minutes", sa.Integer(), nullable=False, server_default=sa.text("30")),
        sa.Column("confirmation_expiry_minutes", sa.Integer(), nullable=False, server_default=sa.text("15")),
        sa.Column("max_reschedule_count", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("allow_cancellation_within_hours", sa.Integer(), nullable=False, server_default=sa.text("2")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=bool_true),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now_fn, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now_fn, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("appointment_workflow_settings")
    op.drop_table("appointment_operation_idempotency")
    op.drop_table("appointment_approval_requests")
    op.drop_table("appointment_confirmations")
    op.drop_table("appointment_workflow_events")
    op.drop_table("appointment_ai_workflows")
