"""Comprehensive Database and SQLAlchemy Models Test Suite

Single Organization Edition: Physio One Clinic.
Validates all 12 core requirements from Task 2 Part E.
"""
import uuid
from datetime import datetime, timezone, timedelta
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select

from app.core.database import Base
from app.models import (
    Role,
    Permission,
    User,
    UserSession,
    WhatsAppAccount,
    WhatsAppContact,
    Conversation,
    WhatsAppMessage,
    WebhookEvent,
    MessageDebounce,
    WhatsAppTemplate,
    Patient,
    PatientConsent,
    Appointment,
    AIProvider,
    AIModel,
    AIAgent,
    AIAgentVersion,
    AIToolDefinition,
    AIToolExecution,
    ConversationSummary,
    ConversationMemory,
    KnowledgeBase,
    KnowledgeDocument,
    KnowledgeChunk,
    CampaignTemplate,
    Campaign,
    CampaignDelivery,
    ScheduledFollowup,
    AutomationRule,
    BackgroundJob,
    SystemSetting,
)


def test_1_database_connection_and_table_count(engine):
    """1. Test connection and verify all tables (including appointment_history) are created in metadata."""
    assert engine is not None
    table_names = list(Base.metadata.tables.keys())
    assert len(table_names) == 34
    assert "patients" in table_names
    assert "appointments" in table_names
    assert "appointment_history" in table_names
    assert "whatsapp_messages" in table_names
    assert "webhook_events" in table_names


