"""Tests for Short-Term Conversation Context and Persistent Patient Memory Isolation."""
import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.whatsapp import WhatsAppContact, Conversation, WhatsAppMessage
from app.services.memory_service import MemoryService
from app.llm.schemas import MessageRole


@pytest.mark.asyncio
async def test_short_term_conversation_memory(async_session: AsyncSession):
    # Setup test contact & conversation
    contact = WhatsAppContact(
        wa_id="919876543210",
        profile_name="John Patient",
    )
    async_session.add(contact)
    await async_session.flush()

    conv = Conversation(
        contact_id=contact.id,
        status="active",
    )
    async_session.add(conv)
    await async_session.flush()

    # Create 3 messages (2 inbound, 1 outbound)
    m1 = WhatsAppMessage(
        conversation_id=conv.id,
        contact_id=contact.id,
        provider="meta",
        provider_message_id=str(uuid.uuid4()),
        direction="inbound",
        message_type="text",
        body="Hi, I have knee pain after running.",
    )
    m2 = WhatsAppMessage(
        conversation_id=conv.id,
        contact_id=contact.id,
        provider="meta",
        provider_message_id=str(uuid.uuid4()),
        direction="outbound",
        message_type="text",
        body="Hello John! Physio One can assist with sports injury rehabilitation.",
    )
    m3 = WhatsAppMessage(
        conversation_id=conv.id,
        contact_id=contact.id,
        provider="meta",
        provider_message_id=str(uuid.uuid4()),
        direction="inbound",
        message_type="text",
        body="Do you have an appointment available tomorrow?",
    )
    async_session.add_all([m1, m2, m3])
    await async_session.commit()

    # Load history
    turns = await MemoryService.load_conversation_history(async_session, conv.id, max_messages=10)
    assert len(turns) == 3
    # Verify chronological order
    assert turns[0].role == MessageRole.USER
    assert "knee pain" in turns[0].content
    assert turns[1].role == MessageRole.ASSISTANT
    assert "sports injury" in turns[1].content
    assert turns[2].role == MessageRole.USER
    assert "tomorrow" in turns[2].content


@pytest.mark.asyncio
async def test_patient_memory_isolation(async_session: AsyncSession):
    # Setup two distinct contacts
    contact_a = WhatsAppContact(
        wa_id="919876543211",
        profile_name="Patient Alice",
    )
    contact_b = WhatsAppContact(
        wa_id="919876543222",
        profile_name="Patient Bob",
    )
    async_session.add_all([contact_a, contact_b])
    await async_session.flush()

    # Store memory for Alice
    mem_a = await MemoryService.store_contact_memory(
        db=async_session,
        contact_id=contact_a.id,
        content="Patient prefers morning appointments before 11 AM due to work shift.",
        memory_type="appointment_preference",
    )

    # Store memory for Bob
    mem_b = await MemoryService.store_contact_memory(
        db=async_session,
        contact_id=contact_b.id,
        content="Allergic to latex therapy bands.",
        memory_type="clinical_note",
    )

    # Strict isolation check: Query Alice's memories
    alice_memories = await MemoryService.list_contact_memories(async_session, contact_a.id)
    assert len(alice_memories) == 1
    assert "morning appointments" in alice_memories[0].content
    # Bob's memory MUST NOT appear in Alice's list
    assert not any("latex" in m.content for m in alice_memories)

    # Query Bob's memories
    bob_memories = await MemoryService.list_contact_memories(async_session, contact_b.id)
    assert len(bob_memories) == 1
    assert "latex" in bob_memories[0].content
    # Alice's memory MUST NOT appear in Bob's list
    assert not any("morning" in m.content for m in bob_memories)

    # Format context for Alice
    alice_ctx = await MemoryService.build_patient_memory_context(async_session, contact_a.id)
    assert "morning appointments" in alice_ctx
    assert "latex" not in alice_ctx

    # Deletion test
    deleted = await MemoryService.delete_contact_memory(async_session, mem_a.id, contact_id=contact_a.id)
    assert deleted is True
    assert len(await MemoryService.list_contact_memories(async_session, contact_a.id)) == 0
