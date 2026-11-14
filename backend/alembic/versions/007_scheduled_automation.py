"""scheduled automations, appointment reminders, patient follow-ups, and durable scheduling

Revision ID: 007_scheduled_automation
Revises: 006_appointment_ai_workflows
Create Date: 2026-11-14 23:15:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "007_scheduled_automation"
down_revision: Union[str, None] = "006_appointment_ai_workflows"
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

    # 1. Create automation_message_templates table
    op.create_table(
        "automation_message_templates",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("name", sa.String(100), unique=True, nullable=False, index=True),
        sa.Column("provider", sa.String(50), nullable=False, server_default=sa.text("'any'")),
        sa.Column("language", sa.String(20), nullable=False, server_default=sa.text("'en'")),
        sa.Column("category", sa.String(50), nullable=False, server_default=sa.text("'UTILITY'")),
        sa.Column("approval_status", sa.String(30), nullable=False, server_default=sa.text("'APPROVED'")),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("variables", json_type, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=bool_true),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now_fn),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=now_fn),
    )

    # 2. Add columns to automation_rules
    with op.batch_alter_table("automation_rules") as batch_op:
        batch_op.add_column(
            sa.Column("automation_type", sa.String(50), nullable=False, server_default=sa.text("'appointment_reminder'"))
        )
        batch_op.add_column(
            sa.Column("trigger_event", sa.String(50), nullable=False, server_default=sa.text("'appointment_confirmed'"))
        )
        batch_op.add_column(
            sa.Column("delay_minutes", sa.Integer(), nullable=False, server_default=sa.text("0"))
        )
        batch_op.add_column(
            sa.Column("business_hours_only", sa.Boolean(), nullable=False, server_default=bool_true)
        )
        batch_op.add_column(
            sa.Column("start_hour", sa.String(10), nullable=False, server_default=sa.text("'09:00'"))
        )
        batch_op.add_column(
            sa.Column("end_hour", sa.String(10), nullable=False, server_default=sa.text("'20:00'"))
        )
        batch_op.add_column(
            sa.Column("permitted_days", json_type, nullable=False, server_default=sa.text("'[1, 2, 3, 4, 5, 6]'"))
        )
        batch_op.add_column(
            sa.Column("timezone", sa.String(50), nullable=False, server_default=sa.text("'Asia/Kolkata'"))
        )
        batch_op.add_column(
            sa.Column(
                "template_id",
                uuid_type,
                sa.ForeignKey("automation_message_templates.id", ondelete="SET NULL"),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column("fallback_body", sa.Text(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("provider", sa.String(50), nullable=False, server_default=sa.text("'any'"))
        )
        batch_op.add_column(
            sa.Column("max_sends_per_contact", sa.Integer(), nullable=False, server_default=sa.text("1"))
        )
        batch_op.add_column(
            sa.Column("cooldown_hours", sa.Integer(), nullable=False, server_default=sa.text("24"))
        )
        batch_op.add_column(
            sa.Column(
                "retry_policy",
                json_type,
                nullable=False,
                server_default=sa.text("'{\"max_retries\": 3, \"backoff_minutes\": 5}'"),
            )
        )
        batch_op.add_column(
            sa.Column("eligibility_filters", json_type, nullable=False, server_default=sa.text("'{}'"))
        )
        batch_op.add_column(
            sa.Column(
                "created_by_user_id",
                uuid_type,
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "updated_by_user_id",
                uuid_type,
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            )
        )
        # Ensure is_enabled defaults to False for safe automation controls
        batch_op.alter_column("is_enabled", server_default=bool_false)

    op.create_index("idx_automation_rules_type", "automation_rules", ["automation_type"])
    op.create_index("idx_automation_rules_trigger", "automation_rules", ["trigger_event"])

    # 3. Create automation_scheduled_jobs table
    op.create_table(
        "automation_scheduled_jobs",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column(
            "rule_id",
            uuid_type,
            sa.ForeignKey("automation_rules.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("automation_type", sa.String(50), nullable=False, index=True),
        sa.Column(
            "contact_id",
            uuid_type,
            sa.ForeignKey("whatsapp_contacts.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "conversation_id",
            uuid_type,
            sa.ForeignKey("conversations.id", ondelete="SET NULL"),
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
        sa.Column(
            "patient_id",
            uuid_type,
            sa.ForeignKey("patients.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("status", sa.String(30), nullable=False, server_default=sa.text("'scheduled'"), index=True),
        sa.Column("suppression_reason", sa.String(100), nullable=True),
        sa.Column("suppression_details", json_type, nullable=True),
        sa.Column("payload", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("rendered_message", sa.Text(), nullable=True),
        sa.Column(
            "template_id",
            uuid_type,
            sa.ForeignKey("automation_message_templates.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("provider", sa.String(50), nullable=False, server_default=sa.text("'any'")),
        sa.Column("provider_message_id", sa.String(150), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(100), nullable=True),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(150), unique=True, index=True, nullable=False),
        sa.Column(
            "assigned_staff_id",
            uuid_type,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_by_user_id",
            uuid_type,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now_fn),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=now_fn),
    )
    op.create_index("idx_auto_jobs_status_scheduled", "automation_scheduled_jobs", ["status", "scheduled_for"])
    op.create_index("idx_auto_jobs_appt_status", "automation_scheduled_jobs", ["appointment_id", "status"])
    op.create_index("idx_auto_jobs_conv_status", "automation_scheduled_jobs", ["conversation_id", "status"])
    op.create_index("idx_auto_jobs_contact_type", "automation_scheduled_jobs", ["contact_id", "automation_type"])

    # 4. Create automation_execution_logs table
    op.create_table(
        "automation_execution_logs",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column(
            "job_id",
            uuid_type,
            sa.ForeignKey("automation_scheduled_jobs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "rule_id",
            uuid_type,
            sa.ForeignKey("automation_rules.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "contact_id",
            uuid_type,
            sa.ForeignKey("whatsapp_contacts.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("automation_type", sa.String(50), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("status_before", sa.String(30), nullable=True),
        sa.Column("status_after", sa.String(30), nullable=True),
        sa.Column("provider", sa.String(50), nullable=True),
        sa.Column("provider_message_id", sa.String(150), nullable=True),
        sa.Column("details", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now_fn),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=now_fn),
    )
    op.create_index("idx_auto_exec_job", "automation_execution_logs", ["job_id", "created_at"])
    op.create_index("idx_auto_exec_contact", "automation_execution_logs", ["contact_id", "created_at"])

    # 5. Create automation_suppression_logs table
    op.create_table(
        "automation_suppression_logs",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column(
            "job_id",
            uuid_type,
            sa.ForeignKey("automation_scheduled_jobs.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "rule_id",
            uuid_type,
            sa.ForeignKey("automation_rules.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "contact_id",
            uuid_type,
            sa.ForeignKey("whatsapp_contacts.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("reason", sa.String(100), nullable=False),
        sa.Column("details", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now_fn),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=now_fn),
    )
    op.create_index("idx_auto_suppress_contact", "automation_suppression_logs", ["contact_id", "created_at"])
    op.create_index("idx_auto_suppress_reason", "automation_suppression_logs", ["reason", "created_at"])

    # 6. Create automation_settings table
    op.create_table(
        "automation_settings",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("outbound_enabled", sa.Boolean(), nullable=False, server_default=bool_false),
        sa.Column("default_timezone", sa.String(50), nullable=False, server_default=sa.text("'Asia/Kolkata'")),
        sa.Column("quiet_hours_start", sa.String(10), nullable=False, server_default=sa.text("'21:00'")),
        sa.Column("quiet_hours_end", sa.String(10), nullable=False, server_default=sa.text("'09:00'")),
        sa.Column("business_hours_start", sa.String(10), nullable=False, server_default=sa.text("'09:00'")),
        sa.Column("business_hours_end", sa.String(10), nullable=False, server_default=sa.text("'20:00'")),
        sa.Column("worker_scan_interval_seconds", sa.Integer(), nullable=False, server_default=sa.text("60")),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("default_cooldown_hours", sa.Integer(), nullable=False, server_default=sa.text("24")),
        sa.Column("rate_limit_per_minute", sa.Integer(), nullable=False, server_default=sa.text("30")),
        sa.Column("emergency_stop", sa.Boolean(), nullable=False, server_default=bool_false),
        sa.Column(
            "updated_by_user_id",
            uuid_type,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now_fn),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=now_fn),
    )

    # 7. Create automation_contact_cooldowns table
    op.create_table(
        "automation_contact_cooldowns",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column(
            "contact_id",
            uuid_type,
            sa.ForeignKey("whatsapp_contacts.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("automation_type", sa.String(50), nullable=False, index=True),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now_fn),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=now_fn),
    )
    op.create_index("idx_auto_cooldown_contact_type", "automation_contact_cooldowns", ["contact_id", "automation_type"])
    op.create_index("idx_auto_cooldown_expires", "automation_contact_cooldowns", ["expires_at"])


def downgrade() -> None:
    op.drop_table("automation_contact_cooldowns")
    op.drop_table("automation_settings")
    op.drop_table("automation_suppression_logs")
    op.drop_table("automation_execution_logs")
    op.drop_table("automation_scheduled_jobs")

    with op.batch_alter_table("automation_rules") as batch_op:
        batch_op.drop_index("idx_automation_rules_trigger")
        batch_op.drop_index("idx_automation_rules_type")
        batch_op.drop_column("updated_by_user_id")
        batch_op.drop_column("created_by_user_id")
        batch_op.drop_column("eligibility_filters")
        batch_op.drop_column("retry_policy")
        batch_op.drop_column("cooldown_hours")
        batch_op.drop_column("max_sends_per_contact")
        batch_op.drop_column("provider")
        batch_op.drop_column("fallback_body")
        batch_op.drop_column("template_id")
        batch_op.drop_column("timezone")
        batch_op.drop_column("permitted_days")
        batch_op.drop_column("end_hour")
        batch_op.drop_column("start_hour")
        batch_op.drop_column("business_hours_only")
        batch_op.drop_column("delay_minutes")
        batch_op.drop_column("trigger_event")
        batch_op.drop_column("automation_type")

    op.drop_table("automation_message_templates")
