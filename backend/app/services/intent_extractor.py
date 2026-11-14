"""Structured Intent Extraction and Normalization Engine for Appointments.

Single Organization Edition: Physio One Clinic.
Uses deterministic rule-based and NLP patterns operating strictly in Asia/Kolkata timezone.
Extracts structured booking, availability, rescheduling, and cancellation intents
without inventing missing details.
"""
import re
from datetime import datetime, date, timedelta, time
from typing import Optional, Dict, Any, Tuple
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.schemas.workflow import WorkflowIntent, ExtractedAppointmentIntent


def get_clinic_now() -> datetime:
    """Return current datetime in clinic timezone (Asia/Kolkata)."""
    try:
        tz = ZoneInfo(settings.CLINIC_TIMEZONE)
    except Exception:
        from datetime import timezone
        tz = timezone(timedelta(hours=5, minutes=30), name="Asia/Kolkata")
    return datetime.now(tz)


class AppointmentIntentExtractor:
    """Extracts appointment-related intents and entities from patient WhatsApp messages."""

    # Explicit confirmation regexes
    CONFIRM_PATTERNS = [
        r"^(yes|yep|yeah|yup|confirm|confirmed|proceed|book\s*it|sure|haan|ha|correct|ok|okay|perfect|done|please\s*confirm|go\s*ahead)[\s.!,]*$",
        r"\b(yes,\s*please|please\s*proceed|confirm\s*it|confirm\s*my\s*appointment|i\s*confirm)\b",
    ]

    REJECT_PATTERNS = [
        r"^(no|nope|cancel\s*that|don't\s*book|do\s*not\s*book|nahi|na|reject|discard|nevermind|never\s*mind)[\s.!,]*$",
        r"^(no[\s,]+(cancel\s*that|don't\s*book|stop|discard|do\s*not\s*book))[\s.!,]*$",
        r"\b(cancel\s*this\s*request|cancel\s*that|do\s*not\s*confirm|don't\s*confirm|no,\s*cancel)\b",
    ]

    HUMAN_PATTERNS = [
        r"\b(speak\s*to\s*(a\s*)?(human|person|agent|receptionist|staff|doctor))\b",
        r"\b(talk\s*to\s*(a\s*)?(human|person|agent|receptionist|staff|doctor))\b",
        r"\b(connect\s*(me\s*)?(to|with)\s*(a\s*)?(human|staff|receptionist|person))\b",
        r"\b(human\s*help|human\s*assistance|real\s*person)\b",
    ]

    STATUS_PATTERNS = [
        r"\b(do\s*i\s*have\s*(a\s*)?(booking|appointment))\b",
        r"\b(when\s*is\s*my\s*(next\s*)?(appointment|booking|visit|session))\b",
        r"\b(check\s*my\s*(appointment|booking|status))\b",
        r"\b(what\s*time\s*is\s*my\s*(appointment|booking))\b",
        r"\b(appointment\s*details|my\s*booking\s*details)\b",
    ]

    CANCEL_PATTERNS = [
        r"\b(cancel\s*(my\s*)?(appointment|booking|session|visit))\b",
        r"\b(cannot\s*make\s*it|can't\s*make\s*it|won't\s*be\s*able\s*to\s*come)\b",
        r"\b(please\s*cancel\s*(my\s*)?slot)\b",
    ]

    RESCHEDULE_PATTERNS = [
        r"\b(reschedule|postpone|prepune|prepone)\b",
        r"\b(move\s*(my\s*)?(appointment|booking)\s*to)\b",
        r"\b(change\s*(my\s*)?(appointment|booking)\s*(date|time|slot)?)\b",
        r"\b(shift\s*(my\s*)?(appointment|booking))\b",
    ]

    BOOK_PATTERNS = [
        r"\b(book|schedule|make|fix|take|need|want)\s*(an?\s*)?(new\s*)?(appointment|booking|consultation|session|slot)\b",
        r"\b(i\s*need\s*an\s*appointment)\b",
        r"\b(i\s*want\s*to\s*(see|consult|visit)\s*(the\s*)?(physio|doctor|practitioner))\b",
    ]

    AVAILABILITY_PATTERNS = [
        r"\b(can\s*i\s*come\s*(at|on|tomorrow|today))\b",
        r"\b(are\s*you\s*open\s*(at|on|tomorrow|today))\b",
        r"\b(is\s*(there\s*)?(any\s*)?slots?\s*available)\b",
        r"\b(what\s*(time|slots?)\s*(are\s*)?available)\b",
        r"\b(availability\s*for)\b",
    ]

    @classmethod
    def extract_intent(cls, message_text: str) -> ExtractedAppointmentIntent:
        """Parse message text into a validated structured appointment intent."""
        cleaned = (message_text or "").strip()
        lower = cleaned.lower()

        # Check explicit confirmation or rejection first
        for pat in cls.CONFIRM_PATTERNS:
            if re.search(pat, lower, re.IGNORECASE):
                return ExtractedAppointmentIntent(
                    intent=WorkflowIntent.BOOK_APPOINTMENT,
                    confidence=0.98,
                    is_explicit_confirmation=True,
                    raw_entities={"original_text": cleaned},
                )

        for pat in cls.REJECT_PATTERNS:
            if re.search(pat, lower, re.IGNORECASE):
                return ExtractedAppointmentIntent(
                    intent=WorkflowIntent.CANCEL_APPOINTMENT,
                    confidence=0.95,
                    is_explicit_confirmation=False,
                    raw_entities={"original_text": cleaned},
                )

        # 1. Human Assistance
        for pat in cls.HUMAN_PATTERNS:
            if re.search(pat, lower, re.IGNORECASE):
                return ExtractedAppointmentIntent(
                    intent=WorkflowIntent.REQUEST_HUMAN_ASSISTANCE,
                    confidence=0.99,
                    raw_entities={"matched_pattern": pat},
                )

        # 2. Appointment Status
        for pat in cls.STATUS_PATTERNS:
            if re.search(pat, lower, re.IGNORECASE):
                return ExtractedAppointmentIntent(
                    intent=WorkflowIntent.CHECK_APPOINTMENT_STATUS,
                    confidence=0.95,
                    raw_entities={"matched_pattern": pat},
                )

        # Extract dates and times
        target_date = cls._extract_date(lower)
        preferred_time = cls._extract_time(lower)

        # 3. Cancel Appointment
        for pat in cls.CANCEL_PATTERNS:
            if re.search(pat, lower, re.IGNORECASE):
                reason = cls._extract_reason(cleaned)
                return ExtractedAppointmentIntent(
                    intent=WorkflowIntent.CANCEL_APPOINTMENT,
                    confidence=0.95,
                    target_date=target_date,
                    cancellation_reason=reason,
                    raw_entities={"matched_pattern": pat},
                )

        # 4. Reschedule Appointment
        for pat in cls.RESCHEDULE_PATTERNS:
            if re.search(pat, lower, re.IGNORECASE):
                return ExtractedAppointmentIntent(
                    intent=WorkflowIntent.RESCHEDULE_APPOINTMENT,
                    confidence=0.95,
                    target_date=target_date,
                    preferred_time=preferred_time,
                    raw_entities={"matched_pattern": pat},
                )

        # 5. Availability Check
        for pat in cls.AVAILABILITY_PATTERNS:
            if re.search(pat, lower, re.IGNORECASE):
                return ExtractedAppointmentIntent(
                    intent=WorkflowIntent.CHECK_AVAILABILITY,
                    confidence=0.90,
                    target_date=target_date,
                    preferred_time=preferred_time,
                    raw_entities={"matched_pattern": pat},
                )

        # 6. Book Appointment
        for pat in cls.BOOK_PATTERNS:
            if re.search(pat, lower, re.IGNORECASE):
                service = cls._extract_service(lower)
                return ExtractedAppointmentIntent(
                    intent=WorkflowIntent.BOOK_APPOINTMENT,
                    confidence=0.92,
                    target_date=target_date,
                    preferred_time=preferred_time,
                    service_type=service,
                    raw_entities={"matched_pattern": pat},
                )

        # 7. Fallback: if user specified a date and time like "tomorrow at 5 pm"
        if target_date and preferred_time:
            return ExtractedAppointmentIntent(
                intent=WorkflowIntent.BOOK_APPOINTMENT,
                confidence=0.75,
                target_date=target_date,
                preferred_time=preferred_time,
                raw_entities={"inferred_from_datetime": True},
            )

        # Default fallback: check availability or general query
        return ExtractedAppointmentIntent(
            intent=WorkflowIntent.CHECK_AVAILABILITY,
            confidence=0.50,
            target_date=target_date,
            preferred_time=preferred_time,
            raw_entities={"fallback": True},
        )

    @classmethod
    def _extract_date(cls, text: str) -> Optional[str]:
        """Extract explicit or relative date in YYYY-MM-DD in Asia/Kolkata."""
        now_clinic = get_clinic_now()
        today = now_clinic.date()

        if re.search(r"\b(today)\b", text):
            return today.isoformat()
        if re.search(r"\b(tomorrow)\b", text):
            return (today + timedelta(days=1)).isoformat()
        if re.search(r"\b(day\s*after\s*tomorrow)\b", text):
            return (today + timedelta(days=2)).isoformat()

        # Day of week (e.g., "on monday", "this friday", "next monday")
        weekdays = {
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6,
        }
        for name, wd in weekdays.items():
            if re.search(rf"\b(this\s+|next\s+|on\s+)?{name}\b", text):
                current_wd = today.weekday()
                days_ahead = (wd - current_wd) % 7
                if days_ahead == 0:
                    days_ahead = 7  # If today is Monday and user asks "on Monday", assume next Monday
                target = today + timedelta(days=days_ahead)
                return target.isoformat()

        # Specific ISO or format matches: YYYY-MM-DD
        iso_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
        if iso_match:
            try:
                d = datetime.strptime(iso_match.group(1), "%Y-%m-%d").date()
                return d.isoformat()
            except ValueError:
                pass

        # DD/MM/YYYY or DD-MM-YYYY
        dmy_match = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", text)
        if dmy_match:
            try:
                day_num = int(dmy_match.group(1))
                month_num = int(dmy_match.group(2))
                year_num = int(dmy_match.group(3))
                d = date(year_num, month_num, day_num)
                return d.isoformat()
            except ValueError:
                pass

        return None

    @classmethod
    def _extract_time(cls, text: str) -> Optional[str]:
        """Extract preferred time string (e.g. '5:00 PM', '10:00 AM')."""
        # Match "5 pm", "5:30 pm", "10 am", "17:00"
        m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", text)
        if m:
            hour = int(m.group(1))
            minute = int(m.group(2) or 0)
            meridiem = m.group(3).upper()
            return f"{hour}:{minute:02d} {meridiem}"

        m_24 = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", text)
        if m_24:
            hour = int(m_24.group(1))
            minute = int(m_24.group(2))
            meridiem = "AM" if hour < 12 else "PM"
            display_hour = hour % 12
            if display_hour == 0:
                display_hour = 12
            return f"{display_hour}:{minute:02d} {meridiem}"

        if re.search(r"\b(morning)\b", text):
            return "morning"
        if re.search(r"\b(afternoon)\b", text):
            return "afternoon"
        if re.search(r"\b(evening)\b", text):
            return "evening"

        return None

    @classmethod
    def _extract_service(cls, text: str) -> str:
        """Extract requested service type if mentioned."""
        if re.search(r"\b(assessment|consultation|initial\s*visit)\b", text):
            return "Initial Physiotherapy Assessment"
        if re.search(r"\b(follow\s*up|followup|subsequent)\b", text):
            return "Follow-up Physiotherapy Session"
        if re.search(r"\b(back\s*pain|spine|lumbar)\b", text):
            return "Spine & Back Pain Therapy"
        if re.search(r"\b(sports|injury|rehab)\b", text):
            return "Sports Injury Rehabilitation"
        return "Initial Physiotherapy Assessment"

    @classmethod
    def _extract_reason(cls, text: str) -> Optional[str]:
        """Extract reason for cancellation or rescheduling if present."""
        m = re.search(r"\b(?:because|due\s*to|reason\s*is|since)\s+([^.!?]+)", text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        return None
