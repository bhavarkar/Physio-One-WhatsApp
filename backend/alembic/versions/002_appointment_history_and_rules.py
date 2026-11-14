"""add appointment history, duration, user tracking and concurrency rules

Revision ID: 002_appointment_history_and_rules
Revises: 001_initial_schema
Create Date: 2026-11-13 23:45:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "002_appointment_history_and_rules"
down_revision: Union[str, None] = "001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add duration_minutes, created_by_id, updated_by_id to appointments
    op.add_column(
        "appointments",
        sa.Column(
            "duration_minutes",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("45"),
        ),
    )
    op.add_column(
        "appointments",
        sa.Column(
            "created_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "appointments",
        sa.Column(
            "updated_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("idx_appointments_created_by", "appointments", ["created_by_id"])
    op.create_index("idx_appointments_updated_by", "appointments", ["updated_by_id"])

    # 2. Create appointment_history table
    op.create_table(
        "appointment_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "appointment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("appointments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("from_status", sa.String(length=30), nullable=True),
        sa.Column("to_status", sa.String(length=30), nullable=True),
        sa.Column("from_start_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("from_end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("to_start_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("to_end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("actor_type", sa.String(length=30), nullable=False, server_default=sa.text("'staff'")),
        sa.Column(
            "actor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_appointment_history_appt_created", "appointment_history", ["appointment_id", "created_at"])

    # 3. PostgreSQL concurrency exclusion constraint (safe across dialects)
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist;")
        op.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'uq_no_overlapping_active_appointments'
                ) THEN
                    ALTER TABLE appointments
                    ADD CONSTRAINT uq_no_overlapping_active_appointments
                    EXCLUDE USING gist (
                        practitioner_name WITH =,
                        tstzrange(start_time, end_time) WITH &&
                    )
                    WHERE (status NOT IN ('cancelled', 'no_show'));
                END IF;
            END $$;
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            ALTER TABLE appointments
            DROP CONSTRAINT IF EXISTS uq_no_overlapping_active_appointments;
            """
        )

    op.drop_index("idx_appointment_history_appt_created", table_name="appointment_history")
    op.drop_table("appointment_history")
    op.drop_index("idx_appointments_updated_by", table_name="appointments")
    op.drop_index("idx_appointments_created_by", table_name="appointments")
    op.drop_column("appointments", "updated_by_id")
    op.drop_column("appointments", "created_by_id")
    op.drop_column("appointments", "duration_minutes")

