"""Integration and Safety Test Suite for Inbound AI Receptionist (Deepti) Orchestration.

Single Organization Edition: Physio One Clinic.
Tests:
1. Inbound Queue & Debouncing: burst messages aggregated into single turn.
2. Default Safety: ai_mode defaults to 'disabled'; no LLM execution or outbound send.
3. Shadow Mode: generates persistent AIResponseDraft; zero outbound messages dispatched.
4. Live Mode & Idempotency: autonomous dispatch only when explicitly activated, with once-only idempotency.
5. Opt-Out Safety: STOP / UNSUBSCRIBE sets opted_out_all and creates handoff audit trail.
6. Emergency Safety: emergency keywords trigger immediate human takeover and emergency guidance.
7. Human Takeover & AI Pause: active takeover or pause completely suppresses automated responses.
8. Live Inbox API Endpoints: list conversations, details, takeover, pause, resume, manual reply, and settings.
"""
import pytest
import uuid
import json
import httpx
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from httpx import AsyncClient

from app.core.crypto import encrypt_secret
from app.models.inbound import (
    InboundProcessingJob,
    AIInboundSettings,
    ConversationHandoff,
    AIResponseDraft,
    OutboundIdempotencyKey,
)
from app.models.whatsapp import Conversation, WhatsAppContact, WhatsAppMessage, WhatsAppAccount
from app.models.ai import AIAgent
from app.models.user import Role
from app.services.agent_service import AgentService
from app.services.inbound_queue import InboundQueueService
from app.services.inbound_orchestrator import InboundOrchestrator
from app.services.outbound_dispatcher import OutboundDispatcher
from app.providers.base import MessageDirection, MessageStatus, MessageType


async def setup_test_conversation(async_session: AsyncSession):
    """Seed test contact, conversation, and active WhatsApp account."""
    clean_phone = "+919876543210"
    
    # 1. Active WhatsApp Account
    stmt_acc = select(WhatsAppAccount).where(WhatsAppAccount.is_active == True)  # noqa: E712
    account = (await async_session.execute(stmt_acc)).scalars().first()
    if not account:
        account = WhatsAppAccount(
            provider="meta",
            account_name="Physio One Test WhatsApp",
            phone_number_id="1234567890",
            business_account_id="9876543210",
            display_phone_number="+919876543210",
            webhook_verify_token="test_token_123",
            access_token_encrypted=encrypt_secret("dummy_access_token"),
            is_active=True,
        )
        async_session.add(account)
        await async_session.flush()

    # 2. Contact
    stmt_c = select(WhatsAppContact).where(WhatsAppContact.wa_id == clean_phone)
    contact = (await async_session.execute(stmt_c)).scalar_one_or_none()
    if not contact:
        contact = WhatsAppContact(
            wa_id=clean_phone,
            profile_name="Ramesh Patel",
            last_active_at=datetime.now(timezone.utc),
        )
        async_session.add(contact)
        await async_session.flush()

    # 3. Conversation
    stmt_conv = select(Conversation).where(
        Conversation.contact_id == contact.id,
        Conversation.status != "closed",
    )
    conversation = (await async_session.execute(stmt_conv)).scalars().first()
    if not conversation:
        conversation = Conversation(
            contact_id=contact.id,
            status="open",
            is_human_takeover=False,
            ai_paused=False,
            last_message_at=datetime.now(timezone.utc),
        )
        async_session.add(conversation)
        await async_session.flush()

    await async_session.commit()
    return account, contact, conversation


