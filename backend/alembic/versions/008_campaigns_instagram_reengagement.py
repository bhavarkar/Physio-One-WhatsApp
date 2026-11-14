"""campaigns instagram reengagement, legacy ycloud migration, media library, and approvals

Revision ID: 008_campaigns_instagram_reengagement
Revises: 007_scheduled_automation
Create Date: 2026-11-15 00:15:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "008_campaigns_instagram_reengagement"
down_revision: Union[str, None] = "007_scheduled_automation"
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

    # 1. Create campaign_media table (Media Library for Instagram Reels and assets)
    op.create_table(
        "campaign_media",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("title", sa.String(150), nullable=False),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("media_type", sa.String(30), nullable=False, server_default=sa.text("'instagram_reel'")),
        sa.Column("storage_path", sa.String(500), nullable=True),
        sa.Column("external_url", sa.Text(), nullable=True),
        sa.Column("thumbnail_url", sa.Text(), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column("tags", json_type, nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=bool_true),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=bool_false),
        sa.Column("created_by_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now_fn),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=now_fn),
    )
    op.create_index("idx_campaign_media_type", "campaign_media", ["media_type", "is_active"])

    # 2. Additive alterations to existing campaigns table
    with op.batch_alter_table("campaigns") as batch_op:
        batch_op.add_column(
            sa.Column("campaign_type", sa.String(50), nullable=False, server_default=sa.text("'instagram_reengagement'"))
        )
        batch_op.add_column(sa.Column("description", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("current_version", sa.Integer(), nullable=False, server_default=sa.text("1")))
        batch_op.add_column(sa.Column("is_approved", sa.Boolean(), nullable=False, server_default=bool_false))
        batch_op.add_column(sa.Column("approved_by_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True))
        batch_op.add_column(sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("approved_version", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("approval_notes", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("template_name", sa.String(150), nullable=True))
        batch_op.add_column(
            sa.Column("template_id", uuid_type, sa.ForeignKey("automation_message_templates.id", ondelete="SET NULL"), nullable=True)
        )
        batch_op.add_column(sa.Column("custom_message_body", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("media_id", uuid_type, sa.ForeignKey("campaign_media.id", ondelete="SET NULL"), nullable=True)
        )
        batch_op.add_column(sa.Column("rate_limit_per_minute", sa.Integer(), nullable=False, server_default=sa.text("30")))
        batch_op.add_column(sa.Column("rate_limit_per_hour", sa.Integer(), nullable=False, server_default=sa.text("1000")))
        batch_op.add_column(sa.Column("batch_size", sa.Integer(), nullable=False, server_default=sa.text("25")))
        batch_op.add_column(sa.Column("cooldown_days", sa.Integer(), nullable=False, server_default=sa.text("7")))
        batch_op.add_column(sa.Column("total_read", sa.Integer(), nullable=False, server_default=sa.text("0")))
        batch_op.add_column(sa.Column("total_converted", sa.Integer(), nullable=False, server_default=sa.text("0")))
        batch_op.add_column(sa.Column("total_suppressed", sa.Integer(), nullable=False, server_default=sa.text("0")))
        batch_op.add_column(sa.Column("total_failed", sa.Integer(), nullable=False, server_default=sa.text("0")))
        batch_op.add_column(sa.Column("created_by_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True))
        batch_op.add_column(sa.Column("error_message", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))

    op.create_index("idx_campaign_type_status", "campaigns", ["campaign_type", "status"])

    # 3. Create campaign_versions table (Immutable snapshots of campaign definitions)
    op.create_table(
        "campaign_versions",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("campaign_id", uuid_type, sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("snapshot", json_type, nullable=False),
        sa.Column("created_by_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now_fn),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=now_fn),
        sa.UniqueConstraint("campaign_id", "version_number", name="uq_campaign_version"),
    )
    op.create_index("idx_campaign_version_lookup", "campaign_versions", ["campaign_id", "version_number"])

    # 4. Create campaign_audiences table (Segment specifications & metrics)
    op.create_table(
        "campaign_audiences",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("campaign_id", uuid_type, sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("filter_criteria", json_type, nullable=False),
        sa.Column("total_contacts_evaluated", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("eligible_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("excluded_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now_fn),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=now_fn),
    )

    # 5. Create campaign_recipients table (Authoritative recipient lifecycle & idempotency)
    op.create_table(
        "campaign_recipients",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("campaign_id", uuid_type, sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("contact_id", uuid_type, sa.ForeignKey("whatsapp_contacts.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("patient_id", uuid_type, sa.ForeignKey("patients.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("is_eligible", sa.Boolean(), nullable=False, server_default=bool_true),
        sa.Column("suppression_reason", sa.String(100), nullable=True),
        sa.Column("suppression_details", json_type, nullable=True),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("converted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_message_id", sa.String(100), nullable=True),
        sa.Column("idempotency_key", sa.String(150), unique=True, nullable=False),
        sa.Column("rendered_message", sa.Text(), nullable=True),
        sa.Column("delivery_attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now_fn),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=now_fn),
        sa.UniqueConstraint("campaign_id", "contact_id", name="uq_campaign_recipient_contact"),
    )
    op.create_index("idx_campaign_recipient_status", "campaign_recipients", ["status", "scheduled_for"])
    op.create_index("idx_campaign_recipient_provider_msg", "campaign_recipients", ["provider_message_id"])

    # 6. Create campaign_approvals table (Staff approval records with version snapshots)
    op.create_table(
        "campaign_approvals",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("campaign_id", uuid_type, sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("campaign_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("reviewed_by_id", uuid_type, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("decision_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("snapshot", json_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now_fn),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=now_fn),
    )
    op.create_index("idx_campaign_approval_version", "campaign_approvals", ["campaign_id", "campaign_version"])

    # 7. Create campaign_delivery_events table (Provider event timeline)
    op.create_table(
        "campaign_delivery_events",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("campaign_id", uuid_type, sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("recipient_id", uuid_type, sa.ForeignKey("campaign_recipients.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False, server_default=sa.text("'meta'")),
        sa.Column("provider_message_id", sa.String(100), nullable=True),
        sa.Column("details", json_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now_fn),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=now_fn),
    )
    op.create_index("idx_delivery_event_recipient", "campaign_delivery_events", ["recipient_id", "event_type"])

    # 8. Create campaign_conversion_events table (Appointment booking attribution)
    op.create_table(
        "campaign_conversion_events",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("campaign_id", uuid_type, sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("recipient_id", uuid_type, sa.ForeignKey("campaign_recipients.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("contact_id", uuid_type, sa.ForeignKey("whatsapp_contacts.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("conversion_type", sa.String(50), nullable=False),
        sa.Column("appointment_id", uuid_type, sa.ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("attribution_window_hours", sa.Integer(), nullable=False, server_default=sa.text("72")),
        sa.Column("details", json_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now_fn),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=now_fn),
    )
    op.create_index("idx_conversion_event_campaign", "campaign_conversion_events", ["campaign_id", "conversion_type"])

    # 9. Create legacy_workflow_migrations table (YCloud/n8n cutover state machine)
    op.create_table(
        "legacy_workflow_migrations",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("workflow_name", sa.String(100), unique=True, nullable=False),
        sa.Column("provider", sa.String(20), nullable=False, server_default=sa.text("'ycloud'")),
        sa.Column("cutover_state", sa.String(50), nullable=False, server_default=sa.text("'legacy_active'")),
        sa.Column("legacy_trigger_info", json_type, nullable=True),
        sa.Column("shadow_run_results", json_type, nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("activated_by_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now_fn),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=now_fn),
    )


def downgrade() -> None:
    op.drop_table("legacy_workflow_migrations")
    op.drop_table("campaign_conversion_events")
    op.drop_table("campaign_delivery_events")
    op.drop_table("campaign_approvals")
    op.drop_table("campaign_recipients")
    op.drop_table("campaign_audiences")
    op.drop_table("campaign_versions")
    with op.batch_alter_table("campaigns") as batch_op:
        batch_op.drop_column("completed_at")
        batch_op.drop_column("error_message")
        batch_op.drop_column("created_by_id")
        batch_op.drop_column("total_failed")
        batch_op.drop_column("total_suppressed")
        batch_op.drop_column("total_converted")
        batch_op.drop_column("total_read")
        batch_op.drop_column("cooldown_days")
        batch_op.drop_column("batch_size")
        batch_op.drop_column("rate_limit_per_hour")
        batch_op.drop_column("rate_limit_per_minute")
        batch_op.drop_column("media_id")
        batch_op.drop_column("custom_message_body")
        batch_op.drop_column("template_id")
        batch_op.drop_column("template_name")
        batch_op.drop_column("approval_notes")
        batch_op.drop_column("approved_version")
        batch_op.drop_column("approved_at")
        batch_op.drop_column("approved_by_id")
        batch_op.drop_column("is_approved")
        batch_op.drop_column("current_version")
        batch_op.drop_column("description")
        batch_op.drop_column("campaign_type")
    op.drop_table("campaign_media")