def test_2_roles_and_permissions_foreign_key(db_session):
    """2 & 4. Test Role and Permission relationship with foreign keys and cascade."""
    admin_role = Role(name="Administrator", description="Clinic Admin")
    db_session.add(admin_role)
    db_session.commit()

    perm1 = Permission(role_id=admin_role.id, resource="appointments", action="create")
    perm2 = Permission(role_id=admin_role.id, resource="appointments", action="read")
    db_session.add_all([perm1, perm2])
    db_session.commit()

    # Verify relationship
    fetched_role = db_session.scalar(select(Role).where(Role.name == "Administrator"))
    assert len(fetched_role.permissions) == 2

    # Verify duplicate permission unique constraint
    dup_perm = Permission(role_id=admin_role.id, resource="appointments", action="create")
    db_session.add(dup_perm)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_3_user_and_session_creation(db_session):
    """3. Test User creation and UserSession persistence with foreign key."""
    role = Role(name="Operator", description="Desk Staff")
    db_session.add(role)
    db_session.commit()

    user = User(
        role_id=role.id,
        email="reception@physioone.com",
        password_hash="argon2_hashed_secret",
        full_name="Physio Reception",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    session = UserSession(
        user_id=user.id,
        token_hash="sample_token_hash_value_123",
        ip_address="127.0.0.1",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db_session.add(session)
    db_session.commit()

    fetched_user = db_session.scalar(select(User).where(User.email == "reception@physioone.com"))
    assert fetched_user is not None
    assert len(fetched_user.sessions) == 1
    assert fetched_user.sessions[0].token_hash == "sample_token_hash_value_123"


def test_4_unique_provider_message_ids(db_session):
    """5 & 8. Test unique provider message ID enforcement."""
    contact = WhatsAppContact(wa_id="919876543210", profile_name="Rahul Sharma")
    db_session.add(contact)
    db_session.commit()

    conv = Conversation(contact_id=contact.id, status="open")
    db_session.add(conv)
    db_session.commit()

    msg1 = WhatsAppMessage(
        conversation_id=conv.id,
        contact_id=contact.id,
        provider="meta",
        provider_message_id="wamid.HBgLOTE5ODc2NTQzMjEwFQIAEhgUM0EBQ0QxMjM0NTY3ODkwQUJDREY=",
        direction="inbound",
        message_type="text",
        body="Hello, do you have slots tomorrow?",
    )
    db_session.add(msg1)
    db_session.commit()

    # Attempting to insert identical provider message ID must fail
    msg_duplicate = WhatsAppMessage(
        conversation_id=conv.id,
        contact_id=contact.id,
        provider="meta",
        provider_message_id="wamid.HBgLOTE5ODc2NTQzMjEwFQIAEhgUM0EBQ0QxMjM0NTY3ODkwQUJDREY=",
        direction="inbound",
        message_type="text",
        body="Duplicate message delivery attempt",
    )
    db_session.add(msg_duplicate)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_5_duplicate_webhook_event_prevention(db_session):
    """6. Test duplicate webhook event prevention across providers."""
    evt1 = WebhookEvent(
        provider="ycloud",
        event_id="evt_ycloud_1001",
        event_type="message.received",
        payload={"message": {"id": "msg_123"}},
        status="processed",
    )
    db_session.add(evt1)
    db_session.commit()

    # Duplicate webhook event
    evt_dup = WebhookEvent(
        provider="ycloud",
        event_id="evt_ycloud_1001",
        event_type="message.received",
        payload={"message": {"id": "msg_123"}},
        status="received",
    )
    db_session.add(evt_dup)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_6_contact_creation_and_lookup(db_session):
    """7. Test WhatsApp contact creation and indexed lookup."""
    contact = WhatsAppContact(
        wa_id="919123456789",
        profile_name="Priya Patel",
        opted_out_marketing=False,
    )
    db_session.add(contact)
    db_session.commit()

    found = db_session.scalar(select(WhatsAppContact).where(WhatsAppContact.wa_id == "919123456789"))
    assert found is not None
    assert found.profile_name == "Priya Patel"


def test_7_appointment_persistence(db_session):
    """9. Test appointment scheduling with patient relationship."""
    contact = WhatsAppContact(wa_id="919999888877", profile_name="Amit Verma")
    db_session.add(contact)
    db_session.commit()

    patient = Patient(
        contact_id=contact.id,
        full_name="Amit Verma",
        phone_number="919999888877",
        primary_complaint="Lower back pain",
    )
    db_session.add(patient)
    db_session.commit()

    # Create Wednesday appointment (not Sunday)
    start = datetime(2026, 11, 18, 10, 0, tzinfo=timezone.utc)  # Nov 18, 2026 is Wednesday
    end = start + timedelta(minutes=45)

    appointment = Appointment(
        patient_id=patient.id,
        practitioner_name="Dr. Physio One",
        service_type="Initial Physiotherapy Assessment",
        start_time=start,
        end_time=end,
        status="confirmed",
        booked_by="deepti_agent",
        notes="Patient requested morning slot.",
    )
    db_session.add(appointment)
    db_session.commit()

    fetched = db_session.scalar(select(Appointment).where(Appointment.patient_id == patient.id))
    assert fetched is not None
    assert fetched.practitioner_name == "Dr. Physio One"
    assert fetched.status == "confirmed"


def test_8_campaign_recipient_persistence(db_session):
    """10. Test campaign template, campaign, and recipient delivery persistence with unique constraint."""
    tpl = CampaignTemplate(
        name="Instagram Back Pain Reel Promo",
        reel_url="https://www.instagram.com/reel/C8XYZ123/",
        headline="Relieve your lower back pain today",
        body_template="Hi {{1}}, Dr. Physio One shared 3 quick stretches for back stiffness.",
    )
    db_session.add(tpl)
    db_session.commit()

    campaign = Campaign(
        campaign_template_id=tpl.id,
        title="November Back Pain Campaign",
        provider="meta",
        status="active",
        target_audience_rules={"workflow": "instagram_reengagement", "window_hours": [24, 48]},
    )
    db_session.add(campaign)
    db_session.commit()

    contact = WhatsAppContact(wa_id="919444333222", profile_name="Sunita Rao")
    db_session.add(contact)
    db_session.commit()

    delivery = CampaignDelivery(
        campaign_id=campaign.id,
        contact_id=contact.id,
        is_eligible=True,
        status="sent",
        sent_at=datetime.now(timezone.utc),
    )
    db_session.add(delivery)
    db_session.commit()

    # Duplicate delivery for same contact and campaign must fail
    dup_delivery = CampaignDelivery(
        campaign_id=campaign.id,
        contact_id=contact.id,
        is_eligible=True,
        status="pending",
    )
    db_session.add(dup_delivery)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_9_followup_task_persistence(db_session):
    """11. Test durable 3-touch follow-up persistence and status progression."""
    contact = WhatsAppContact(wa_id="919555666777", profile_name="Karan Johar")
    db_session.add(contact)
    db_session.commit()

    conv = Conversation(contact_id=contact.id, status="open")
    db_session.add(conv)
    db_session.commit()

    # Touch 1: 2 hours later
    followup1 = ScheduledFollowup(
        contact_id=contact.id,
        conversation_id=conv.id,
        touch_stage=1,
        scheduled_for=datetime.now(timezone.utc) + timedelta(hours=2),
        status="scheduled",
    )
    db_session.add(followup1)
    db_session.commit()

    assert followup1.id is not None
    assert followup1.touch_stage == 1
    assert followup1.status == "scheduled"

    # Simulate cancellation when appointment is booked
    followup1.status = "suppressed"
    followup1.suppression_reason = "booked_appointment"
    db_session.commit()

    refetched = db_session.get(ScheduledFollowup, followup1.id)
    assert refetched.status == "suppressed"
    assert refetched.suppression_reason == "booked_appointment"


def test_10_ai_agent_and_version_history(db_session):
    """4. Test AI Provider, Model, Agent, and Version History persistence."""
    provider = AIProvider(
        name="meta_muse",
        base_url="https://api.muse.example.com/v1",
        api_key_encrypted="encrypted_key_sample",
        is_enabled=True,
    )
    db_session.add(provider)
    db_session.commit()

    model = AIModel(
        provider_id=provider.id,
        model_identifier="muse-chat-v1",
        display_name="Muse Chat v1",
        supports_tools=True,
    )
    db_session.add(model)
    db_session.commit()

    agent = AIAgent(
        name="Deepti Receptionist",
        description="Physio One Virtual Receptionist",
        primary_model_id=model.id,
        system_prompt="You are Deepti, the friendly AI receptionist for Physio One...",
        temperature=0.20,
        max_tokens=1000,
    )
    db_session.add(agent)
    db_session.commit()

    # Version 1 history
    v1 = AIAgentVersion(
        agent_id=agent.id,
        version_number=1,
        system_prompt=agent.system_prompt,
        temperature=agent.temperature,
        change_summary="Initial prompt creation for Physio One",
    )
    db_session.add(v1)
    db_session.commit()

    refetched_agent = db_session.scalar(select(AIAgent).where(AIAgent.name == "Deepti Receptionist"))
    assert refetched_agent is not None
    assert len(refetched_agent.versions) == 1
    assert refetched_agent.versions[0].version_number == 1


def test_11_knowledge_base_and_chunks(db_session):
    """12. Test Knowledge Base, Document, and Vector Chunk persistence."""
    kb = KnowledgeBase(name="Physio One Clinic FAQs", description="Clinical policies and FAQs")
    db_session.add(kb)
    db_session.commit()

    doc = KnowledgeDocument(
        knowledge_base_id=kb.id,
        title="Clinic Operating Hours and Sunday Policy.pdf",
        file_type="pdf",
        file_url="/storage/docs/faq.pdf",
        chunk_count=2,
    )
    db_session.add(doc)
    db_session.commit()

    chunk1 = KnowledgeChunk(
        document_id=doc.id,
        chunk_index=0,
        chunk_text="Physio One is strictly closed on Sundays. Appointments can be scheduled Monday through Saturday from 9 AM to 8 PM.",
    )
    db_session.add(chunk1)
    db_session.commit()

    assert chunk1.id is not None
    assert "closed on Sundays" in chunk1.chunk_text

def test_12_alembic_migration_script(capsys):
    """12. Test Alembic migration script generation and upgrade path."""
    from alembic.config import Config
    from alembic import command

    alembic_cfg = Config("backend/alembic.ini")
    alembic_cfg.set_main_option("script_location", "backend/alembic")
    
    command.upgrade(alembic_cfg, "head", sql=True)
    captured = capsys.readouterr()
    sql_output = captured.out

    assert "CREATE EXTENSION IF NOT EXISTS vector;" in sql_output
    assert "CREATE TABLE patients" in sql_output
    assert "CREATE TABLE appointments" in sql_output
    assert "CREATE TABLE whatsapp_messages" in sql_output
    assert "CREATE TABLE webhook_events" in sql_output
    assert "CREATE TABLE campaign_deliveries" in sql_output
    assert "CREATE TABLE scheduled_followups" in sql_output


def test_13_expand_and_contract_migration(capsys):
    """13. Test forward-compatible expand migration verification."""
    from alembic.operations import Operations
    from alembic.migration import MigrationContext
    from sqlalchemy import Column, String
    import io

    # Mock migration context for Postgres dialect
    from sqlalchemy.dialects import postgresql
    ctx = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True})
    op = Operations(ctx)

    # Perform expand step: add nullable column
    op.add_column("whatsapp_contacts", Column("notes", String(255), nullable=True))

    captured = capsys.readouterr()
    assert "ALTER TABLE whatsapp_contacts ADD COLUMN notes VARCHAR(255);" in captured.out
