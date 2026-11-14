"""Controlled Appointment Mutating Tools for AI Receptionist.

Single Organization Edition: Physio One Clinic.
Implements create_appointment, reschedule_appointment, and cancel_appointment.
CRITICAL CONSTRAINT: All mutating tools are strictly gated by the backend workflow
state machine, patient confirmation tokens, and clinic automation policy (Mode A Read Only by default).
The LLM cannot directly create, reschedule, or cancel appointments.
"""
from typing import Dict, Any, Optional
import uuid
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.tools.base import BaseTool, ToolExecutionContext
from app.services.workflow_service import (
    AppointmentWorkflowService,
    WorkflowError,
    WorkflowPolicyViolationError,
    WorkflowStateError,
    ConfirmationRequiredError,
    ApprovalRequiredError,
)
from app.schemas.workflow import WorkflowState, AutomationPolicyMode


class CreateAppointmentTool(BaseTool):
    """Mutating tool creating a confirmed appointment only when authorized by workflow state machine."""

    name = "create_appointment"
    description = (
        "Commit a new clinic appointment booking into the authoritative appointment database. "
        "STRICTLY REQUIRES an active workflow in 'ready_to_commit' state with verified patient confirmation "
        "and staff approval where required by policy. Cannot be called directly without workflow approval."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "workflow_id": {
                "type": "string",
                "description": "UUID of the approved and confirmed appointment workflow",
            },
            "confirmation_token": {
                "type": "string",
                "description": "Patient confirmation token generated during slot selection",
            },
            "idempotency_key": {
                "type": "string",
                "description": "Optional idempotency key to prevent duplicate booking commits",
            },
        },
        "required": ["workflow_id", "confirmation_token"],
    }
    requires_permission = "appointments:create"
    is_mutation = True
    is_idempotent = True
    timeout_seconds = 15.0

    async def execute(
        self,
        arguments: Dict[str, Any],
        context: ToolExecutionContext,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """Commit new appointment booking through state machine."""
        wf_id_str = arguments.get("workflow_id")
        conf_token = arguments.get("confirmation_token")
        idempotency_key = arguments.get("idempotency_key")

        if not wf_id_str or not conf_token:
            return {
                "success": False,
                "error": "Both 'workflow_id' and 'confirmation_token' are required to commit a booking.",
            }

        try:
            wf_uuid = uuid.UUID(str(wf_id_str))
        except ValueError:
            return {"success": False, "error": f"Invalid workflow UUID: {wf_id_str}"}

        workflow = await AppointmentWorkflowService.get_workflow_by_id(db, wf_uuid)
        if not workflow:
            return {"success": False, "error": "Workflow not found."}

        # 1. Verify token
        if workflow.confirmation_token != conf_token.strip().upper():
            return {
                "success": False,
                "error": "Invalid or mismatched confirmation token. Mutation rejected.",
            }

        # 2. Check policy mode
        settings_obj = await AppointmentWorkflowService.get_or_create_settings(db)
        if settings_obj.policy_mode == AutomationPolicyMode.MODE_A_READ_ONLY.value:
            return {
                "success": False,
                "error": (
                    "Direct appointment mutation is disabled in Mode A (Read Only). "
                    "The booking proposal has been recorded and requires manual staff approval in the clinic dashboard."
                ),
                "policy_mode": settings_obj.policy_mode,
            }

        if settings_obj.policy_mode == AutomationPolicyMode.MODE_B_STAFF_APPROVAL.value:
            if workflow.approval_status != "approved":
                return {
                    "success": False,
                    "error": (
                        "Staff approval is required by clinic policy before this appointment can be committed. "
                        f"Current approval status: '{workflow.approval_status}'."
                    ),
                    "approval_status": workflow.approval_status,
                }

        # 3. Verify workflow state is ready_to_commit
        if workflow.status != WorkflowState.READY_TO_COMMIT.value:
            return {
                "success": False,
                "error": (
                    f"Workflow is in '{workflow.status}' state, not 'ready_to_commit'. "
                    "Cannot commit appointment directly."
                ),
            }

        # 4. Execute commit
        try:
            result = await AppointmentWorkflowService.commit_workflow(
                db=db,
                workflow_id=workflow.id,
                actor_type="deepti_agent",
                idempotency_key=idempotency_key,
            )
            return {
                "success": True,
                "message": "Appointment successfully booked and committed.",
                "details": result.get("result"),
            }
        except Exception as e:
            return {"success": False, "error": f"Commit failed: {str(e)}"}


class RescheduleAppointmentTool(BaseTool):
    """Mutating tool rescheduling an appointment only when authorized by workflow state machine."""

    name = "reschedule_appointment"
    description = (
        "Reschedule an existing active appointment to a new date and time. "
        "STRICTLY REQUIRES workflow state verification, patient ownership verification, and patient confirmation. "
        "Blocked in Mode A (Read Only)."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "workflow_id": {
                "type": "string",
                "description": "UUID of the approved rescheduling workflow",
            },
            "appointment_id": {
                "type": "string",
                "description": "UUID of the existing appointment to reschedule",
            },
            "new_start_time": {
                "type": "string",
                "description": "Target new start time in ISO 8601 format",
            },
            "confirmation_token": {
                "type": "string",
                "description": "Patient confirmation token",
            },
            "idempotency_key": {
                "type": "string",
                "description": "Optional idempotency key",
            },
        },
        "required": ["workflow_id", "appointment_id", "confirmation_token"],
    }
    requires_permission = "appointments:reschedule"
    is_mutation = True
    is_idempotent = True
    timeout_seconds = 15.0

    async def execute(
        self,
        arguments: Dict[str, Any],
        context: ToolExecutionContext,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """Reschedule appointment through state machine."""
        wf_id_str = arguments.get("workflow_id")
        conf_token = arguments.get("confirmation_token")
        idempotency_key = arguments.get("idempotency_key")

        if not wf_id_str or not conf_token:
            return {"success": False, "error": "Missing workflow_id or confirmation_token."}

        try:
            wf_uuid = uuid.UUID(str(wf_id_str))
        except ValueError:
            return {"success": False, "error": f"Invalid workflow UUID: {wf_id_str}"}

        workflow = await AppointmentWorkflowService.get_workflow_by_id(db, wf_uuid)
        if not workflow:
            return {"success": False, "error": "Workflow not found."}

        # 1. Verify token
        if workflow.confirmation_token != conf_token.strip().upper():
            return {"success": False, "error": "Invalid or mismatched confirmation token."}

        # 2. Check policy mode
        settings_obj = await AppointmentWorkflowService.get_or_create_settings(db)
        if settings_obj.policy_mode == AutomationPolicyMode.MODE_A_READ_ONLY.value:
            return {
                "success": False,
                "error": "Rescheduling mutation is disabled in Mode A (Read Only). Staff approval required.",
                "policy_mode": settings_obj.policy_mode,
            }

        if settings_obj.policy_mode == AutomationPolicyMode.MODE_B_STAFF_APPROVAL.value:
            if workflow.approval_status != "approved":
                return {
                    "success": False,
                    "error": "Staff approval is required before rescheduling can be committed.",
                    "approval_status": workflow.approval_status,
                }

        # 3. Verify workflow state
        if workflow.status != WorkflowState.READY_TO_COMMIT.value:
            return {
                "success": False,
                "error": f"Workflow is in '{workflow.status}' state, not 'ready_to_commit'.",
            }

        # 4. Execute commit
        try:
            result = await AppointmentWorkflowService.commit_workflow(
                db=db,
                workflow_id=workflow.id,
                actor_type="deepti_agent",
                idempotency_key=idempotency_key,
            )
            return {
                "success": True,
                "message": "Appointment successfully rescheduled.",
                "details": result.get("result"),
            }
        except Exception as e:
            return {"success": False, "error": f"Reschedule commit failed: {str(e)}"}


class CancelAppointmentTool(BaseTool):
    """Mutating tool cancelling an appointment only when authorized by workflow state machine."""

    name = "cancel_appointment"
    description = (
        "Cancel an existing appointment with verified patient ownership and explicit confirmation. "
        "A casual statement containing 'cancel' must never trigger this tool directly. "
        "Strictly gated by backend confirmation token and policy."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "workflow_id": {
                "type": "string",
                "description": "UUID of the cancellation workflow",
            },
            "appointment_id": {
                "type": "string",
                "description": "UUID of the appointment to cancel",
            },
            "reason": {
                "type": "string",
                "description": "Cancellation reason",
            },
            "confirmation_token": {
                "type": "string",
                "description": "Patient confirmation token",
            },
            "idempotency_key": {
                "type": "string",
                "description": "Optional idempotency key",
            },
        },
        "required": ["workflow_id", "appointment_id", "confirmation_token"],
    }
    requires_permission = "appointments:cancel"
    is_mutation = True
    is_idempotent = True
    timeout_seconds = 15.0

    async def execute(
        self,
        arguments: Dict[str, Any],
        context: ToolExecutionContext,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """Cancel appointment through state machine."""
        wf_id_str = arguments.get("workflow_id")
        conf_token = arguments.get("confirmation_token")
        idempotency_key = arguments.get("idempotency_key")

        if not wf_id_str or not conf_token:
            return {"success": False, "error": "Missing workflow_id or confirmation_token."}

        try:
            wf_uuid = uuid.UUID(str(wf_id_str))
        except ValueError:
            return {"success": False, "error": f"Invalid workflow UUID: {wf_id_str}"}

        workflow = await AppointmentWorkflowService.get_workflow_by_id(db, wf_uuid)
        if not workflow:
            return {"success": False, "error": "Workflow not found."}

        # 1. Verify token
        if workflow.confirmation_token != conf_token.strip().upper():
            return {"success": False, "error": "Invalid or mismatched confirmation token."}

        # 2. Check policy mode
        settings_obj = await AppointmentWorkflowService.get_or_create_settings(db)
        if settings_obj.policy_mode == AutomationPolicyMode.MODE_A_READ_ONLY.value:
            return {
                "success": False,
                "error": "Cancellation mutation is disabled in Mode A (Read Only). Staff approval required.",
                "policy_mode": settings_obj.policy_mode,
            }

        if settings_obj.policy_mode == AutomationPolicyMode.MODE_B_STAFF_APPROVAL.value:
            if workflow.approval_status != "approved":
                return {
                    "success": False,
                    "error": "Staff approval is required before cancellation can be committed.",
                    "approval_status": workflow.approval_status,
                }

        # 3. Verify workflow state
        if workflow.status != WorkflowState.READY_TO_COMMIT.value:
            return {
                "success": False,
                "error": f"Workflow is in '{workflow.status}' state, not 'ready_to_commit'.",
            }

        # 4. Execute commit
        try:
            result = await AppointmentWorkflowService.commit_workflow(
                db=db,
                workflow_id=workflow.id,
                actor_type="deepti_agent",
                idempotency_key=idempotency_key,
            )
            return {
                "success": True,
                "message": "Appointment successfully cancelled.",
                "details": result.get("result"),
            }
        except Exception as e:
            return {"success": False, "error": f"Cancellation commit failed: {str(e)}"}
