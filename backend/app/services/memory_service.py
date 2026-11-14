"""Patient Memory and Conversation Context Service.

Single Organization Edition: Physio One Clinic.
Enforces strict patient memory isolation: contact-scoped memories are never exposed
across patients or in general clinic FAQ search.
"""
import uuid
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

from app.models.memory import ConversationMemory, ConversationSummary
from app.models.whatsapp import WhatsAppMessage, Conversation
from app.llm.schemas import ChatMessage, MessageRole


class MemoryService:
    """Service managing short-term conversation turns and persistent patient-scoped memories."""

    # -------------------------------------------------------------------------
    # A. Short-Term Conversation Memory
    # -------------------------------------------------------------------------

    @classmethod
    async def load_conversation_history(
        cls,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        max_messages: int = 10,
        max_chars: int = 4000,
    ) -> List[ChatMessage]:
        """Load recent chronological turns from WhatsApp message history."""
        stmt = (
            select(WhatsAppMessage)
            .where(
                and_(
                    WhatsAppMessage.conversation_id == conversation_id,
                    WhatsAppMessage.message_type.in_(["text", "interactive"]),
                )
            )
            .order_by(desc(WhatsAppMessage.created_at))
            .limit(max_messages)
        )
        recent_messages = list((await db.execute(stmt)).scalars().all())
        # Reverse to chronological order (oldest to newest)
        recent_messages.reverse()

        chat_turns: List[ChatMessage] = []
        total_chars = 0

        for msg in recent_messages:
            content = msg.body or ""
            if not content.strip():
                continue

            role = MessageRole.USER if msg.direction == "inbound" else MessageRole.ASSISTANT
            if total_chars + len(content) > max_chars:
                break

            chat_turns.append(ChatMessage(role=role, content=content))
            total_chars += len(content)

        return chat_turns

    # -------------------------------------------------------------------------
    # B. Persistent Contact Memory (Isolated by contact_id)
    # -------------------------------------------------------------------------

    @classmethod
    async def store_contact_memory(
        cls,
        db: AsyncSession,
        contact_id: uuid.UUID,
        content: str,
        memory_type: str = "preference",
        conversation_id: Optional[uuid.UUID] = None,
        source_message_id: Optional[uuid.UUID] = None,
        confidence_score: float = 1.0,
    ) -> ConversationMemory:
        """Save a durable fact or preference strictly scoped to a contact."""
        clean_content = content.strip()
        if not clean_content:
            raise ValueError("Memory content cannot be empty.")

        mem = ConversationMemory(
            contact_id=contact_id,
            conversation_id=conversation_id,
            memory_type=memory_type,
            content=clean_content,
            confidence_score=confidence_score,
            is_active=True,
            source_message_id=source_message_id,
        )
        db.add(mem)
        await db.commit()
        await db.refresh(mem)
        return mem

    @classmethod
    async def list_contact_memories(
        cls,
        db: AsyncSession,
        contact_id: uuid.UUID,
        active_only: bool = True,
    ) -> List[ConversationMemory]:
        """Retrieve memories strictly belonging to the specified contact."""
        stmt = select(ConversationMemory).where(ConversationMemory.contact_id == contact_id)
        if active_only:
            stmt = stmt.where(ConversationMemory.is_active == True)
        stmt = stmt.order_by(ConversationMemory.created_at.desc())
        return list((await db.execute(stmt)).scalars().all())

    @classmethod
    async def delete_contact_memory(
        cls,
        db: AsyncSession,
        memory_id: uuid.UUID,
        contact_id: Optional[uuid.UUID] = None,
    ) -> bool:
        """Delete or deactivate a memory, optionally verifying contact ownership."""
        stmt = select(ConversationMemory).where(ConversationMemory.id == memory_id)
        if contact_id:
            stmt = stmt.where(ConversationMemory.contact_id == contact_id)

        mem = (await db.execute(stmt)).scalar_one_or_none()
        if not mem:
            return False

        await db.delete(mem)
        await db.commit()
        return True

    @classmethod
    async def build_patient_memory_context(
        cls,
        db: AsyncSession,
        contact_id: uuid.UUID,
        max_memories: int = 5,
    ) -> str:
        """Format authorized contact memories for agent context without cross-patient leakage."""
        memories = await cls.list_contact_memories(db, contact_id, active_only=True)
        if not memories:
            return ""

        lines = ["=== PATIENT SPECIFIC PREFERENCES & NOTES (STRICTLY ISOLATED) ==="]
        for m in memories[:max_memories]:
            lines.append(f"- [{m.memory_type.upper()}] {m.content}")
        lines.append("================================================================")
        return "\n".join(lines)
