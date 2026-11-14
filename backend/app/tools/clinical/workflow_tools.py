"""Workflow State Machine Control Tools for AI Receptionist.

Single Organization Edition: Physio One Clinic.
Allows Deepti to safely initiate appointment workflows, select validated slots,
request explicit patient confirmation, and inspect current workflow status.
All mutations are mediated by AppointmentWorkflowService.
"""
from typing import Dict, Any, Optional
import uuid
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.tools.base import BaseTool, ToolExecutionContext
from app.services.workflow_service import AppointmentWorkflowService, WorkflowError
from app.models.whatsapp import Conversation
from app.schemas.workflow import WorkflowIntent


class StartAppointmentWorkflowTool(BaseTool):
    """Tool allowing AI agent to begin a controlled appointment workflow."""

    name = "start_appointment_workflow"
    description = (
        "Start a tracked appointment workflow for booking, rescheduling, or cancelling an appointment. "
        "Coordinates identity resolution and manages state transitions."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "intent": {
                "type": "string",
                "enum": [
                    "book_appointment",
                    "reschedule_appointment",
                    "cancel_appointment",
                    "check_availability",
                    "check_appointment_status",
                    "request_human_assistance",
                ],
                "description": "The classified appointment intent from the patient message",
            },
            "target_date": {
                "type": "string",
                "description": "Optional target date in YYYY-MM-DD format if provided by the patient",
            },
            "preferred_time": {
                "type": "string",
                "description": "Optional time preference mentioned by the patient (e.g. '5:00 PM' or 'morning')",
            },
            "service_type": {
                "type": "string",
                "description": "Optional clinic service type (e.g. 'Initial Physiotherapy Assessment')",
            },
            "appointment_id": {
                "type": "string",
                "description": "UUID of the existing appointment for reschedule or cancellation",
            },
        },
        "required": ["intent"],
    }
    requires_permission = "appointments:read"
    is_mutation = False
    is_idempotent = False
    timeout_seconds = 10.0

    async def execute(
        self,
        arguments: Dict[str, Any],
        context: ToolExecutionContext,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """Start workflow for conversation."""
        conv_id = context.conversation_id
        if not conv_id:
            return {"success": False, "error": "Missing conversation context."}

        stmt = select(Conversation).where(Conversation.id == conv_id)
        conv = (await db.execute(stmt)).scalar_one_or_none()
        if not conv:
            return {"success": False, "error": "Conversation record not found."}

        intent = arguments.get("intent")
        target_date = arguments.get("target_date")
        preferred_time = arguments.get("preferred_time")
        service_type = arguments.get("service_type")
        appt_id_str = arguments.get("appointment_id")
        appt_uuid = None
        if appt_id_str:
            try:
                appt_uuid = uuid.UUID(str(appt_id_str))
            except ValueError:
                pass

        try:
            workflow = await AppointmentWorkflowService.start_workflow(
                db=db,
                conversation_id=conv.id,
                contact_id=conv.contact_id,
                intent=intent,
                target_date=target_date,
                preferred_time=preferred_time,
                service_type=service_type,
                appointment_id=appt_uuid,
            )
            return {
                "success": True,
                "workflow_id": str(workflow.id),
                "intent": workflow.intent,
                "status": workflow.status,
                "message": f"Workflow started in state '{workflow.status}'.",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class SelectAppointmentSlotTool(BaseTool):
    """Tool allowing AI agent to choose a specific slot and prepare confirmation summary."""

    name = "select_appointment_slot"
    description = (
        "Select an available appointment time slot that the patient agreed to. "
        "Validates operating hours, Sunday restriction, and generates a confirmation summary for the patient."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "workflow_id": {
                "type": "string",
                "description": "Optional workflow UUID. If omitted, uses active workflow for the conversation.",
            },
            "slot_start": {
                "type": "string",
                "description": "Slot start time in ISO 8601 format (e.g. '2026-11-16T17:00:00+05:30')",
            },
            "slot_end": {
                "type": "string",
                "description": "Optional slot end time in ISO 8601 format",
            },
        },
        "required": ["slot_start"],
    }
    requires_permission = "appointments:read"
    is_mutation = False
    is_idempotent = False
    timeout_seconds = 10.0

    async def execute(
        self,
        arguments: Dict[str, Any],
        context: ToolExecutionContext,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """Assign slot to workflow and transition to awaiting confirmation."""
        conv_id = context.conversation_id
        wf_id_str = arguments.get("workflow_id")
        workflow = None

        if wf_id_str:
            try:
                wf_uuid = uuid.UUID(str(wf_id_str))
                workflow = await AppointmentWorkflowService.get_workflow_by_id(db, wf_uuid)
            except ValueError:
                return {"success": False, "error": f"Invalid workflow UUID: {wf_id_str}"}
        elif conv_id:
            workflow = await AppointmentWorkflowService.get_active_workflow(db, conv_id)

        if not workflow:
            return {"success": False, "error": "No active appointment workflow found."}

        slot_start_str = arguments.get("slot_start")
        try:
            slot_start = datetime.fromisoformat(slot_start_str.replace("Z", "+00:00"))
        except Exception:
            return {"success": False, "error": f"Invalid ISO datetime for slot_start: {slot_start_str}"}

        slot_end = None
        slot_end_str = arguments.get("slot_end")
        if slot_end_str:
            try:
                slot_end = datetime.fromisoformat(slot_end_str.replace("Z", "+00:00"))
            except Exception:
                pass

        try:
            updated_wf = await AppointmentWorkflowService.select_slot(
                db=db,
                workflow_id=workflow.id,
                slot_start=slot_start,
                slot_end=slot_end,
                actor_type="deepti_agent",
            )
            return {
                "success": True,
                "workflow_id": str(updated_wf.id),
                "status": updated_wf.status,
                "confirmation_token": updated_wf.confirmation_token,
                "proposed_changes": updated_wf.proposed_changes,
                "confirmation_prompt": (
                    f"Please confirm: {updated_wf.proposed_changes.get('formatted_display')} "
                    f"for {updated_wf.service_type} with {updated_wf.practitioner_name}. "
                    "Reply YES to confirm or NO to change."
                ),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class RequestAppointmentConfirmationTool(BaseTool):
    """Tool allowing AI agent to explicitly prompt patient for confirmation."""

    name = "request_appointment_confirmation"
    description = (
        "Retrieve the formatted confirmation summary and token that the patient must explicitly confirm. "
        "Ensures explicit patient confirmation is captured before any booking attempt."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "workflow_id": {
                "type": "string",
                "description": "Optional workflow UUID. If omitted, uses active workflow for the conversation.",
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
        """Fetch confirmation summary."""
        conv_id = context.conversation_id
        wf_id_str = arguments.get("workflow_id")
        workflow = None

        if wf_id_str:
            try:
                wf_uuid = uuid.UUID(str(wf_id_str))
                workflow = await AppointmentWorkflowService.get_workflow_by_id(db, wf_uuid)
            except ValueError:
                return {"success": False, "error": f"Invalid workflow UUID: {wf_id_str}"}
        elif conv_id:
            workflow = await AppointmentWorkflowService.get_active_workflow(db, conv_id)

        if not workflow:
            return {"success": False, "error": "No active appointment workflow found."}

        if not workflow.selected_slot_start:
            return {
                "success": False,
                "error": "No slot has been selected yet. Use select_appointment_slot first.",
            }

        return {
            "success": True,
            "workflow_id": str(workflow.id),
            "status": workflow.status,
            "confirmation_token": workflow.confirmation_token,
            "proposed_changes": workflow.proposed_changes,
            "message": (
                f"Proposed appointment on {workflow.proposed_changes.get('formatted_display')}. "
                "Ask the patient explicitly to reply YES to confirm."
            ),
        }


class GetAppointmentWorkflowStatusTool(BaseTool):
    """Tool inspecting current workflow state, slot selection, and confirmation status."""

    name = "get_appointment_workflow_status"
    description = (
        "Inspect the current status, selected slot, and confirmation state of an active appointment workflow."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "workflow_id": {
                "type": "string",
                "description": "Optional workflow UUID. If omitted, checks active workflow for conversation.",
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
        """Inspect workflow state."""
        conv_id = context.conversation_id
        wf_id_str = arguments.get("workflow_id")
        workflow = None

        if wf_id_str:
            try:
                wf_uuid = uuid.UUID(str(wf_id_str))
                workflow = await AppointmentWorkflowService.get_workflow_by_id(db, wf_uuid)
            except ValueError:
                return {"success": False, "error": f"Invalid workflow UUID: {wf_id_str}"}
        elif conv_id:
            workflow = await AppointmentWorkflowService.get_active_workflow(db, conv_id)

        if not workflow:
            return {
                "success": True,
                "has_active_workflow": False,
                "message": "No active appointment workflow for this conversation.",
            }

        return {
            "success": True,
            "has_active_workflow": True,
            "workflow_id": str(workflow.id),
            "intent": workflow.intent,
            "status": workflow.status,
            "workflow_version": workflow.workflow_version,
            "selected_slot": workflow.proposed_changes.get("formatted_display"),
            "confirmation_status": workflow.confirmation_status,
            "approval_status": workflow.approval_status,
        }