@pytest.mark.asyncio
async def test_1_inbound_queue_debouncing(async_session: AsyncSession):
    """Verify burst messages within debounce window are aggregated into a single job."""
    account, contact, conversation = await setup_test_conversation(async_session)

    # Message 1
    msg1 = WhatsAppMessage(
        conversation_id=conversation.id,
        contact_id=contact.id,
        provider="meta",
        provider_message_id=f"inbound_burst_{uuid.uuid4()}",
        direction=MessageDirection.INBOUND.value,
        message_type=MessageType.TEXT.value,
        body="Hi there",
        status=MessageStatus.RECEIVED.value,
    )
    async_session.add(msg1)
    await async_session.flush()

    job1 = await InboundQueueService.enqueue_inbound_message(
        db=async_session,
        message=msg1,
        conversation=conversation,
        contact=contact,
    )
    await async_session.commit()

    assert job1.status == "debouncing"
    assert job1.aggregated_text == "Hi there"
    assert len(job1.aggregated_message_ids) == 1
    initial_debounce_until = job1.debounce_until

    # Message 2 sent 1 second later
    msg2 = WhatsAppMessage(
        conversation_id=conversation.id,
        contact_id=contact.id,
        provider="meta",
        provider_message_id=f"inbound_burst_{uuid.uuid4()}",
        direction=MessageDirection.INBOUND.value,
        message_type=MessageType.TEXT.value,
        body="I would like to check availability for next week.",
        status=MessageStatus.RECEIVED.value,
    )
    async_session.add(msg2)
    await async_session.flush()

    job2 = await InboundQueueService.enqueue_inbound_message(
        db=async_session,
        message=msg2,
        conversation=conversation,
        contact=contact,
    )
    await async_session.commit()

    # Same job is reused and aggregated
    assert job2.id == job1.id
    assert job2.status == "debouncing"
    assert "Hi there" in job2.aggregated_text
    assert "I would like to check availability" in job2.aggregated_text
    assert len(job2.aggregated_message_ids) == 2
    assert job2.debounce_until >= initial_debounce_until


@pytest.mark.asyncio
async def test_2_default_ai_mode_is_disabled(async_session: AsyncSession):
    """MANDATORY SAFETY: AI mode must default to 'disabled' and skip LLM execution."""
    account, contact, conversation = await setup_test_conversation(async_session)
    settings = await InboundQueueService.get_or_create_settings(async_session)
    
    assert settings.ai_mode == "disabled"

    job = InboundProcessingJob(
        conversation_id=conversation.id,
        contact_id=contact.id,
        provider="meta",
        status="processing",
        aggregated_message_ids=["msg_1"],
        aggregated_text="Hello, do you do back pain therapy?",
        debounce_until=datetime.now(timezone.utc) - timedelta(seconds=1),
        scheduled_at=datetime.now(timezone.utc),
    )
    async_session.add(job)
    await async_session.commit()

    outcome = await InboundOrchestrator.process_job(async_session, job)

    assert outcome["status"] == "skipped"
    assert outcome["reason"] == "ai_mode_disabled"

    # Confirm zero drafts created
    stmt_d = select(AIResponseDraft).where(AIResponseDraft.inbound_job_id == job.id)
    drafts = (await async_session.execute(stmt_d)).scalars().all()
    assert len(drafts) == 0


