"""WhatsApp Message Template Engine & 24-Hour Service Window Compliance.

Single Organization Edition: Physio One Clinic.
Handles variable interpolation, missing variable validation, template approval checks,
and WhatsApp 24-hour customer service window enforcement.
"""
import re
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("physio_one.automation.templates")

VARIABLE_PATTERN = re.compile(r"\{\{([a-zA-Z0-9_]+)\}\}")


class TemplateError(Exception):
    """Base class for template processing errors."""
    pass


class MissingTemplateVariableError(TemplateError):
    def __init__(self, missing_variables: List[str], template_name: Optional[str] = None):
        self.missing_variables = missing_variables
        self.template_name = template_name
        super().__init__(
            f"Missing required template variables: {', '.join(missing_variables)}"
            + (f" in template '{template_name}'" if template_name else "")
        )


class UnapprovedTemplateError(TemplateError):
    def __init__(self, template_name: str, status: str):
        self.template_name = template_name
        self.status = status
        super().__init__(f"Template '{template_name}' cannot be used because its status is '{status}'. Must be 'APPROVED'.")


class ServiceWindowComplianceError(TemplateError):
    def __init__(self, reason: str = "WhatsApp 24-hour customer service window is closed; an approved template is required."):
        super().__init__(reason)


class TemplateService:
    """Manages template variable extraction, rendering, and WhatsApp compliance."""

    @staticmethod
    def extract_variables(body: str) -> List[str]:
        """Extract all {{variable_name}} tokens from template text."""
        return sorted(list(set(VARIABLE_PATTERN.findall(body))))

    @staticmethod
    def render(body: str, variables: Dict[str, Any], template_name: Optional[str] = None) -> str:
        """Safely substitute variables in body.
        
        Raises MissingTemplateVariableError if any variable in body is missing or None.
        """
        required_vars = TemplateService.extract_variables(body)
        missing: List[str] = []

        for var in required_vars:
            if var not in variables or variables[var] is None:
                missing.append(var)

        if missing:
            raise MissingTemplateVariableError(missing, template_name)

        def _repl(match):
            key = match.group(1)
            val = variables.get(key, "")
            return str(val)

        return VARIABLE_PATTERN.sub(_repl, body)

    @staticmethod
    def validate_template_approval(template_status: str, template_name: str) -> None:
        """Ensure template has an APPROVED status."""
        if (template_status or "").upper() != "APPROVED":
            raise UnapprovedTemplateError(template_name, template_status)

    @staticmethod
    def is_service_window_open(last_inbound_at: Optional[datetime], now: Optional[datetime] = None) -> bool:
        """Check if contact's 24-hour customer care window is open."""
        if not last_inbound_at:
            return False
        cur_now = now or datetime.now(timezone.utc)
        inbound_utc = last_inbound_at if last_inbound_at.tzinfo else last_inbound_at.replace(tzinfo=timezone.utc)
        return cur_now <= (inbound_utc + timedelta(hours=24))

    @staticmethod
    def build_appointment_context(
        patient_name: str,
        start_time_local: datetime,
        practitioner_name: str = "Dr. Physio One",
        service_type: str = "Physiotherapy Consultation",
        clinic_name: str = "Physio One Clinic",
        custom_notes: Optional[str] = None,
    ) -> Dict[str, str]:
        """Format standard clinical appointment variables for templates."""
        date_str = start_time_local.strftime("%A, %d %B %Y")
        time_str = start_time_local.strftime("%I:%M %p")
        return {
            "patient_name": patient_name,
            "appointment_date": date_str,
            "appointment_time": time_str,
            "practitioner_name": practitioner_name,
            "service_type": service_type,
            "clinic_name": clinic_name,
            "notes": custom_notes or "",
        }
