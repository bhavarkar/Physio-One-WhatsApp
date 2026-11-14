"""Clinical Availability Tool.

Single Organization Edition: Physio One Clinic.
Read-only tool querying AppointmentService to discover available consultation slots.
Strictly enforces Sunday restriction and operating hours (09:00 - 20:00 IST).
"""
from datetime import datetime, date
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.tools.base import BaseTool, ToolExecutionContext
from app.services.appointment_service import AppointmentService


class CheckAvailabilityTool(BaseTool):
    """Read-only tool checking appointment slots against clinic business rules."""

    name = "check_availability"
    description = (
        "Check available appointment consultation slots for a specific date at Physio One Clinic. "
        "The clinic operates Monday to Saturday from 09:00 AM to 08:00 PM IST. "
        "Physio One is strictly closed on Sundays."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "date": {
                "type": "string",
                "description": "Target date to check availability in YYYY-MM-DD format (e.g. '2026-11-16')",
            },
            "duration_minutes": {
                "type": "integer",
                "description": "Expected consultation duration in minutes (standard: 45)",
                "default": 45,
            },
            "practitioner_name": {
                "type": "string",
                "description": "Optional practitioner name (default: 'Dr. Physio One')",
                "default": "Dr. Physio One",
            },
        },
        "required": ["date"],
    }
    requires_permission = "appointments:read"
    is_mutation = False
    is_idempotent = True
    timeout_seconds = 10.0

    async def execute(
        self,
        arguments: Dict[str, Any],
        context: ToolExecutionContext,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """Query availability from the clinical appointment engine."""
        date_str = arguments.get("date")
        if not date_str:
            return {
                "success": False,
                "error": "Missing required 'date' parameter in YYYY-MM-DD format.",
            }

        try:
            target_date = datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
        except ValueError:
            return {
                "success": False,
                "error": f"Invalid date format '{date_str}'. Expected format is YYYY-MM-DD.",
            }

        duration = int(arguments.get("duration_minutes") or 45)
        practitioner = str(arguments.get("practitioner_name") or "Dr. Physio One")

        # Invoke core clinical appointment service
        avail = await AppointmentService.get_daily_availability(
            db=db,
            target_date=target_date,
            duration_minutes=duration,
            practitioner_name=practitioner,
        )

        available_slots = [
            {
                "start_time": s.start_time.isoformat() if hasattr(s.start_time, "isoformat") else str(s.start_time),
                "end_time": s.end_time.isoformat() if hasattr(s.end_time, "isoformat") else str(s.end_time),
            }
            for s in avail.slots
            if s.is_available
        ]

        return {
            "success": True,
            "date": avail.date,
            "is_open": avail.is_open,
            "message": avail.message or ("Clinic open for consultations" if avail.is_open else "Clinic closed"),
            "is_sunday": target_date.weekday() == 6,
            "total_slots_available": len(available_slots),
            "available_slots": available_slots[:15],  # Sample first 15 to stay within context budget
        }