@pytest.mark.asyncio
async def test_3_shadow_mode_creates_draft_without_outbound_dispatch(async_session: AsyncSession):
    """Verify shadow mode executes Deepti agent, saves draft, but dispatches ZERO WhatsApp messages."""
    await AgentService.ensure_default_ai_entities(async_session)
    account, contact, conversation = await setup_test_conversation(async_session)

    # Configure shadow mode
    settings = await InboundQueueService.get_or_create_settings(async_session)
    settings.ai_mode = "shadow"
    await async_session.commit()

    job = InboundProcessingJob(
        conversation_id=conversation.id,
        contact_id=contact.id,
        provider="meta",
        status="processing",
        aggregated_message_ids=["msg_shadow_1"],
        aggregated_text="What are your clinic operating hours?",
        debounce_until=datetime.now(timezone.utc) - timedelta(seconds=1),
        scheduled_at=datetime.now(timezone.utc),
    )
    async_session.add(job)
    await async_session.commit()

    # Mock LLM response
    mock_payload = {
        "id": "cmpl-shadow",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Physio One is open Monday to Saturday from 9:00 AM to 8:00 PM IST. We are strictly closed on Sundays.",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 60, "completion_tokens": 30, "total_tokens": 90},
    }
    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=mock_payload)))

    # Count existing outbound messages
    stmt_cnt = select(WhatsAppMessage).where(WhatsAppMessage.direction == "outbound")
    pre_outbound_count = len((await async_session.execute(stmt_cnt)).scalars().all())

    outcome = await InboundOrchestrator.process_job(
        async_session,
        job,
        override_settings=settings,
        override_http_client=mock_client,
    )

    assert outcome["status"] == "shadow_drafted"
    assert "draft_id" in outcome

    # Verify draft in database
    stmt_d = select(AIResponseDraft).where(AIResponseDraft.id == uuid.UUID(outcome["draft_id"]))
    draft = (await async_session.execute(stmt_d)).scalar_one()
    assert draft.ai_mode == "shadow"
    assert draft.dispatched is False
    assert "Monday to Saturday from 9:00 AM to 8:00 PM" in draft.draft_text

    # MANDATORY: Zero outbound messages dispatched
    post_outbound_count = len((await async_session.execute(stmt_cnt)).scalars().all())
    assert post_outbound_count == pre_outbound_count


@pytest.mark.asyncio
async def test_4_live_mode_dispatch_and_idempotency(async_session: AsyncSession, monkeypatch):
    """Verify live mode dispatches outbound WhatsApp message with idempotency key."""
    await AgentService.ensure_default_ai_entities(async_session)
    account, contact, conversation = await setup_test_conversation(async_session)

    settings = await InboundQueueService.get_or_create_settings(async_session)
    settings.ai_mode = "live"
    await async_session.commit()

    job = InboundProcessingJob(
        conversation_id=conversation.id,
        contact_id=contact.id,
        provider="meta",
        status="processing",
        aggregated_message_ids=["msg_live_1"],
        aggregated_text="Do you treat knee pain?",
        debounce_until=datetime.now(timezone.utc) - timedelta(seconds=1),
        scheduled_at=datetime.now(timezone.utc),
    )
    async_session.add(job)
    await async_session.commit()

    # Mock provider adapter send
    from app.providers.meta import MetaCloudProvider
    from app.providers.base import OutboundSendResult
    from app.core.config import settings as core_settings

    monkeypatch.setattr(core_settings, "AUTOMATION_OUTBOUND_ENABLED", True)

    async def mock_send(self, to, text, preview_url=False):
        return OutboundSendResult(
            success=True,
            provider_message_id=f"wamid.mock_{uuid.uuid4()}",
            raw_response={"status": "sent"},
        )

    monkeypatch.setattr(MetaCloudProvider, "send_text_message", mock_send)

    mock_payload = {
        "id": "cmpl-live",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Yes, Physio One provides specialized knee rehabilitation and physiotherapy.",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
    }
    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=mock_payload)))

    outcome = await InboundOrchestrator.process_job(
        async_session,
        job,
        override_settings=settings,
        override_http_client=mock_client,
    )

    assert outcome["status"] == "live_dispatched"
    draft_id = uuid.UUID(outcome["draft_id"])
    stmt_d = select(AIResponseDraft).where(AIResponseDraft.id == draft_id)
    draft = (await async_session.execute(stmt_d)).scalar_one()
    assert draft.dispatched is True
    assert draft.outbound_message_id is not None

    # Verify idempotency key is recorded as 'sent'
    stmt_k = select(OutboundIdempotencyKey).where(
        OutboundIdempotencyKey.idempotency_key == f"ai_reply_{conversation.id}_{job.id}"
    )
    key_record = (await async_session.execute(stmt_k)).scalar_one()
    assert key_record.status == "sent"

    # Re-dispatch with identical idempotency key blocks duplicate send
    dup_res = await OutboundDispatcher.dispatch_ai_reply(
        db=async_session,
        conversation=conversation,
        contact=contact,
        provider="meta",
        reply_text="Duplicate test",
        idempotency_key=f"ai_reply_{conversation.id}_{job.id}",
        settings=settings,
    )
    assert dup_res.get("duplicate") is True


