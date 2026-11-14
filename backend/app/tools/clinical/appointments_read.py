"""Read-Only Clinical Appointment Lookup Tools for AI Receptionist.

Single Organization Edition: Physio One Clinic.
Allows Deepti to retrieve existing and upcoming appointments for the authenticated patient.
Strictly isolates patient data so patients can never see another person's appointments.
"""
from typing import Dict, Any, Optional
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from app.tools.base import BaseTool, ToolExecutionContext
from app.models.patient import Patient, Appointment
from app.models.whatsapp import Conversation, WhatsAppContact
from app.services.appointment_service import normalize_to_clinic_tz, ensure_utc_aware


class GetPatientAppointmentsTool(BaseTool):
    """Read-only tool querying upcoming or recent appointments for the current conversation's patient."""

    name = "get_patient_appointments"
    description = (
        "Retrieve current, upcoming, or past appointments for the verified patient in this conversation. "
        "Strictly prevents cross-patient data access by resolving the patient from conversation context."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "status_filter": {
                "type": "string",
                "description": "Optional filter: 'active' (default: confirmed/scheduled), 'all', or 'cancelled'",
                "default": "active",
            },
        },
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
        """Fetch appointments linked to verified contact/patient in context."""
        conv_id = context.conversation_id
        if not conv_id:
            return {
                "success": False,
                "error": "No active conversation context provided. Cannot verify patient identity.",
            }

        # Resolve contact and patient from conversation
        stmt = (
            select(Conversation)
            .options(
                selectinload(Conversation.contact).selectinload(WhatsAppContact.patient)
            )
            .where(Conversation.id == conv_id)
        )
        conv = (await db.execute(stmt)).scalar_one_or_none()
        if not conv or not conv.contact:
            return {"success": False, "error": "Conversation or contact record not found."}

        contact = conv.contact
        patient = contact.patient
        if not patient:
            # Fallback lookup by phone number
            p_stmt = select(Patient).where(Patient.phone_number == contact.phone_number)
            patient = (await db.execute(p_stmt)).scalars().first()

        if not patient:
            return {
                "success": True,
                "has_patient_record": False,
                "appointments": [],
                "message": "No registered patient record found for this phone number.",
            }

        status_filter = arguments.get("status_filter", "active")
        query = select(Appointment).where(Appointment.patient_id == patient.id)
        if status_filter == "active":
            query = query.where(Appointment.status.not_in(["cancelled", "no_show"]))
        elif status_filter == "cancelled":
            query = query.where(Appointment.status == "cancelled")

        query = query.order_by(Appointment.start_time.asc())
        appts = (await db.execute(query)).scalars().all()

        formatted = []
        for a in appts:
            s_utc = ensure_utc_aware(a.start_time)
            e_utc = ensure_utc_aware(a.end_time)
            s_local = normalize_to_clinic_tz(s_utc)
            e_local = normalize_to_clinic_tz(e_utc)

            formatted.append({
                "appointment_id": str(a.id),
                "practitioner_name": a.practitioner_name,
                "service_type": a.service_type,
                "date": s_local.strftime("%Y-%m-%d"),
                "start_time_local": s_local.strftime("%I:%M %p"),
                "end_time_local": e_local.strftime("%I:%M %p"),
                "status": a.status,
                "duration_minutes": a.duration_minutes,
            })

        return {
            "success": True,
            "patient_name": patient.full_name,
            "total_count": len(formatted),
            "appointments": formatted,
        }


class GetAppointmentDetailsTool(BaseTool):
    """Read-only tool querying details of a specific appointment with ownership verification."""

    name = "get_appointment_details"
    description = (
        "Get detailed information about a specific appointment by ID. "
        "Strictly verifies that the appointment belongs to the verified patient in the current conversation."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "appointment_id": {
                "type": "string",
                "description": "UUID of the appointment to inspect",
            },
        },
        "required": ["appointment_id"],
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
        """Fetch appointment details after verifying caller patient ownership."""
        appt_id_str = arguments.get("appointment_id")
        if not appt_id_str:
            return {"success": False, "error": "Missing required appointment_id parameter."}

        try:
            appt_uuid = uuid.UUID(str(appt_id_str))
        except ValueError:
            return {"success": False, "error": f"Invalid appointment UUID: {appt_id_str}"}

        conv_id = context.conversation_id
        if not conv_id:
            return {"success": False, "error": "No active conversation context provided."}

        # Resolve verified patient
        stmt = (
            select(Conversation)
            .options(
                selectinload(Conversation.contact).selectinload(WhatsAppContact.patient)
            )
            .where(Conversation.id == conv_id)
        )
        conv = (await db.execute(stmt)).scalar_one_or_none()
        if not conv or not conv.contact:
            return {"success": False, "error": "Conversation or contact record not found."}

        patient = conv.contact.patient
        if not patient:
            p_stmt = select(Patient).where(Patient.phone_number == conv.contact.phone_number)
            patient = (await db.execute(p_stmt)).scalars().first()

        if not patient:
            return {"success": False, "error": "No verified patient record found."}

        appt_stmt = (
            select(Appointment)
            .options(selectinload(Appointment.patient))
            .where(Appointment.id == appt_uuid)
        )
        appt = (await db.execute(appt_stmt)).scalar_one_or_none()
        if not appt:
            return {"success": False, "error": "Appointment not found."}

        # Strict cross-patient boundary protection
        if appt.patient_id != patient.id:
            return {
                "success": False,
                "error": "Access denied. You do not have permission to view this appointment record.",
            }

        s_utc = ensure_utc_aware(appt.start_time)
        e_utc = ensure_utc_aware(appt.end_time)
        s_local = normalize_to_clinic_tz(s_utc)
        e_local = normalize_to_clinic_tz(e_utc)

        return {
            "success": True,
            "appointment": {
                "appointment_id": str(appt.id),
                "patient_name": patient.full_name,
                "practitioner_name": appt.practitioner_name,
                "service_type": appt.service_type,
                "date": s_local.strftime("%Y-%m-%d"),
                "start_time_local": s_local.strftime("%I:%M %p"),
                "end_time_local": e_local.strftime("%I:%M %p"),
                "status": appt.status,
                "notes": appt.notes,
                "cancellation_reason": appt.cancellation_reason,
            },
        }
