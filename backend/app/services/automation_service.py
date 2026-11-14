"""Core Scheduled Automation Engine and Event Orchestration.

Single Organization Edition: Physio One Clinic.
Governs appointment reminder creation/rescheduling/cancellation,
inactivity tracking, post-appointment follow-ups, missed appointment checks,
and staff-controlled individual scheduling.
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, or_, func
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
from app.models.whatsapp import Conversation, WhatsAppContact, WhatsAppMessage
from app.models.patient import Patient, Appointment
from app.models.user import User
from app.services.business_hours_service import calculate_next_eligible_send_time

logger = logging.getLogger("physio_one.automation.service")


class AutomationService:
    """Manages automation rules, job creation, cancellation, and event hooks."""

    @classmethod
    async def get_or_create_settings(cls, db: AsyncSession) -> AutomationSettings:
        """Fetch or initialize singleton global automation settings.
        
        MANDATORY REQUIREMENT: Defaults strictly to outbound_enabled=False.
        """
        stmt = select(AutomationSettings).order_by(AutomationSettings.created_at.asc())
        settings = (await db.execute(stmt)).scalars().first()
        if not settings:
            settings = AutomationSettings(
                outbound_enabled=False,  # Strict default
                default_timezone="Asia/Kolkata",
                quiet_hours_start="21:00",
                quiet_hours_end="09:00",
                business_hours_start="09:00",
                business_hours_end="20:00",
                worker_scan_interval_seconds=60,
                max_retries=3,
                default_cooldown_hours=24,
                rate_limit_per_minute=30,
                emergency_stop=False,
            )
            db.add(settings)
            await db.flush()
        return settings

    @classmethod
    async def ensure_default_templates_and_rules(cls, db: AsyncSession) -> None:
        """Seed default Physio One templates and rules in disabled state if not present."""
        # 1. Message Templates
        templates_def = [
            {
                "name": "appointment_reminder_24h",
                "category": "UTILITY",
                "body": "Hello {{patient_name}}, this is a reminder of your appointment at {{clinic_name}} on {{appointment_date}} at {{appointment_time}} with {{practitioner_name}}.",
                "variables": ["patient_name", "clinic_name", "appointment_date", "appointment_time", "practitioner_name"],
            },
            {
                "name": "appointment_reminder_2h",
                "category": "UTILITY",
                "body": "Hello {{patient_name}}, your appointment at {{clinic_name}} is in 2 hours ({{appointment_time}}). Please arrive 10 minutes early.",
                "variables": ["patient_name", "clinic_name", "appointment_time"],
            },
            {
                "name": "post_appointment_checkin",
                "category": "UTILITY",
                "body": "Hello {{patient_name}}, thank you for visiting {{clinic_name}} today. How are you feeling following your session with {{practitioner_name}}?",
                "variables": ["patient_name", "clinic_name", "practitioner_name"],
            },
            {
                "name": "missed_appointment_followup",
                "category": "UTILITY",
                "body": "Hello {{patient_name}}, we noticed you were unable to make your appointment today. Would you like to reschedule your session with {{practitioner_name}}?",
                "variables": ["patient_name", "practitioner_name"],
            },
            {
                "name": "inactivity_checkin_2h",
                "category": "UTILITY",
                "body": "Hello {{patient_name}}, would you like help with your appointment inquiry at {{clinic_name}}?",
                "variables": ["patient_name", "clinic_name"],
            },
            {
                "name": "inactivity_checkin_5h",
                "category": "UTILITY",
                "body": "Hello {{patient_name}}, our {{clinic_name}} team is available if you need any assistance with your physiotherapy consultation.",
                "variables": ["patient_name", "clinic_name"],
            },
        ]

        templates_map: Dict[str, AutomationMessageTemplate] = {}
        for t_data in templates_def:
            stmt = select(AutomationMessageTemplate).where(AutomationMessageTemplate.name == t_data["name"])
            existing = (await db.execute(stmt)).scalars().first()
            if not existing:
                existing = AutomationMessageTemplate(
                    name=t_data["name"],
                    provider="any",
                    language="en",
                    category=t_data["category"],
                    approval_status="APPROVED",
                    body=t_data["body"],
                    variables=t_data["variables"],
                    version=1,
                    is_active=True,
                )
                db.add(existing)
                await db.flush()
            templates_map[t_data["name"]] = existing

        # 2. Automation Rules (ALL DISABLED BY DEFAULT)
        rules_def = [
            {
                "name": "24h Appointment Reminder",
                "automation_type": "appointment_reminder",
                "trigger_event": "appointment_confirmed",
                "delay_minutes": -1440,  # 24h before
                "template_name": "appointment_reminder_24h",
            },
            {
                "name": "2h Appointment Reminder",
                "automation_type": "appointment_reminder",
                "trigger_event": "appointment_confirmed",
                "delay_minutes": -120,  # 2h before
                "template_name": "appointment_reminder_2h",
            },
            {
                "name": "Post-Appointment Follow-up",
                "automation_type": "appointment_followup",
                "trigger_event": "appointment_completed",
                "delay_minutes": 120,  # 2h after completion
                "template_name": "post_appointment_checkin",
            },
            {
                "name": "Missed Appointment Follow-up",
                "automation_type": "noshow_followup",
                "trigger_event": "appointment_noshow",
                "delay_minutes": 60,  # 1h after no-show
                "template_name": "missed_appointment_followup",
            },
            {
                "name": "2h Inactivity Check-in",
                "automation_type": "inactivity_followup",
                "trigger_event": "conversation_inactivity",
                "delay_minutes": 120,
                "template_name": "inactivity_checkin_2h",
            },
            {
                "name": "5h Inactivity Follow-up",
                "automation_type": "inactivity_followup",
                "trigger_event": "conversation_inactivity",
                "delay_minutes": 300,
                "template_name": "inactivity_checkin_5h",
            },
        ]

        for r_data in rules_def:
            stmt = select(AutomationRule).where(AutomationRule.name == r_data["name"])
            existing_rule = (await db.execute(stmt)).scalars().first()
            if not existing_rule:
                tmpl = templates_map.get(r_data["template_name"])
                rule = AutomationRule(
                    name=r_data["name"],
                    trigger_type=r_data["automation_type"],
                    condition_json={},
                    action_type="send_whatsapp_message",
                    is_enabled=False,  # MANDATORY DEFAULT: DISABLED
                    automation_type=r_data["automation_type"],
                    trigger_event=r_data["trigger_event"],
                    delay_minutes=r_data["delay_minutes"],
                    business_hours_only=True,
                    start_hour="09:00",
                    end_hour="20:00",
                    permitted_days=[1, 2, 3, 4, 5, 6],
                    timezone="Asia/Kolkata",
                    template_id=tmpl.id if tmpl else None,
                    provider="any",
                    max_sends_per_contact=1,
                    cooldown_hours=24,
                    retry_policy={"max_retries": 3, "backoff_minutes": 5},
                    eligibility_filters={},
                )
                db.add(rule)
                await db.flush()

    @classmethod
    async def handle_appointment_event(
        cls,
        db: AsyncSession,
        event_type: str,
        appointment: Appointment,
        user: Optional[User] = None,
    ) -> List[AutomationScheduledJob]:
        """Transactional event handler for appointment state mutations."""
        await cls.ensure_default_templates_and_rules(db)
        settings = await cls.get_or_create_settings(db)
        now_utc = datetime.now(timezone.utc)
        created_jobs: List[AutomationScheduledJob] = []

        # Find or load patient and contact
        patient = appointment.patient or await db.get(Patient, appointment.patient_id)
        if not patient:
            logger.warning("Appointment %s has no linked patient; skipping automation", appointment.id)
            return []

        contact: Optional[WhatsAppContact] = None
        if patient.contact_id:
            contact = await db.get(WhatsAppContact, patient.contact_id)
        if not contact and patient.phone_number:
            # Look up contact by phone number
            c_stmt = select(WhatsAppContact).where(WhatsAppContact.wa_id == patient.phone_number)
            contact = (await db.execute(c_stmt)).scalars().first()

        if not contact:
            logger.info("Patient %s has no WhatsApp contact record; skipping automation", patient.id)
            return []

        # Find active conversation if any
        conv_stmt = select(Conversation).where(
            Conversation.contact_id == contact.id,
            Conversation.status != "closed",
        ).order_by(Conversation.created_at.desc())
        conversation = (await db.execute(conv_stmt)).scalars().first()
        conv_id = conversation.id if conversation else None

        appt_start = appointment.start_time if appointment.start_time.tzinfo else appointment.start_time.replace(tzinfo=timezone.utc)

        # -------------------------------------------------------------------
        # Event A: Appointment Confirmed
        # -------------------------------------------------------------------
        if event_type == "appointment_confirmed":
            rules_stmt = select(AutomationRule).where(
                AutomationRule.automation_type == "appointment_reminder",
                AutomationRule.trigger_event == "appointment_confirmed",
                AutomationRule.is_enabled.is_(True),
            )
            active_rules = (await db.execute(rules_stmt)).scalars().all()

            for rule in active_rules:
                target_send = appt_start + timedelta(minutes=rule.delay_minutes)
                # Next eligible send time (respecting business/quiet hours)
                target_send = calculate_next_eligible_send_time(
                    target_send,
                    rule.start_hour,
                    rule.end_hour,
                    settings.quiet_hours_start,
                    settings.quiet_hours_end,
                    rule.permitted_days,
                    rule.timezone,
                )

                # If target send is already past the appointment start, don't schedule
                if target_send >= appt_start:
                    continue

                idempotency_key = f"appt_{appointment.id}_rule_{rule.id}"
                # Check for existing job
                existing_stmt = select(AutomationScheduledJob).where(
                    AutomationScheduledJob.idempotency_key == idempotency_key
                )
                existing = (await db.execute(existing_stmt)).scalars().first()
                if existing:
                    continue

                job = AutomationScheduledJob(
                    rule_id=rule.id,
                    automation_type=rule.automation_type,
                    contact_id=contact.id,
                    conversation_id=conv_id,
                    appointment_id=appointment.id,
                    patient_id=patient.id,
                    scheduled_for=target_send,
                    status="scheduled",
                    template_id=rule.template_id,
                    provider=rule.provider,
                    idempotency_key=idempotency_key,
                    created_by_user_id=user.id if user else None,
                    payload={
                        "practitioner_name": appointment.practitioner_name,
                        "service_type": appointment.service_type,
                        "appointment_start": appt_start.isoformat(),
                    },
                )
                db.add(job)
                await db.flush()

                exec_log = AutomationExecutionLog(
                    job_id=job.id,
                    rule_id=rule.id,
                    contact_id=contact.id,
                    automation_type=rule.automation_type,
                    action="scheduled",
                    status_before=None,
                    status_after="scheduled",
                    details={"scheduled_for": target_send.isoformat(), "event": event_type},
                )
                db.add(exec_log)
                created_jobs.append(job)

        # -------------------------------------------------------------------
        # Event B: Appointment Rescheduled
        # -------------------------------------------------------------------
        elif event_type == "appointment_rescheduled":
            # 1. Cancel pending reminder jobs for this appointment
            pending_stmt = select(AutomationScheduledJob).where(
                AutomationScheduledJob.appointment_id == appointment.id,
                AutomationScheduledJob.status.in_(["scheduled", "queued", "eligible", "processing", "retrying"]),
            )
            pending_jobs = (await db.execute(pending_stmt)).scalars().all()
            for p_job in pending_jobs:
                p_job.status = "cancelled"
                p_job.suppression_reason = "appointment_rescheduled"
                p_job.completed_at = now_utc
                db.add(
                    AutomationExecutionLog(
                        job_id=p_job.id,
                        rule_id=p_job.rule_id,
                        contact_id=contact.id,
                        automation_type=p_job.automation_type,
                        action="cancelled",
                        status_before="scheduled",
                        status_after="cancelled",
                        details={"reason": "Appointment was rescheduled to a new time."},
                    )
                )

            # 2. Schedule reminders for the new appointment time
            rules_stmt = select(AutomationRule).where(
                AutomationRule.automation_type == "appointment_reminder",
                AutomationRule.trigger_event == "appointment_confirmed",
                AutomationRule.is_enabled.is_(True),
            )
            active_rules = (await db.execute(rules_stmt)).scalars().all()
            resched_token = int(now_utc.timestamp())

            for rule in active_rules:
                target_send = appt_start + timedelta(minutes=rule.delay_minutes)
                target_send = calculate_next_eligible_send_time(
                    target_send,
                    rule.start_hour,
                    rule.end_hour,
                    settings.quiet_hours_start,
                    settings.quiet_hours_end,
                    rule.permitted_days,
                    rule.timezone,
                )
                if target_send >= appt_start:
                    continue

                idempotency_key = f"appt_{appointment.id}_rule_{rule.id}_resched_{resched_token}"
                job = AutomationScheduledJob(
                    rule_id=rule.id,
                    automation_type=rule.automation_type,
                    contact_id=contact.id,
                    conversation_id=conv_id,
                    appointment_id=appointment.id,
                    patient_id=patient.id,
                    scheduled_for=target_send,
                    status="scheduled",
                    template_id=rule.template_id,
                    provider=rule.provider,
                    idempotency_key=idempotency_key,
                    created_by_user_id=user.id if user else None,
                    payload={
                        "practitioner_name": appointment.practitioner_name,
                        "service_type": appointment.service_type,
                        "appointment_start": appt_start.isoformat(),
                        "rescheduled": True,
                    },
                )
                db.add(job)
                await db.flush()

                db.add(
                    AutomationExecutionLog(
                        job_id=job.id,
                        rule_id=rule.id,
                        contact_id=contact.id,
                        automation_type=rule.automation_type,
                        action="scheduled",
                        status_before=None,
                        status_after="scheduled",
                        details={"scheduled_for": target_send.isoformat(), "event": "appointment_rescheduled"},
                    )
                )
                created_jobs.append(job)

        # -------------------------------------------------------------------
        # Event C: Appointment Cancelled
        # -------------------------------------------------------------------
        elif event_type == "appointment_cancelled":
            pending_stmt = select(AutomationScheduledJob).where(
                AutomationScheduledJob.appointment_id == appointment.id,
                AutomationScheduledJob.status.in_(["scheduled", "queued", "eligible", "processing", "retrying"]),
            )
            pending_jobs = (await db.execute(pending_stmt)).scalars().all()
            for p_job in pending_jobs:
                p_job.status = "cancelled"
                p_job.suppression_reason = "appointment_cancelled"
                p_job.completed_at = now_utc
                db.add(
                    AutomationExecutionLog(
                        job_id=p_job.id,
                        rule_id=p_job.rule_id,
                        contact_id=contact.id,
                        automation_type=p_job.automation_type,
                        action="cancelled",
                        status_before="scheduled",
                        status_after="cancelled",
                        details={"reason": "Appointment was cancelled."},
                    )
                )

        # -------------------------------------------------------------------
        # Event D: Appointment Completed (Follow-up)
        # -------------------------------------------------------------------
        elif event_type == "appointment_completed":
            rules_stmt = select(AutomationRule).where(
                AutomationRule.automation_type == "appointment_followup",
                AutomationRule.trigger_event == "appointment_completed",
                AutomationRule.is_enabled.is_(True),
            )
            active_rules = (await db.execute(rules_stmt)).scalars().all()
            for rule in active_rules:
                target_send = now_utc + timedelta(minutes=rule.delay_minutes)
                target_send = calculate_next_eligible_send_time(
                    target_send,
                    rule.start_hour,
                    rule.end_hour,
                    settings.quiet_hours_start,
                    settings.quiet_hours_end,
                    rule.permitted_days,
                    rule.timezone,
                )
                idempotency_key = f"appt_{appointment.id}_completed_rule_{rule.id}"
                existing = (await db.execute(select(AutomationScheduledJob).where(AutomationScheduledJob.idempotency_key == idempotency_key))).scalars().first()
                if existing:
                    continue

                job = AutomationScheduledJob(
                    rule_id=rule.id,
                    automation_type=rule.automation_type,
                    contact_id=contact.id,
                    conversation_id=conv_id,
                    appointment_id=appointment.id,
                    patient_id=patient.id,
                    scheduled_for=target_send,
                    status="scheduled",
                    template_id=rule.template_id,
                    provider=rule.provider,
                    idempotency_key=idempotency_key,
                    created_by_user_id=user.id if user else None,
                    payload={"practitioner_name": appointment.practitioner_name, "service_type": appointment.service_type},
                )
                db.add(job)
                await db.flush()
                db.add(
                    AutomationExecutionLog(
                        job_id=job.id,
                        rule_id=rule.id,
                        contact_id=contact.id,
                        automation_type=rule.automation_type,
                        action="scheduled",
                        status_before=None,
                        status_after="scheduled",
                        details={"scheduled_for": target_send.isoformat(), "event": "appointment_completed"},
                    )
                )
                created_jobs.append(job)

        # -------------------------------------------------------------------
        # Event E: Appointment Marked No-Show
        # -------------------------------------------------------------------
        elif event_type == "appointment_noshow":
            rules_stmt = select(AutomationRule).where(
                AutomationRule.automation_type == "noshow_followup",
                AutomationRule.trigger_event == "appointment_noshow",
                AutomationRule.is_enabled.is_(True),
            )
            active_rules = (await db.execute(rules_stmt)).scalars().all()
            for rule in active_rules:
                target_send = now_utc + timedelta(minutes=rule.delay_minutes)
                target_send = calculate_next_eligible_send_time(
                    target_send,
                    rule.start_hour,
                    rule.end_hour,
                    settings.quiet_hours_start,
                    settings.quiet_hours_end,
                    rule.permitted_days,
                    rule.timezone,
                )
                idempotency_key = f"appt_{appointment.id}_noshow_rule_{rule.id}"
                existing = (await db.execute(select(AutomationScheduledJob).where(AutomationScheduledJob.idempotency_key == idempotency_key))).scalars().first()
                if existing:
                    continue

                job = AutomationScheduledJob(
                    rule_id=rule.id,
                    automation_type=rule.automation_type,
                    contact_id=contact.id,
                    conversation_id=conv_id,
                    appointment_id=appointment.id,
                    patient_id=patient.id,
                    scheduled_for=target_send,
                    status="scheduled",
                    template_id=rule.template_id,
                    provider=rule.provider,
                    idempotency_key=idempotency_key,
                    created_by_user_id=user.id if user else None,
                    payload={"practitioner_name": appointment.practitioner_name, "service_type": appointment.service_type},
                )
                db.add(job)
                await db.flush()
                db.add(
                    AutomationExecutionLog(
                        job_id=job.id,
                        rule_id=rule.id,
                        contact_id=contact.id,
                        automation_type=rule.automation_type,
                        action="scheduled",
                        status_before=None,
                        status_after="scheduled",
                        details={"scheduled_for": target_send.isoformat(), "event": "appointment_noshow"},
                    )
                )
                created_jobs.append(job)

        await db.flush()
        return created_jobs

    @classmethod
    async def scan_and_schedule_inactivity_followups(
        cls,
        db: AsyncSession,
        now: Optional[datetime] = None,
    ) -> List[AutomationScheduledJob]:
        """Scan open conversations and schedule 2h / 5h follow-up jobs for inactive patients."""
        cur_now = now or datetime.now(timezone.utc)
        await cls.ensure_default_templates_and_rules(db)
        settings = await cls.get_or_create_settings(db)

        # Look for active inactivity rules
        rules_stmt = select(AutomationRule).where(
            AutomationRule.automation_type == "inactivity_followup",
            AutomationRule.is_enabled.is_(True),
        ).order_by(AutomationRule.delay_minutes.asc())
        rules = (await db.execute(rules_stmt)).scalars().all()
        if not rules:
            return []

        # Find open conversations not in human takeover or ai pause
        conv_stmt = (
            select(Conversation)
            .options(selectinload(Conversation.contact))
            .where(
                Conversation.status != "closed",
                Conversation.is_human_takeover.is_(False),
                Conversation.ai_paused.is_(False),
            )
        )
        conversations = (await db.execute(conv_stmt)).scalars().all()
        created_jobs: List[AutomationScheduledJob] = []

        for conv in conversations:
            contact = conv.contact
            if not contact or contact.opted_out_all:
                continue

            # Determine last inbound patient interaction timestamp
            last_inbound_stmt = select(func.max(WhatsAppMessage.created_at)).where(
                WhatsAppMessage.conversation_id == conv.id,
                WhatsAppMessage.direction == "inbound",
            )
            last_inbound = await db.scalar(last_inbound_stmt)
            if not last_inbound:
                continue

            last_inbound_utc = last_inbound if last_inbound.tzinfo else last_inbound.replace(tzinfo=timezone.utc)
            elapsed_minutes = (cur_now - last_inbound_utc).total_seconds() / 60.0

            for rule in rules:
                if elapsed_minutes >= rule.delay_minutes:
                    # Inactivity threshold reached (e.g. 120m for 2h or 300m for 5h)
                    # Check if patient replied after this threshold point
                    # Deterministic idempotency key per inbound turn & rule stage:
                    idempotency_key = f"inactivity_conv_{conv.id}_msg_{int(last_inbound_utc.timestamp())}_rule_{rule.id}"

                    existing = (
                        await db.execute(
                            select(AutomationScheduledJob).where(
                                AutomationScheduledJob.idempotency_key == idempotency_key
                            )
                        )
                    ).scalars().first()

                    if existing:
                        continue

                    # Target send time
                    target_send = cur_now
                    target_send = calculate_next_eligible_send_time(
                        target_send,
                        rule.start_hour,
                        rule.end_hour,
                        settings.quiet_hours_start,
                        settings.quiet_hours_end,
                        rule.permitted_days,
                        rule.timezone,
                    )

                    patient_id_stmt = select(Patient.id).where(Patient.contact_id == contact.id)
                    linked_patient_id = await db.scalar(patient_id_stmt)

                    job = AutomationScheduledJob(
                        rule_id=rule.id,
                        automation_type="inactivity_followup",
                        contact_id=contact.id,
                        conversation_id=conv.id,
                        patient_id=linked_patient_id,
                        scheduled_for=target_send,
                        status="scheduled",
                        template_id=rule.template_id,
                        provider=rule.provider,
                        idempotency_key=idempotency_key,
                        payload={
                            "inactivity_since": last_inbound_utc.isoformat(),
                            "stage_minutes": rule.delay_minutes,
                            "rule_name": rule.name,
                        },
                    )
                    db.add(job)
                    await db.flush()

                    db.add(
                        AutomationExecutionLog(
                            job_id=job.id,
                            rule_id=rule.id,
                            contact_id=contact.id,
                            automation_type="inactivity_followup",
                            action="scheduled",
                            status_before=None,
                            status_after="scheduled",
                            details={"inactivity_since": last_inbound_utc.isoformat(), "delay_minutes": rule.delay_minutes},
                        )
                    )
                    created_jobs.append(job)

        await db.flush()
        return created_jobs

    @classmethod
    async def schedule_staff_followup(
        cls,
        db: AsyncSession,
        contact_id: uuid.UUID,
        scheduled_for: datetime,
        reason: str,
        message_text: Optional[str] = None,
        template_id: Optional[uuid.UUID] = None,
        conversation_id: Optional[uuid.UUID] = None,
        appointment_id: Optional[uuid.UUID] = None,
        assigned_staff_id: Optional[uuid.UUID] = None,
        current_user: Optional[User] = None,
        provider: str = "any",
    ) -> AutomationScheduledJob:
        """Schedule an authorized staff-controlled individual follow-up."""
        contact = await db.get(WhatsAppContact, contact_id)
        if not contact:
            raise ValueError(f"Contact {contact_id} not found.")

        user_id = current_user.id if current_user else None
        now_utc = datetime.now(timezone.utc)
        send_time = scheduled_for if scheduled_for.tzinfo else scheduled_for.replace(tzinfo=timezone.utc)

        idempotency_key = f"staff_{contact_id}_{int(send_time.timestamp())}_{uuid.uuid4().hex[:8]}"

        patient_id_stmt = select(Patient.id).where(Patient.contact_id == contact.id)
        linked_patient_id = await db.scalar(patient_id_stmt)

        job = AutomationScheduledJob(
            rule_id=None,
            automation_type="staff_scheduled",
            contact_id=contact.id,
            conversation_id=conversation_id,
            appointment_id=appointment_id,
            patient_id=linked_patient_id,
            scheduled_for=send_time,
            status="scheduled",
            rendered_message=message_text,
            template_id=template_id,
            provider=provider,
            idempotency_key=idempotency_key,
            assigned_staff_id=assigned_staff_id or user_id,
            created_by_user_id=user_id,
            payload={"reason": reason, "created_by_staff": True},
        )
        db.add(job)
        await db.flush()

        db.add(
            AutomationExecutionLog(
                job_id=job.id,
                rule_id=None,
                contact_id=contact.id,
                automation_type="staff_scheduled",
                action="scheduled",
                status_before=None,
                status_after="scheduled",
                details={"reason": reason, "scheduled_for": send_time.isoformat()},
            )
        )
        await db.commit()
        await db.refresh(job)
        return job

    @classmethod
    async def cancel_job(
        cls,
        db: AsyncSession,
        job_id: uuid.UUID,
        reason: str = "Cancelled by user",
        current_user: Optional[User] = None,
    ) -> AutomationScheduledJob:
        """Cancel a scheduled job."""
        job = await db.get(AutomationScheduledJob, job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found.")

        if job.status in ["sent", "delivered", "read", "cancelled"]:
            raise ValueError(f"Cannot cancel job in status '{job.status}'.")

        old_status = job.status
        job.status = "cancelled"
        job.suppression_reason = reason
        job.completed_at = datetime.now(timezone.utc)

        db.add(
            AutomationExecutionLog(
                job_id=job.id,
                rule_id=job.rule_id,
                contact_id=job.contact_id,
                automation_type=job.automation_type,
                action="cancelled",
                status_before=old_status,
                status_after="cancelled",
                details={"cancelled_by_user_id": str(current_user.id) if current_user else None, "reason": reason},
            )
        )
        await db.commit()
        await db.refresh(job)
        return job

    @classmethod
    async def retry_job(
        cls,
        db: AsyncSession,
        job_id: uuid.UUID,
        reset_attempts: bool = True,
        current_user: Optional[User] = None,
    ) -> AutomationScheduledJob:
        """Reset a failed or suppressed job back to scheduled state for execution."""
        job = await db.get(AutomationScheduledJob, job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found.")

        old_status = job.status
        job.status = "scheduled"
        job.suppression_reason = None
        job.suppression_details = None
        job.completed_at = None
        job.scheduled_for = datetime.now(timezone.utc)
        if reset_attempts:
            job.attempt_count = 0

        db.add(
            AutomationExecutionLog(
                job_id=job.id,
                rule_id=job.rule_id,
                contact_id=job.contact_id,
                automation_type=job.automation_type,
                action="retry_scheduled",
                status_before=old_status,
                status_after="scheduled",
                details={"retried_by_user_id": str(current_user.id) if current_user else None},
            )
        )
        await db.commit()
        await db.refresh(job)
        return job