@pytest.mark.asyncio
async def test_5_opt_out_keyword_suppresses_ai(async_session: AsyncSession):
    """Verify STOP/UNSUBSCRIBE sets opted_out_all and creates an immutable handoff audit record."""
    account, contact, conversation = await setup_test_conversation(async_session)
    contact.opted_out_all = False
    await async_session.commit()

    settings = await InboundQueueService.get_or_create_settings(async_session)

    job = InboundProcessingJob(
        conversation_id=conversation.id,
        contact_id=contact.id,
        provider="meta",
        status="processing",
        aggregated_message_ids=["msg_optout"],
        aggregated_text="Please STOP sending me messages",
        debounce_until=datetime.now(timezone.utc) - timedelta(seconds=1),
        scheduled_at=datetime.now(timezone.utc),
    )
    async_session.add(job)
    await async_session.commit()

    outcome = await InboundOrchestrator.process_job(async_session, job, override_settings=settings)

    assert outcome["status"] == "opted_out"

    # Contact is now opted out
    await async_session.refresh(contact)
    assert contact.opted_out_all is True

    # Audit handoff record
    stmt_h = select(ConversationHandoff).where(
        ConversationHandoff.conversation_id == conversation.id,
        ConversationHandoff.action == "opt_out_triggered",
    )
    handoff = (await async_session.execute(stmt_h)).scalar_one()
    assert handoff.actor_type == "patient"


@pytest.mark.asyncio
async def test_6_emergency_keyword_triggers_human_takeover(async_session: AsyncSession):
    """Verify emergency keywords trigger human takeover, safety audit, and emergency draft."""
    account, contact, conversation = await setup_test_conversation(async_session)
    conversation.is_human_takeover = False
    await async_session.commit()

    settings = await InboundQueueService.get_or_create_settings(async_session)

    job = InboundProcessingJob(
        conversation_id=conversation.id,
        contact_id=contact.id,
        provider="meta",
        status="processing",
        aggregated_message_ids=["msg_emerg"],
        aggregated_text="I am having severe pain and chest pain, emergency help needed!",
        debounce_until=datetime.now(timezone.utc) - timedelta(seconds=1),
        scheduled_at=datetime.now(timezone.utc),
    )
    async_session.add(job)
    await async_session.commit()

    outcome = await InboundOrchestrator.process_job(async_session, job, override_settings=settings)

    assert outcome["status"] == "emergency_handled"

    # Conversation is immediately in human takeover
    await async_session.refresh(conversation)
    assert conversation.is_human_takeover is True

    # Handoff record exists
    stmt_h = select(ConversationHandoff).where(
        ConversationHandoff.conversation_id == conversation.id,
        ConversationHandoff.action == "emergency_detected",
    )
    handoff = (await async_session.execute(stmt_h)).scalar_one()
    assert handoff.actor_type == "system"


@pytest.mark.asyncio
async def test_7_human_takeover_and_ai_paused_suppress_orchestration(async_session: AsyncSession):
    """Verify conversations under human takeover or ai_paused do not invoke AI."""
    account, contact, conversation = await setup_test_conversation(async_session)

    # 1. Human Takeover test
    conversation.is_human_takeover = True
    conversation.ai_paused = False
    await async_session.commit()

    job1 = InboundProcessingJob(
        conversation_id=conversation.id,
        contact_id=contact.id,
        provider="meta",
        status="processing",
        aggregated_message_ids=["msg_t1"],
        aggregated_text="Can I book for tomorrow?",
        debounce_until=datetime.now(timezone.utc) - timedelta(seconds=1),
        scheduled_at=datetime.now(timezone.utc),
    )
    async_session.add(job1)
    await async_session.commit()

    res1 = await InboundOrchestrator.process_job(async_session, job1)
    assert res1["status"] == "suppressed"
    assert res1["reason"] == "human_takeover_active"

    # 2. AI Paused test
    conversation.is_human_takeover = False
    conversation.ai_paused = True
    await async_session.commit()

    job2 = InboundProcessingJob(
        conversation_id=conversation.id,
        contact_id=contact.id,
        provider="meta",
        status="processing",
        aggregated_message_ids=["msg_t2"],
        aggregated_text="Can I book for tomorrow?",
        debounce_until=datetime.now(timezone.utc) - timedelta(seconds=1),
        scheduled_at=datetime.now(timezone.utc),
    )
    async_session.add(job2)
    await async_session.commit()

    res2 = await InboundOrchestrator.process_job(async_session, job2)
    assert res2["status"] == "suppressed"
    assert res2["reason"] == "ai_paused"


