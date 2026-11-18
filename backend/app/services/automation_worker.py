"""Durable PostgreSQL-backed Worker Service for Scheduled Automations.

Single Organization Edition: Physio One Clinic.
Governs worker leasing, lease expiry recovery, eligibility revalidation,
template rendering, outbound dispatch, retry backoff, dead-letter handling,
and delivery state tracking.
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, or_, and_, func
from sqlalchemy.orm import selectinload

from app.models.followup import (
    AutomationRule,
    AutomationScheduledJob,
    AutomationExecutionLog,
    AutomationSuppressionLog,
    AutomationSettings,
    AutomationMessageTemplate,
    AutomationContactCooldown,
)
from app.models.whatsapp import Conversation, WhatsAppContact, WhatsAppMessage, WhatsAppAccount
from app.models.patient import Patient, Appointment
from app.services.business_hours_service import get_tz, DEFAULT_TIMEZONE
from app.services.template_service import TemplateService, MissingTemplateVariableError, UnapprovedTemplateError
from app.services.eligibility_service import EligibilityService, EligibilityResult
from app.services.automation_service import AutomationService
from app.services.whatsapp_service import send_outbound_text_message, get_active_account_by_provider
from app.providers.base import OutboundSendResult, MessageStatus

logger = logging.getLogger("physio_one.automation.worker")


class AutomationWorkerService:
    """Orchestrates durable background execution of scheduled automation jobs."""

    @classmethod
    async def recover_expired_leases(cls, db: AsyncSession, lease_timeout_seconds: int = 120) -> int:
        """Find jobs stuck in 'processing' whose lease has expired and recover them."""
        now_utc = datetime.now(timezone.utc)
        stmt = select(AutomationScheduledJob).where(
            AutomationScheduledJob.status == "processing",
            AutomationScheduledJob.locked_until.is_not(None),
            AutomationScheduledJob.locked_until < now_utc,
        )
        expired_jobs = (await db.execute(stmt)).scalars().all()
        recovered = 0
        for job in expired_jobs:
            logger.warning("Recovering expired worker lease on job %s (locked by %s)", job.id, job.locked_by)
            job.status = "retrying"
            job.locked_by = None
            job.locked_until = None
            recovered += 1

        if recovered > 0:
            await db.commit()
        return recovered

    @classmethod
    async def fetch_and_lock_due_jobs(
        cls,
        db: AsyncSession,
        limit: int = 20,
        worker_id: Optional[str] = None,
        lease_seconds: int = 120,
        now: Optional[datetime] = None,
    ) -> List[AutomationScheduledJob]:
        """Fetch and lock scheduled jobs due for execution."""
        cur_now = now or datetime.now(timezone.utc)
        wid = worker_id or f"worker_{uuid.uuid4().hex[:8]}"
        lease_expiry = cur_now + timedelta(seconds=lease_seconds)

        stmt = (
            select(AutomationScheduledJob)
            .options(
                selectinload(AutomationScheduledJob.rule),
                selectinload(AutomationScheduledJob.contact),
                selectinload(AutomationScheduledJob.conversation),
                selectinload(AutomationScheduledJob.appointment),
                selectinload(AutomationScheduledJob.patient),
                selectinload(AutomationScheduledJob.template),
            )
            .where(
                AutomationScheduledJob.status.in_(["scheduled", "queued", "eligible", "retrying"]),
                AutomationScheduledJob.scheduled_for <= cur_now,
                or_(
                    AutomationScheduledJob.locked_until.is_(None),
                    AutomationScheduledJob.locked_until < cur_now,
                ),
            )
            .order_by(AutomationScheduledJob.scheduled_for.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        jobs = (await db.execute(stmt)).scalars().all()

        for j in jobs:
            j.status = "processing"
            j.locked_by = wid
            j.locked_until = lease_expiry
            j.attempt_count += 1
            j.last_attempt_at = cur_now

        if jobs:
            await db.commit()
            for j in jobs:
                await db.refresh(j)

        return list(jobs)

    @classmethod
    async def process_single_job(
        cls,
        db: AsyncSession,
        job: AutomationScheduledJob,
        settings: AutomationSettings,
        mock_dispatcher: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Process a locked automation job through eligibility, rendering, and dispatch."""
        now_utc = datetime.now(timezone.utc)
        job_id = job.id
        contact_id = job.contact_id
        rule_id = job.rule_id
        automation_type = job.automation_type
        attempt_count = job.attempt_count
        rule_retry = job.rule.retry_policy if job.rule else None
        default_max_retries = settings.max_retries
        result = {
            "job_id": str(job.id),
            "status": "unprocessed",
            "reason": None,
            "provider_message_id": None,
        }

        try:
            # 1. Eligibility & Safety Re-evaluation
            eligibility = await EligibilityService.evaluate_job_eligibility(
                db, job, settings, job.rule, now=now_utc
            )

            if eligibility.should_reschedule and eligibility.next_eligible_time:
                # Outside business hours or in quiet hours: shift to next eligible time
                job.scheduled_for = eligibility.next_eligible_time
                job.status = "scheduled"
                job.locked_by = None
                job.locked_until = None
                db.add(
                    AutomationExecutionLog(
                        job_id=job.id,
                        rule_id=job.rule_id,
                        contact_id=job.contact_id,
                        automation_type=job.automation_type,
                        action="rescheduled_business_hours",
                        status_before="processing",
                        status_after="scheduled",
                        details={"new_scheduled_for": eligibility.next_eligible_time.isoformat()},
                    )
                )
                await db.commit()
                result["status"] = "rescheduled"
                result["reason"] = "outside_business_hours"
                return result

            if not eligibility.eligible:
                # Suppressed by one of the safety gates
                await EligibilityService.record_suppression(
                    db, job, eligibility.suppression_reason, eligibility.details
                )
                job.locked_by = None
                job.locked_until = None
                db.add(
                    AutomationExecutionLog(
                        job_id=job.id,
                        rule_id=job.rule_id,
                        contact_id=job.contact_id,
                        automation_type=job.automation_type,
                        action="suppressed",
                        status_before="processing",
                        status_after="suppressed",
                        details={"suppression_reason": eligibility.suppression_reason, **(eligibility.details or {})},
                    )
                )
                await db.commit()
                result["status"] = "suppressed"
                result["reason"] = eligibility.suppression_reason
                return result

            # 2. Template / Message Rendering
            body_template: Optional[str] = None
            template_obj = job.template
            if template_obj:
                body_template = template_obj.body
            elif job.rule and job.rule.fallback_body:
                body_template = job.rule.fallback_body
            elif job.rendered_message:
                body_template = job.rendered_message

            if not body_template:
                # Default fallback copy based on automation type
                if job.automation_type == "appointment_reminder":
                    body_template = "Hello {{patient_name}}, this is a reminder of your appointment at {{clinic_name}} on {{appointment_date}} at {{appointment_time}} with {{practitioner_name}}."
                elif job.automation_type == "inactivity_followup":
                    body_template = "Hello {{patient_name}}, would you like help with your appointment inquiry at {{clinic_name}}?"
                elif job.automation_type == "appointment_followup":
                    body_template = "Hello {{patient_name}}, thank you for visiting {{clinic_name}} today. How are you feeling after your consultation?"
                elif job.automation_type == "noshow_followup":
                    body_template = "Hello {{patient_name}}, we missed you today at {{clinic_name}}. Would you like to reschedule your consultation?"
                else:
                    body_template = "Hello {{patient_name}}, message from {{clinic_name}}."

            # Construct template context
            contact = job.contact or await db.get(WhatsAppContact, job.contact_id)
            patient_name = "Patient"
            if job.patient:
                patient_name = job.patient.full_name
            elif contact and contact.profile_name:
                patient_name = contact.profile_name

            tz = get_tz((job.rule.timezone if job.rule else None) or settings.default_timezone)

            appt_date_str = ""
            appt_time_str = ""
            practitioner_name = "Dr. Physio One"
            service_type = "Physiotherapy Assessment"

            if job.appointment:
                appt_local = job.appointment.start_time.astimezone(tz)
                appt_date_str = appt_local.strftime("%A, %d %B %Y")
                appt_time_str = appt_local.strftime("%I:%M %p")
                practitioner_name = job.appointment.practitioner_name or practitioner_name
                service_type = job.appointment.service_type or service_type

            variables: Dict[str, Any] = {
                "patient_name": patient_name,
                "clinic_name": "Physio One Clinic",
                "appointment_date": appt_date_str,
                "appointment_time": appt_time_str,
                "practitioner_name": practitioner_name,
                "service_type": service_type,
                "notes": job.payload.get("notes", ""),
                **(job.payload.get("variables", {})),
            }

            try:
                rendered_text = TemplateService.render(
                    body_template, variables, template_obj.name if template_obj else "inline"
                )
            except MissingTemplateVariableError as mve:
                logger.error("Template rendering failed for job %s: %s", job.id, mve)
                await EligibilityService.record_suppression(
                    db, job, "missing_template_variable", {"missing": mve.missing_variables}
                )
                job.locked_by = None
                job.locked_until = None
                await db.commit()
                result["status"] = "suppressed"
                result["reason"] = "missing_template_variable"
                return result

            job.rendered_message = rendered_text

            # 3. Shadow / Test Mode Check
            is_test_mode = job.payload.get("test_mode") is True
            if is_test_mode and not mock_dispatcher:
                test_msg_id = f"test_{uuid.uuid4().hex[:12]}"
                job.status = "sent"
                job.provider_message_id = test_msg_id
                job.completed_at = now_utc
                job.locked_by = None
                job.locked_until = None
                db.add(
                    AutomationExecutionLog(
                        job_id=job.id,
                        rule_id=job.rule_id,
                        contact_id=job.contact_id,
                        automation_type=job.automation_type,
                        action="dispatched_shadow_mode",
                        status_before="processing",
                        status_after="sent",
                        provider=job.provider,
                        provider_message_id=test_msg_id,
                        details={"test_mode": True, "rendered_text": rendered_text},
                    )
                )
                await db.commit()
                result["status"] = "sent"
                result["provider_message_id"] = test_msg_id
                return result

            # 4. Outbound Dispatch
            clean_phone = contact.wa_id if contact else ""
            provider_msg_id: Optional[str] = None
            dispatch_status = "sent"

            if mock_dispatcher:
                # Used in tests or custom mock inject
                dispatch_res = await mock_dispatcher(
                    to=clean_phone,
                    text=rendered_text,
                    template_name=template_obj.name if template_obj else None,
                    job=job,
                )
                if isinstance(dispatch_res, dict):
                    provider_msg_id = dispatch_res.get("provider_message_id")
                    if dispatch_res.get("status") == "unknown_delivery":
                        dispatch_status = "unknown_delivery"
                elif hasattr(dispatch_res, "provider_message_id"):
                    provider_msg_id = dispatch_res.provider_message_id
            else:
                # Real Dispatch via WhatsApp Service
                send_res = await send_outbound_text_message(
                    db=db,
                    to_phone=clean_phone,
                    text=rendered_text,
                    provider_override=job.provider if job.provider != "any" else None,
                )
                provider_msg_id = send_res.provider_message_id

            if dispatch_status == "unknown_delivery":
                # Provider timed out with uncertain outcome: do NOT immediately retry
                job.status = "unknown_delivery"
                job.locked_by = None
                job.locked_until = None
                db.add(
                    AutomationExecutionLog(
                        job_id=job.id,
                        rule_id=job.rule_id,
                        contact_id=job.contact_id,
                        automation_type=job.automation_type,
                        action="unknown_delivery_timeout",
                        status_before="processing",
                        status_after="unknown_delivery",
                        provider=job.provider,
                        details={"message": "Provider request timed out; outcome uncertain. Blind retry suppressed."},
                    )
                )
                await db.commit()
                result["status"] = "unknown_delivery"
                result["reason"] = "provider_timeout"
                return result

            # Successful send
            provider_msg_id = provider_msg_id or f"outbound_auto_{uuid.uuid4().hex[:12]}"
            job.status = "sent"
            job.provider_message_id = provider_msg_id
            job.completed_at = now_utc
            job.locked_by = None
            job.locked_until = None

            # Record cooldown
            cooldown_hours = job.rule.cooldown_hours if job.rule else settings.default_cooldown_hours
            cooldown_expires = now_utc + timedelta(hours=cooldown_hours)
            cooldown_entry = AutomationContactCooldown(
                contact_id=job.contact_id,
                automation_type=job.automation_type,
                last_sent_at=now_utc,
                expires_at=cooldown_expires,
            )
            db.add(cooldown_entry)

            db.add(
                AutomationExecutionLog(
                    job_id=job.id,
                    rule_id=job.rule_id,
                    contact_id=job.contact_id,
                    automation_type=job.automation_type,
                    action="dispatched",
                    status_before="processing",
                    status_after="sent",
                    provider=job.provider,
                    provider_message_id=provider_msg_id,
                    details={"rendered_message": rendered_text, "cooldown_until": cooldown_expires.isoformat()},
                )
            )
            await db.commit()
            result["status"] = "sent"
            result["provider_message_id"] = provider_msg_id
            return result

        except Exception as exc:
            logger.exception("Error processing automation job %s: %s", job_id, exc)

            # Retry handling with exponential backoff
            retry_policy = rule_retry or {"max_retries": 3, "backoff_minutes": 5}
            max_retries = retry_policy.get("max_retries", default_max_retries)
            backoff_base = retry_policy.get("backoff_minutes", 5)

            job.locked_by = None
            job.locked_until = None
            if attempt_count < max_retries:
                backoff_mins = backoff_base * (2 ** max(0, attempt_count - 1))
                next_retry = now_utc + timedelta(minutes=backoff_mins)
                job.next_retry_at = next_retry
                job.scheduled_for = next_retry
                job.status = "retrying"
                action_name = "retry_scheduled"
            else:
                job.status = "failed"
                job.completed_at = now_utc
                action_name = "dead_letter_failed"

            db.add(
                AutomationExecutionLog(
                    job_id=job.id,
                    rule_id=job.rule_id,
                    contact_id=job.contact_id,
                    automation_type=job.automation_type,
                    action=action_name,
                    status_before="processing",
                    status_after=job.status,
                    provider=job.provider,
                    details={"error": str(exc), "attempt_count": attempt_count, "max_attempts": max_retries},
                )
            )
            await db.commit()
            result["status"] = job.status
            result["reason"] = str(exc)
            return result

    @classmethod
    async def run_worker_cycle(
        cls,
        db: AsyncSession,
        worker_id: Optional[str] = None,
        limit: int = 20,
        mock_dispatcher: Optional[Any] = None,
    ) -> Dict[str, int]:
        """Execute one complete durable worker cycle."""
        await AutomationService.ensure_default_templates_and_rules(db)
        settings = await AutomationService.get_or_create_settings(db)

        # 1. Recover expired leases
        recovered = await cls.recover_expired_leases(db, lease_timeout_seconds=120)

        # 2. Run 15-minute inactivity scan
        await AutomationService.scan_and_schedule_inactivity_followups(db)

        # 3. Fetch and lock due jobs
        locked_jobs = await cls.fetch_and_lock_due_jobs(db, limit=limit, worker_id=worker_id)

        stats = {
            "processed_count": len(locked_jobs),
            "dispatched_count": 0,
            "suppressed_count": 0,
            "rescheduled_count": 0,
            "failed_count": 0,
            "recovered_leases_count": recovered,
        }

        # 4. Process each job
        for job in locked_jobs:
            res = await cls.process_single_job(db, job, settings, mock_dispatcher=mock_dispatcher)
            st = res.get("status")
            if st == "sent":
                stats["dispatched_count"] += 1
            elif st == "suppressed":
                stats["suppressed_count"] += 1
            elif st == "rescheduled":
                stats["rescheduled_count"] += 1
            elif st in ["failed", "retrying"]:
                stats["failed_count"] += 1

        return stats
