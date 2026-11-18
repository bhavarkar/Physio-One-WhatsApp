"""Durable Inbound Queue & Message Debouncer Service.

Single Organization Edition: Physio One Clinic.
Provides durable PostgreSQL queue tracking for inbound messages, debouncing burst
messages into a single conversational turn, worker locking, and Cloud Tasks dispatching.
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, or_
from sqlalchemy.orm import selectinload

from app.models.inbound import InboundProcessingJob, AIInboundSettings
from app.models.whatsapp import Conversation, WhatsAppContact, WhatsAppMessage, WhatsAppAccount

logger = logging.getLogger("physio_one.inbound.queue")


class InboundQueueService:
    """Manages persistent queuing and debouncing of inbound WhatsApp messages."""

    @classmethod
    async def get_or_create_settings(
        cls,
        db: AsyncSession,
        account_id: Optional[uuid.UUID] = None,
    ) -> AIInboundSettings:
        """Fetch or initialize AI inbound settings.
        
        MANDATORY REQUIREMENT: Defaults strictly to ai_mode='disabled'.
        """
        stmt = select(AIInboundSettings)
        if account_id:
            stmt = stmt.where(AIInboundSettings.account_id == account_id)
        else:
            stmt = stmt.order_by(AIInboundSettings.created_at.asc())

        settings = (await db.execute(stmt)).scalars().first()
        if not settings:
            settings = AIInboundSettings(
                account_id=account_id,
                ai_mode="disabled",  # Strict default
                debounce_seconds=5,
                max_ai_steps=5,
                processing_timeout_seconds=60,
                opt_out_keywords=["stop", "unsubscribe", "cancel messages", "optout", "opt out"],
                emergency_keywords=["emergency", "ambulance", "severe pain", "bleeding", "chest pain", "unconscious"],
                is_active=True,
            )
            db.add(settings)
            await db.flush()
        return settings

    @classmethod
    async def enqueue_inbound_message(
        cls,
        db: AsyncSession,
        message: WhatsAppMessage,
        conversation: Conversation,
        contact: WhatsAppContact,
    ) -> InboundProcessingJob:
        """Enqueue an inbound message, debouncing bursts for the same conversation."""
        now = datetime.now(timezone.utc)
        settings = await cls.get_or_create_settings(db)
        debounce_delta = timedelta(seconds=max(1, settings.debounce_seconds))

        # Check for active job in pending/debouncing state for this conversation
        stmt = select(InboundProcessingJob).where(
            InboundProcessingJob.conversation_id == conversation.id,
            InboundProcessingJob.status.in_(["pending", "debouncing"]),
        ).order_by(InboundProcessingJob.created_at.desc())
        
        job = (await db.execute(stmt)).scalars().first()
        msg_id_str = str(message.id)
        msg_text = (message.body or "").strip()

        if job:
            # Aggregate into existing burst job
            existing_ids = list(job.aggregated_message_ids or [])
            if msg_id_str not in existing_ids:
                existing_ids.append(msg_id_str)
                job.aggregated_message_ids = existing_ids
            
            if msg_text:
                if job.aggregated_text:
                    job.aggregated_text = f"{job.aggregated_text}\n{msg_text}"
                else:
                    job.aggregated_text = msg_text
            
            job.debounce_until = now + debounce_delta
            job.status = "debouncing"
            logger.info(
                "Aggregated message %s into active job %s for conversation %s. Debounce extended to %s",
                msg_id_str,
                job.id,
                conversation.id,
                job.debounce_until,
            )
        else:
            # Create new job
            job = InboundProcessingJob(
                conversation_id=conversation.id,
                contact_id=contact.id,
                provider=message.provider,
                status="debouncing",
                aggregated_message_ids=[msg_id_str],
                aggregated_text=msg_text,
                debounce_until=now + debounce_delta,
                scheduled_at=now,
                attempt_count=0,
            )
            db.add(job)
            await db.flush()
            logger.info(
                "Created new inbound job %s for conversation %s. Debounce until %s",
                job.id,
                conversation.id,
                job.debounce_until,
            )

        return job

    @classmethod
    async def fetch_and_lock_due_jobs(
        cls,
        db: AsyncSession,
        limit: int = 10,
        worker_id: Optional[str] = None,
    ) -> List[InboundProcessingJob]:
        """Fetch and lock jobs whose debounce period has passed."""
        now = datetime.now(timezone.utc)
        wid = worker_id or f"worker_{uuid.uuid4()}"
        lock_expiry = now + timedelta(seconds=120)

        stmt = (
            select(InboundProcessingJob)
            .options(
                selectinload(InboundProcessingJob.conversation),
                selectinload(InboundProcessingJob.contact),
            )
            .where(
                InboundProcessingJob.status.in_(["pending", "debouncing"]),
                InboundProcessingJob.debounce_until <= now,
                or_(
                    InboundProcessingJob.locked_until.is_(None),
                    InboundProcessingJob.locked_until < now,
                ),
            )
            .order_by(InboundProcessingJob.debounce_until.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        jobs = (await db.execute(stmt)).scalars().all()

        for j in jobs:
            j.status = "processing"
            j.locked_by = wid
            j.locked_until = lock_expiry
            j.attempt_count += 1

        if jobs:
            await db.commit()
            for j in jobs:
                await db.refresh(j)

        return list(jobs)

    @classmethod
    async def release_job_lock(
        cls,
        db: AsyncSession,
        job_id: uuid.UUID,
        new_status: str = "completed",
        error_message: Optional[str] = None,
    ) -> None:
        """Mark job completion or failure and clear worker lock."""
        stmt = (
            update(InboundProcessingJob)
            .where(InboundProcessingJob.id == job_id)
            .values(
                status=new_status,
                locked_by=None,
                locked_until=None,
                error_message=error_message,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await db.execute(stmt)
        await db.commit()