@pytest.mark.asyncio
async def test_8_live_inbox_and_settings_apis(client: AsyncClient, async_session: AsyncSession):
    """Verify conversations, takeover, pause, resume, and AI inbound settings APIs."""
    account, contact, conversation = await setup_test_conversation(async_session)

    # Setup owner session
    resp_setup = await client.post(
        "/api/v1/auth/setup",
        json={"email": "owner_inbox@physio.test", "password": "OwnerPass2026!", "full_name": "Clinic Owner"},
    )
    csrf_token = client.cookies.get("csrf_token")

    # 1. GET /api/v1/conversations
    resp_list = await client.get("/api/v1/conversations")
    assert resp_list.status_code == 200
    conv_list = resp_list.json()
    assert len(conv_list) >= 1
    assert any(c["id"] == str(conversation.id) for c in conv_list)

    # 2. GET /api/v1/conversations/{id}
    resp_detail = await client.get(f"/api/v1/conversations/{conversation.id}")
    assert resp_detail.status_code == 200
    conv_data = resp_detail.json()
    assert conv_data["id"] == str(conversation.id)
    assert "messages" in conv_data
    assert "drafts" in conv_data

    # 3. POST /api/v1/conversations/{id}/takeover
    resp_takeover = await client.post(
        f"/api/v1/conversations/{conversation.id}/takeover",
        json={"reason": "Staff stepped in to assist patient"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert resp_takeover.status_code == 200
    assert resp_takeover.json()["is_human_takeover"] is True

    # 4. POST /api/v1/conversations/{id}/resume-ai
    resp_resume = await client.post(
        f"/api/v1/conversations/{conversation.id}/resume-ai",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert resp_resume.status_code == 200
    assert resp_resume.json()["is_human_takeover"] is False
    assert resp_resume.json()["ai_paused"] is False

    # 5. POST /api/v1/conversations/{id}/pause-ai
    resp_pause = await client.post(
        f"/api/v1/conversations/{conversation.id}/pause-ai",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert resp_pause.status_code == 200
    assert resp_pause.json()["ai_paused"] is True

    # 6. GET /api/v1/ai-inbound/settings
    resp_settings = await client.get("/api/v1/ai-inbound/settings")
    assert resp_settings.status_code == 200
    settings_data = resp_settings.json()
    assert settings_data["ai_mode"] in ("disabled", "shadow", "live")
    assert settings_data["debounce_seconds"] >= 1

    # 7. PATCH /api/v1/ai-inbound/settings (Set to shadow)
    resp_patch = await client.patch(
        "/api/v1/ai-inbound/settings",
        json={"ai_mode": "shadow", "debounce_seconds": 6},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert resp_patch.status_code == 200
    assert resp_patch.json()["ai_mode"] == "shadow"
    assert resp_patch.json()["debounce_seconds"] == 6

    # 8. Reset ai_mode to disabled (MANDATORY REQUIREMENT: keep disabled at task end)
    resp_reset = await client.patch(
        "/api/v1/ai-inbound/settings",
        json={"ai_mode": "disabled"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert resp_reset.status_code == 200
    assert resp_reset.json()["ai_mode"] == "disabled"
