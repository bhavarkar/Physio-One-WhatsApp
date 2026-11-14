"""create initial single-organization schema with pgvector

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-11-13 21:15:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import pgvector.sqlalchemy

# revision identifiers, used by Alembic.
revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 0. Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # 1. Access Control: roles
    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("name", name="uq_roles_name"),
    )
    op.create_index("idx_roles_name", "roles", ["name"])

    # 2. Access Control: permissions
    op.create_table(
        "permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resource", sa.String(length=50), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("role_id", "resource", "action", name="uq_role_resource_action"),
    )
    op.create_index("idx_permissions_role_id", "permissions", ["role_id"])

    # 3. Access Control: users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("idx_users_email", "users", ["email"])
    op.create_index("idx_users_role_id", "users", ["role_id"])

    # 4. Access Control: user_sessions
    op.create_table(
        "user_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_revoked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("token_hash", name="uq_user_sessions_token_hash"),
    )
    op.create_index("idx_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index("idx_user_sessions_token_hash", "user_sessions", ["token_hash"])

    # 5. Auditing: audit_logs
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=50), nullable=False),
        sa.Column("resource_id", sa.String(length=100), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("idx_audit_logs_action", "audit_logs", ["action"])
    op.create_index("idx_audit_logs_resource", "audit_logs", ["resource_type"])
    op.create_index("idx_audit_logs_created_at", "audit_logs", ["created_at"])

    # 6. WhatsApp: accounts
    op.create_table(
        "whatsapp_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(length=50), nullable=False, server_default=sa.text("'meta'")),
        sa.Column("account_name", sa.String(length=100), nullable=False),
        sa.Column("phone_number_id", sa.String(length=100), nullable=False),
        sa.Column("business_account_id", sa.String(length=100), nullable=True),
        sa.Column("display_phone_number", sa.String(length=30), nullable=False),
        sa.Column("webhook_verify_token", sa.String(length=255), nullable=False),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("secret_key_encrypted", sa.Text(), nullable=True),
        sa.Column("provider_config", postgresql.JSONB(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_whatsapp_accounts_provider", "whatsapp_accounts", ["provider"])
    op.create_index("idx_whatsapp_accounts_phone_id", "whatsapp_accounts", ["phone_number_id"])

    # 7. WhatsApp: contacts
    op.create_table(
        "whatsapp_contacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("wa_id", sa.String(length=50), nullable=False),
        sa.Column("profile_name", sa.String(length=150), nullable=True),
        sa.Column("opted_out_marketing", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("opted_out_all", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("wa_id", name="uq_whatsapp_contacts_wa_id"),
    )
    op.create_index("idx_whatsapp_contacts_wa_id", "whatsapp_contacts", ["wa_id"])
    op.create_index("idx_whatsapp_contacts_last_active", "whatsapp_contacts", ["last_active_at"])

    # 8. WhatsApp: conversations
    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("whatsapp_contacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default=sa.text("'open'")),
        sa.Column("is_human_takeover", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("takeover_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("takeover_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ai_paused", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("ai_paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active_agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_conversations_contact_id", "conversations", ["contact_id"])
    op.create_index("idx_conversations_status", "conversations", ["status"])
    op.create_index("idx_conversations_last_msg", "conversations", ["last_message_at"])

    # 9. WhatsApp: messages
    op.create_table(
        "whatsapp_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("whatsapp_contacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False, server_default=sa.text("'meta'")),
        sa.Column("provider_message_id", sa.String(length=150), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("message_type", sa.String(length=20), nullable=False, server_default=sa.text("'text'")),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("media_url", sa.Text(), nullable=True),
        sa.Column("media_mime_type", sa.String(length=50), nullable=True),
        sa.Column("voice_transcription", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'received'")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("provider", "provider_message_id", name="uq_provider_message_id"),
    )
    op.create_index("idx_whatsapp_messages_conv_created", "whatsapp_messages", ["conversation_id", "created_at"])
    op.create_index("idx_whatsapp_messages_contact_id", "whatsapp_messages", ["contact_id"])
    op.create_index("idx_whatsapp_messages_provider_id", "whatsapp_messages", ["provider", "provider_message_id"])

    # 10. WhatsApp: webhook_events
    op.create_table(
        "webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("event_id", sa.String(length=150), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'received'")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("provider", "event_id", name="uq_provider_event_id"),
    )
    op.create_index("idx_webhook_events_status_created", "webhook_events", ["status", "created_at"])

    # 11. WhatsApp: message_debounce
    op.create_table(
        "message_debounce",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("contact_wa_id", sa.String(length=50), nullable=False),
        sa.Column("message_hash", sa.String(length=64), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_debounce_lookup", "message_debounce", ["contact_wa_id", "message_hash", "expires_at"])

    # 12. WhatsApp: templates
    op.create_table(
        "whatsapp_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(length=50), nullable=False, server_default=sa.text("'meta'")),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=False, server_default=sa.text("'en'")),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("header_type", sa.String(length=20), nullable=True),
        sa.Column("body_template", sa.Text(), nullable=False),
        sa.Column("variables", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("provider", "name", "language", name="uq_template_provider_name_lang"),
    )
    op.create_index("idx_whatsapp_templates_name", "whatsapp_templates", ["name"])

    # 13. Clinical: patients
    op.create_table(
        "patients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("whatsapp_contacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("full_name", sa.String(length=150), nullable=False),
        sa.Column("phone_number", sa.String(length=30), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("age", sa.Integer(), nullable=True),
        sa.Column("gender", sa.String(length=20), nullable=True),
        sa.Column("primary_complaint", sa.Text(), nullable=True),
        sa.Column("medical_history", sa.Text(), nullable=True),
        sa.Column("emergency_contact", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("phone_number", name="uq_patients_phone_number"),
    )
    op.create_index("idx_patients_phone", "patients", ["phone_number"])
    op.create_index("idx_patients_full_name", "patients", ["full_name"])
    op.create_index("idx_patients_contact_id", "patients", ["contact_id"])

    # 14. Clinical: patient_consents
    op.create_table(
        "patient_consents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("consent_type", sa.String(length=50), nullable=False),
        sa.Column("is_granted", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_patient_consents_patient_id", "patient_consents", ["patient_id"])

    # 15. Clinical: appointments
    op.create_table(
        "appointments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("practitioner_name", sa.String(length=100), nullable=False, server_default=sa.text("'Dr. Physio One'")),
        sa.Column("service_type", sa.String(length=100), nullable=False, server_default=sa.text("'Initial Physiotherapy Assessment'")),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(length=50), nullable=False, server_default=sa.text("'Asia/Kolkata'")),
        sa.Column("status", sa.String(length=30), nullable=False, server_default=sa.text("'confirmed'")),
        sa.Column("booked_by", sa.String(length=30), nullable=False, server_default=sa.text("'deepti_agent'")),
        sa.Column("external_appointment_id", sa.String(length=100), nullable=True),
        sa.Column("rescheduled_from_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("EXTRACT(DOW FROM start_time) != 0", name="chk_appointment_no_sunday"),
    )
    op.create_index("idx_appointment_time_status", "appointments", ["start_time", "end_time", "status"])
    op.create_index("idx_appointment_patient_status", "appointments", ["patient_id", "status"])

    # 16. AI: providers
    op.create_table(
        "ai_providers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("base_url", sa.String(length=255), nullable=False),
        sa.Column("api_key_encrypted", sa.Text(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("config", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("name", name="uq_ai_providers_name"),
    )
    op.create_index("idx_ai_providers_name", "ai_providers", ["name"])

    # 17. AI: models
    op.create_table(
        "ai_models",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ai_providers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model_identifier", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("supports_tools", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("supports_vision", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("max_context_tokens", sa.Integer(), nullable=False, server_default=sa.text("8192")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("provider_id", "model_identifier", name="uq_provider_model_identifier"),
    )
    op.create_index("idx_ai_models_provider_id", "ai_models", ["provider_id"])

    # 18. AI: agents
    op.create_table(
        "ai_agents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("primary_model_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ai_models.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("fallback_model_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ai_models.id", ondelete="SET NULL"), nullable=True),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("temperature", sa.Numeric(precision=3, scale=2), nullable=False, server_default=sa.text("0.20")),
        sa.Column("max_tokens", sa.Integer(), nullable=False, server_default=sa.text("1000")),
        sa.Column("supported_languages", postgresql.JSONB(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("name", name="uq_ai_agents_name"),
    )
    op.create_index("idx_ai_agents_name", "ai_agents", ["name"])

    # 19. AI: agent_versions
    op.create_table(
        "ai_agent_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ai_agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("temperature", sa.Numeric(precision=3, scale=2), nullable=False),
        sa.Column("changed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("agent_id", "version_number", name="uq_agent_version_number"),
    )
    op.create_index("idx_ai_agent_versions_agent_id", "ai_agent_versions", ["agent_id"])

    # 20. AI: tool_definitions
    op.create_table(
        "ai_tool_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("parameters_schema", postgresql.JSONB(), nullable=False),
        sa.Column("requires_permission", sa.String(length=50), nullable=False, server_default=sa.text("'appointments:create'")),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("name", name="uq_ai_tool_definitions_name"),
    )
    op.create_index("idx_ai_tool_definitions_name", "ai_tool_definitions", ["name"])

    # 21. AI: tool_executions
    op.create_table(
        "ai_tool_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ai_agents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("tool_name", sa.String(length=100), nullable=False),
        sa.Column("arguments", postgresql.JSONB(), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("execution_duration_ms", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_tool_exec_conv_status", "ai_tool_executions", ["conversation_id", "status"])
    op.create_index("idx_tool_exec_tool_created", "ai_tool_executions", ["tool_name", "created_at"])

    # 22. Memory: conversation_summaries
    op.create_table(
        "conversation_summaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("key_entities", postgresql.JSONB(), nullable=True),
        sa.Column("last_summarized_message_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("whatsapp_messages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_conv_summaries_conv_id", "conversation_summaries", ["conversation_id"])

    # 23. Memory: conversation_memory with pgvector
    op.create_table(
        "conversation_memory",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("whatsapp_contacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("memory_type", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(1536), nullable=True),
        sa.Column("confidence_score", sa.Numeric(precision=3, scale=2), nullable=False, server_default=sa.text("1.00")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_conv_memory_contact_id", "conversation_memory", ["contact_id"])
    op.execute("CREATE INDEX IF NOT EXISTS idx_conv_memory_embedding ON conversation_memory USING hnsw (embedding vector_cosine_ops);")

    # 24. Knowledge: knowledge_bases
    op.create_table(
        "knowledge_bases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("name", name="uq_knowledge_bases_name"),
    )
    op.create_index("idx_knowledge_bases_name", "knowledge_bases", ["name"])

    # 25. Knowledge: knowledge_documents
    op.create_table(
        "knowledge_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("knowledge_base_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("file_type", sa.String(length=20), nullable=False),
        sa.Column("file_url", sa.Text(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_knowledge_docs_kb_id", "knowledge_documents", ["knowledge_base_id"])

    # 26. Knowledge: knowledge_chunks with pgvector
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(1536), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_knowledge_chunk_doc_idx", "knowledge_chunks", ["document_id", "chunk_index"])
    op.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_chunk_embedding ON knowledge_chunks USING hnsw (embedding vector_cosine_ops);")

    # 27. Campaigns: templates
    op.create_table(
        "campaign_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("whatsapp_template_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("whatsapp_templates.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("reel_url", sa.Text(), nullable=True),
        sa.Column("thumbnail_url", sa.Text(), nullable=True),
        sa.Column("headline", sa.String(length=200), nullable=True),
        sa.Column("body_template", sa.Text(), nullable=False),
        sa.Column("parameters", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("name", name="uq_campaign_templates_name"),
    )
    op.create_index("idx_campaign_templates_name", "campaign_templates", ["name"])

    # 28. Campaigns: campaigns
    op.create_table(
        "campaigns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("campaign_template_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("campaign_templates.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.String(length=150), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False, server_default=sa.text("'meta'")),
        sa.Column("status", sa.String(length=30), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("target_audience_rules", postgresql.JSONB(), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_window_start", sa.String(length=5), nullable=False, server_default=sa.text("'09:00'")),
        sa.Column("execution_window_end", sa.String(length=5), nullable=False, server_default=sa.text("'21:00'")),
        sa.Column("total_targeted", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_sent", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_delivered", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_replied", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_campaigns_status_schedule", "campaigns", ["status", "scheduled_for"])

    # 29. Campaigns: deliveries
    op.create_table(
        "campaign_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("whatsapp_contacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_eligible", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("ineligibility_reason", sa.String(length=100), nullable=True),
        sa.Column("delivery_attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("error_reason", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("campaign_id", "contact_id", name="uq_campaign_recipient"),
    )
    op.create_index("idx_campaign_delivery_status", "campaign_deliveries", ["status", "sent_at"])

    # 30. Automations: follow-ups
    op.create_table(
        "scheduled_followups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("whatsapp_contacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("touch_stage", sa.Integer(), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default=sa.text("'scheduled'")),
        sa.Column("suppression_reason", sa.String(length=100), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_message_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("whatsapp_messages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_followup_status_schedule", "scheduled_followups", ["status", "scheduled_for"])
    op.create_index("idx_followup_conv_touch", "scheduled_followups", ["conversation_id", "touch_stage"])

    # 31. Automations: rules
    op.create_table(
        "automation_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("trigger_type", sa.String(length=50), nullable=False),
        sa.Column("condition_json", postgresql.JSONB(), nullable=False),
        sa.Column("action_type", sa.String(length=50), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("name", name="uq_automation_rules_name"),
    )
    op.create_index("idx_automation_rules_name", "automation_rules", ["name"])

    # 32. Background execution: background_jobs
    op.create_table(
        "background_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_type", sa.String(length=100), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_bg_jobs_status_sched", "background_jobs", ["status", "scheduled_at"])

    # 33. Configuration: system_settings
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(length=100), primary_key=True),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_secret", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    # Drop tables in reverse dependency order
    op.drop_table("system_settings")
    op.drop_table("background_jobs")
    op.drop_table("automation_rules")
    op.drop_table("scheduled_followups")
    op.drop_table("campaign_deliveries")
    op.drop_table("campaigns")
    op.drop_table("campaign_templates")
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_documents")
    op.drop_table("knowledge_bases")
    op.drop_table("conversation_memory")
    op.drop_table("conversation_summaries")
    op.drop_table("ai_tool_executions")
    op.drop_table("ai_tool_definitions")
    op.drop_table("ai_agent_versions")
    op.drop_table("ai_agents")
    op.drop_table("ai_models")
    op.drop_table("ai_providers")
    op.drop_table("appointments")
    op.drop_table("patient_consents")
    op.drop_table("patients")
    op.drop_table("whatsapp_templates")
    op.drop_table("message_debounce")
    op.drop_table("webhook_events")
    op.drop_table("whatsapp_messages")
    op.drop_table("conversations")
    op.drop_table("whatsapp_contacts")
    op.drop_table("whatsapp_accounts")
    op.drop_table("audit_logs")
    op.drop_table("user_sessions")
    op.drop_table("users")
    op.drop_table("permissions")
    op.drop_table("roles")

