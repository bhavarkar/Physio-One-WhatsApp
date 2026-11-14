"""Patient Lookup Tool.

Single Organization Edition: Physio One Clinic.
Read-only tool allowing AI agent to verify patient record and recent appointment status.
Masks PHI (phone and contact details) before returning to agent context.
"""
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.tools.base import BaseTool, ToolExecutionContext
from app.models.patient import Patient


class FindPatientTool(BaseTool):
    """Read-only tool searching patient registry with privacy masking."""

    name = "find_patient"
    description = (
        "Look up an existing clinic patient record by contact phone number or name. "
        "Returns basic status and privacy-masked profile."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "phone": {
                "type": "string",
                "description": "Patient phone number with country code (e.g. '+919876543210' or '9876543210')",
            },
            "name": {
                "type": "string",
                "description": "Full or partial name of the patient",
            },
        },
    }
    requires_permission = "contacts:read"
    is_mutation = False
    is_idempotent = True
    timeout_seconds = 10.0

    async def execute(
        self,
        arguments: Dict[str, Any],
        context: ToolExecutionContext,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """Search patient master records."""
        phone = arguments.get("phone")
        name = arguments.get("name")

        if not phone and not name:
            return {
                "success": False,
                "error": "Provide at least 'phone' or 'name' to search for patient records.",
            }

        conditions = []
        if phone:
            clean_phone = phone.strip().replace(" ", "").replace("-", "")
            conditions.append(Patient.phone_number.like(f"%{clean_phone[-10:]}%"))
        if name:
            conditions.append(Patient.full_name.ilike(f"%{name.strip()}%"))

        stmt = select(Patient).where(or_(*conditions)).limit(3)
        patients = (await db.execute(stmt)).scalars().all()

        if not patients:
            return {
                "success": True,
                "found": False,
                "message": "No matching patient records found.",
            }

        results = []
        for p in patients:
            # Mask phone number for PHI protection: +91 98*** **210
            raw_phone = p.phone_number or ""
            masked_phone = raw_phone
            if len(raw_phone) >= 10:
                masked_phone = f"{raw_phone[:3]}***{raw_phone[-4:]}"

            raw_email = p.email or ""
            masked_email = raw_email
            if raw_email and "@" in raw_email:
                parts = raw_email.split("@", 1)
                user_part = parts[0]
                if len(user_part) > 2:
                    masked_email = f"{user_part[0]}***{user_part[-1]}@{parts[1]}"
                else:
                    masked_email = f"***@{parts[1]}"

            results.append({
                "patient_id": str(p.id),
                "full_name": p.full_name,
                "masked_phone": masked_phone,
                "gender": p.gender,
                "masked_email": masked_email,
            })

        return {
            "success": True,
            "found": True,
            "count": len(results),
            "patients": results,
        }
