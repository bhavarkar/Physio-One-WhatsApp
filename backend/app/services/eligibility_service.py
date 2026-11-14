"""Eligibility and Suppression Engine for Scheduled Automations.

Single Organization Edition: Physio One Clinic.
Rigorously evaluates the 12 pre-flight safety gates before any automated message can be dispatched.
Produces structured suppression reasons and audit logs.
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.models.followup import (
    AutomationRule,
    AutomationScheduledJob,
    AutomationSettings,
    AutomationSuppressionLog,
    AutomationContactCooldown,
    AutomationMessageTemplate,
)
from app.models.whatsapp import Conversation, WhatsAppContact, WhatsAppMessage, WhatsAppAccount
from app.models.patient import Patient, PatientConsent, Appointment
from app.services.business_hours_service import (
    is_in_business_hours,
    is_in_quiet_hours,
    calculate_next_eligible_send_time,
)
from app.services.template_service import TemplateService

logger = logging.getLogger("physio_one.automation.eligibility")


@dataclass
class EligibilityResult:
    eligible: bool
    suppression_reason: Optional[str] = None
    details: Dict[str, Any] = None
    should_reschedule: bool = False
    next_eligible_time: Optional[datetime] = None


class EligibilityService:
    """Evaluates multi-layer safety invariants for automated outbound dispatches."""

    @classmethod
    async def evaluate_job_eligibility(
        cls,
        db: AsyncSession,
        job: AutomationScheduledJob,
        settings: AutomationSettings,
        rule: Optional[AutomationRule] = None,
        now: Optional[datetime] = None,
    ) -> EligibilityResult:
        """Evaluate all 12 pre-flight safety invariants for a scheduled job."""
        cur_now = now or datetime.now(timezone.utc)
        rule_obj = rule or job.rule

        # 1. Global Kill Switch Gate
        if not settings.outbound_enabled:
            return EligibilityResult(
                eligible=False,
                suppression_reason="kill_switch_disabled",
                details={"message": "Global automation kill switch (AUTOMATION_OUTBOUND_ENABLED) is disabled."},
            )

        if settings.emergency_stop:
            return EligibilityResult(
                eligible=False,
                suppression_reason="emergency_stop_active",
                details={"message": "Global emergency stop is active."},
            )

        # 2. Rule Enabled Gate (if linked to a rule)
        if rule_obj and not rule_obj.is_enabled:
            return EligibilityResult(
                eligible=False,
                suppression_reason="rule_disabled",
                details={"rule_id": str(rule_obj.id), "rule_name": rule_obj.name},
            )

        # 3. Recipient Existence Gate
        contact = job.contact or await db.get(WhatsAppContact, job.contact_id)
        if not contact:
            return EligibilityResult(
                eligible=False,
                suppression_reason="contact_not_found",
                details={"contact_id": str(job.contact_id)},
            )

        # 4. Consent & Opt-Out Gate
        if contact.opted_out_all:
            return EligibilityResult(
                eligible=False,
                suppression_reason="patient_opted_out_all",
                details={"contact_id": str(contact.id), "reason": "Contact opted out of all automated communications."},
            )

        # If marketing category
        if job.template and job.template.category == "MARKETING":
            if contact.opted_out_marketing:
                return EligibilityResult(
                    eligible=False,
                    suppression_reason="patient_opted_out_marketing",
                    details={"contact_id": str(contact.id)},
                )

        # Patient clinical consent check (if patient linked)
        if job.patient_id:
            consent_stmt = select(PatientConsent).where(
                PatientConsent.patient_id == job.patient_id,
                PatientConsent.consent_type == "whatsapp_communication",
                PatientConsent.is_granted.is_(False),
            )
            revoked_consent = (await db.execute(consent_stmt)).scalars().first()
            if revoked_consent:
                return EligibilityResult(
                    eligible=False,
                    suppression_reason="patient_consent_revoked",
                    details={"patient_id": str(job.patient_id), "consent_type": "whatsapp_communication"},
                )

        # 5. Human Takeover Gate
        conversation: Optional[Conversation] = None
        if job.conversation_id:
            conversation = job.conversation or await db.get(Conversation, job.conversation_id)
        elif contact:
            # Look up most recent open conversation
            conv_stmt = select(Conversation).where(
                Conversation.contact_id == contact.id,
                Conversation.status != "closed",
            ).order_by(Conversation.created_at.desc())
            conversation = (await db.execute(conv_stmt)).scalars().first()

        if conversation:
            if conversation.is_human_takeover:
                return EligibilityResult(
                    eligible=False,
                    suppression_reason="human_takeover_active",
                    details={"conversation_id": str(conversation.id), "takeover_by": str(conversation.takeover_by_user_id)},
                )
            if conversation.ai_paused:
                return EligibilityResult(
                    eligible=False,
                    suppression_reason="ai_paused",
                    details={"conversation_id": str(conversation.id)},
                )

        # 6. Authoritative Appointment Status Gate
        if job.appointment_id:
            appointment = job.appointment or await db.get(Appointment, job.appointment_id)
            if not appointment:
                return EligibilityResult(
                    eligible=False,
                    suppression_reason="appointment_not_found",
                    details={"appointment_id": str(job.appointment_id)},
                )

            # Reminder rules: appointment must be confirmed
            if job.automation_type == "appointment_reminder":
                if appointment.status != "confirmed":
                    return EligibilityResult(
                        eligible=False,
                        suppression_reason="appointment_not_confirmed",
                        details={"appointment_id": str(appointment.id), "current_status": appointment.status},
                    )
                # Also verify appointment is not in the past
                appt_start = appointment.start_time if appointment.start_time.tzinfo else appointment.start_time.replace(tzinfo=timezone.utc)
                if appt_start < cur_now:
                    return EligibilityResult(
                        eligible=False,
                        suppression_reason="appointment_already_passed",
                        details={"appointment_id": str(appointment.id), "start_time": appt_start.isoformat()},
                    )

            # Post-appointment follow-up rules: appointment must be completed
            elif job.automation_type == "appointment_followup":
                if appointment.status != "completed":
                    return EligibilityResult(
                        eligible=False,
                        suppression_reason="appointment_not_completed",
                        details={"appointment_id": str(appointment.id), "current_status": appointment.status},
                    )

            # No-show rules: appointment must be marked no_show
            elif job.automation_type == "noshow_followup":
                if appointment.status != "no_show":
                    return EligibilityResult(
                        eligible=False,
                        suppression_reason="appointment_not_noshow",
                        details={"appointment_id": str(appointment.id), "current_status": appointment.status},
                    )

        # 7. Patient Inbound Reply Gate (for inactivity follow-ups)
        if job.automation_type == "inactivity_followup" and conversation:
            inactivity_base = job.payload.get("inactivity_since")
            if inactivity_base:
                inactivity_dt = datetime.fromisoformat(inactivity_base) if isinstance(inactivity_base, str) else inactivity_base
                inactivity_utc = inactivity_dt if inactivity_dt.tzinfo else inactivity_dt.replace(tzinfo=timezone.utc)
                
                # Check for inbound messages after this point
                reply_stmt = select(func.count(WhatsAppMessage.id)).where(
                    WhatsAppMessage.conversation_id == conversation.id,
                    WhatsAppMessage.direction == "inbound",
                    WhatsAppMessage.created_at > inactivity_utc,
                )
                replies_count = (await db.scalar(reply_stmt)) or 0
                if replies_count > 0:
                    return EligibilityResult(
                        eligible=False,
                        suppression_reason="patient_replied",
                        details={"conversation_id": str(conversation.id), "replies_count": replies_count},
                    )

        # 8. Existing Booking Gate (for inactivity follow-ups intended to encourage booking)
        if job.automation_type == "inactivity_followup":
            # Check if patient already has an active upcoming confirmed booking
            upcoming_appt_stmt = select(Appointment).join(Patient).where(
                Patient.contact_id == contact.id,
                Appointment.status == "confirmed",
                Appointment.start_time > cur_now,
            )
            has_booking = (await db.execute(upcoming_appt_stmt)).scalars().first()
            if has_booking:
                return EligibilityResult(
                    eligible=False,
                    suppression_reason="appointment_already_booked",
                    details={"contact_id": str(contact.id), "appointment_id": str(has_booking.id)},
                )

        # 9. Cooldown Gate
        cooldown_stmt = select(AutomationContactCooldown).where(
            AutomationContactCooldown.contact_id == contact.id,
            AutomationContactCooldown.automation_type == job.automation_type,
            AutomationContactCooldown.expires_at > cur_now,
        )
        active_cooldown = (await db.execute(cooldown_stmt)).scalars().first()
        if active_cooldown:
            return EligibilityResult(
                eligible=False,
                suppression_reason="cooldown_active",
                details={
                    "contact_id": str(contact.id),
                    "automation_type": job.automation_type,
                    "expires_at": active_cooldown.expires_at.isoformat(),
                },
            )

        # 10. Business Hours & Quiet Hours Gate
        tz_name = (rule_obj.timezone if rule_obj else None) or settings.default_timezone
        start_h = (rule_obj.start_hour if rule_obj else None) or settings.business_hours_start
        end_h = (rule_obj.end_hour if rule_obj else None) or settings.business_hours_end
        permitted_d = (rule_obj.permitted_days if rule_obj else None) or [1, 2, 3, 4, 5, 6]
        q_start = settings.quiet_hours_start
        q_end = settings.quiet_hours_end

        in_quiet = is_in_quiet_hours(cur_now, q_start, q_end, tz_name)
        in_biz = is_in_business_hours(cur_now, start_h, end_h, permitted_d, tz_name)

        if in_quiet or not in_biz:
            next_send = calculate_next_eligible_send_time(
                cur_now, start_h, end_h, q_start, q_end, permitted_d, tz_name
            )
            return EligibilityResult(
                eligible=False,
                suppression_reason="outside_business_hours",
                details={
                    "in_quiet_hours": in_quiet,
                    "in_business_hours": in_biz,
                    "next_eligible_send_time": next_send.isoformat(),
                },
                should_reschedule=True,
                next_eligible_time=next_send,
            )

        # 11. WhatsApp 24-Hour Service Window Gate
        last_inbound_stmt = select(func.max(WhatsAppMessage.created_at)).where(
            WhatsAppMessage.contact_id == contact.id,
            WhatsAppMessage.direction == "inbound",
        )
        last_inbound_at = await db.scalar(last_inbound_stmt)
        if not last_inbound_at and contact.last_active_at:
            last_inbound_at = contact.last_active_at
        service_window_open = TemplateService.is_service_window_open(last_inbound_at, cur_now)

        template = job.template
        if not template and job.template_id:
            template = await db.get(AutomationMessageTemplate, job.template_id)

        if not service_window_open:
            # Window expired: approved template is mandatory
            if not template:
                return EligibilityResult(
                    eligible=False,
                    suppression_reason="service_window_expired_template_required",
                    details={
                        "message": "24-hour customer service window is closed; free-form message prohibited without an approved template.",
                        "last_inbound_at": last_inbound_at.isoformat() if last_inbound_at else None,
                    },
                )
            if template.approval_status != "APPROVED":
                return EligibilityResult(
                    eligible=False,
                    suppression_reason="unapproved_template",
                    details={"template_id": str(template.id), "status": template.approval_status},
                )
        else:
            # Window open: template if present must still be valid
            if template and template.approval_status != "APPROVED":
                return EligibilityResult(
                    eligible=False,
                    suppression_reason="unapproved_template",
                    details={"template_id": str(template.id), "status": template.approval_status},
                )

        # 12. Provider Active Connection Gate (skipped for synthetic test_mode)
        if job.payload.get("test_mode") is not True:
            provider_name = job.provider if job.provider != "any" else "meta"
            account_stmt = select(WhatsAppAccount).where(
                WhatsAppAccount.provider == provider_name,
                WhatsAppAccount.is_active.is_(True),
            )
            account = (await db.execute(account_stmt)).scalars().first()
            if not account:
                # Try fallback to other active provider
                any_acc_stmt = select(WhatsAppAccount).where(WhatsAppAccount.is_active.is_(True))
                account = (await db.execute(any_acc_stmt)).scalars().first()
                if not account:
                    return EligibilityResult(
                        eligible=False,
                        suppression_reason="no_active_whatsapp_provider",
                        details={"requested_provider": job.provider},
                    )

        # All 12 gates satisfied
        return EligibilityResult(eligible=True)

    @classmethod
    async def record_suppression(
        cls,
        db: AsyncSession,
        job: AutomationScheduledJob,
        reason: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> AutomationSuppressionLog:
        """Create an immutable suppression log record and update job status."""
        log = AutomationSuppressionLog(
            job_id=job.id,
            rule_id=job.rule_id,
            contact_id=job.contact_id,
            reason=reason,
            details=details or {},
        )
        db.add(log)
        job.status = "suppressed"
        job.suppression_reason = reason
        job.suppression_details = details or {}
        job.completed_at = datetime.now(timezone.utc)
        await db.flush()
        logger.info(
            "Automation job %s suppressed for contact %s. Reason: %s",
            job.id,
            job.contact_id,
            reason,
        )
        return log
