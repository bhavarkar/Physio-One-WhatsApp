"""Appointment Workflow State Machine Engine.

Single Organization Edition: Physio One Clinic.
Coordinates intent-driven appointment lifecycles: collecting information, availability lookup,
slot selection, patient confirmation, staff approvals, and transactional mutation via AppointmentService.
Enforces strict policy isolation (Mode A Read Only by default).
"""
import uuid
import logging
from datetime import datetime, date, time, timedelta, timezone
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, and_, or_
from sqlalchemy.orm import selectinload, joinedload

from app.core.config import settings
from app.models.workflow import (
    AppointmentAIWorkflow,
    AppointmentWorkflowEvent,
    AppointmentConfirmation,
    AppointmentApprovalRequest,
    AppointmentOperationIdempotency,
    AppointmentWorkflowSettings,
)
from app.models.patient import Patient, Appointment, AppointmentHistory
from app.models.whatsapp import Conversation, WhatsAppContact
from app.models.user import User
from app.schemas.workflow import WorkflowIntent, WorkflowState, AutomationPolicyMode
from app.services.appointment_service import (
    AppointmentService,
    AppointmentServiceError,
    SundayRestrictionError,
    OperatingHoursViolationError,
    PastAppointmentError,
    AppointmentConflictError,
    InvalidStatusTransitionError,
    AppointmentNotFoundError,
    get_clinic_tz,
    normalize_to_clinic_tz,
    normalize_to_utc,
    ensure_utc_aware,
)
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentRescheduleRequest,
    AppointmentCancelRequest,
)

logger = logging.getLogger("physio_one.appointment.workflow")


class WorkflowError(Exception):
    """Base exception for workflow state machine violations."""
    def __init__(self, message: str, code: str = "WORKFLOW_ERROR", details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}


class WorkflowPolicyViolationError(WorkflowError):
    """Raised when an operation violates configured automation policy."""
    def __init__(self, message: str = "Appointment mutation not allowed by current policy mode.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="POLICY_VIOLATION", details=details)


class WorkflowStateError(WorkflowError):
    """Raised when an operation is invalid for current workflow state."""
    def __init__(self, message: str = "Invalid workflow state transition.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="INVALID_WORKFLOW_STATE", details=details)


class ConfirmationRequiredError(WorkflowError):
    """Raised when explicit patient confirmation is missing or expired."""
    def __init__(self, message: str = "Explicit patient confirmation is required.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="CONFIRMATION_REQUIRED", details=details)


class ApprovalRequiredError(WorkflowError):
    """Raised when staff approval is required before mutation."""
    def __init__(self, message: str = "Staff approval is required before committing this appointment operation.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="APPROVAL_REQUIRED", details=details)


class AppointmentWorkflowService:
    """Persistent state machine for clinical appointment workflows."""

    @classmethod
    async def get_or_create_settings(cls, db: AsyncSession) -> AppointmentWorkflowSettings:
        """Fetch singleton workflow automation settings, creating default Mode A if missing."""
        stmt = select(AppointmentWorkflowSettings).limit(1)
        setting = (await db.execute(stmt)).scalar_one_or_none()
        if not setting:
            setting = AppointmentWorkflowSettings(
                policy_mode=AutomationPolicyMode.MODE_A_READ_ONLY.value,
                require_patient_confirmation=True,
                workflow_expiry_minutes=30,
                confirmation_expiry_minutes=15,
                max_reschedule_count=3,
                allow_cancellation_within_hours=2,
                is_active=True,
            )
            db.add(setting)
            await db.commit()
            await db.refresh(setting)
        return setting

    @classmethod
    async def get_active_workflow(
        cls,
        db: AsyncSession,
        conversation_id: uuid.UUID,
    ) -> Optional[AppointmentAIWorkflow]:
        """Fetch currently active workflow for conversation, auto-expiring stale workflows."""
        terminal_statuses = [
            WorkflowState.CONFIRMED.value,
            WorkflowState.CANCELLED.value,
            WorkflowState.EXPIRED.value,
            WorkflowState.FAILED.value,
            WorkflowState.HUMAN_HANDOFF.value,
        ]
        stmt = (
            select(AppointmentAIWorkflow)
            .options(
                selectinload(AppointmentAIWorkflow.events),
                selectinload(AppointmentAIWorkflow.confirmations),
                selectinload(AppointmentAIWorkflow.approval_requests),
                joinedload(AppointmentAIWorkflow.patient),
            )
            .where(
                AppointmentAIWorkflow.conversation_id == conversation_id,
                AppointmentAIWorkflow.status.not_in(terminal_statuses),
            )
            .order_by(AppointmentAIWorkflow.created_at.desc())
            .limit(1)
        )
        workflow = (await db.execute(stmt)).scalar_one_or_none()
        if not workflow:
            return None

        # Check expiration
        now_utc = datetime.now(timezone.utc)
        if workflow.expires_at and ensure_utc_aware(workflow.expires_at) < now_utc:
            workflow.status = WorkflowState.EXPIRED.value
            event = AppointmentWorkflowEvent(
                workflow_id=workflow.id,
                from_status=workflow.status,
                to_status=WorkflowState.EXPIRED.value,
                event_type="workflow_expired",
                actor_type="system",
                notes="Workflow reached expiration time without completion.",
            )
            db.add(event)
            await db.commit()
            return None

        return workflow

    @classmethod
    async def get_workflow_by_id(
        cls,
        db: AsyncSession,
        workflow_id: uuid.UUID,
    ) -> Optional[AppointmentAIWorkflow]:
        """Fetch detailed workflow record by ID."""
        stmt = (
            select(AppointmentAIWorkflow)
            .options(
                selectinload(AppointmentAIWorkflow.events),
                selectinload(AppointmentAIWorkflow.confirmations),
                selectinload(AppointmentAIWorkflow.approval_requests),
                joinedload(AppointmentAIWorkflow.patient),
            )
            .where(AppointmentAIWorkflow.id == workflow_id)
        )
        return (await db.execute(stmt)).scalar_one_or_none()

    @classmethod
    async def start_workflow(
        cls,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        contact_id: uuid.UUID,
        intent: str,
        target_date: Optional[str] = None,
        preferred_time: Optional[str] = None,
        service_type: Optional[str] = None,
        appointment_id: Optional[uuid.UUID] = None,
        practitioner_name: str = "Dr. Physio One",
        duration_minutes: int = 45,
        collected_data: Optional[Dict[str, Any]] = None,
        actor_type: str = "deepti_agent",
    ) -> AppointmentAIWorkflow:
        """Initialize or supersede active workflow for a conversation."""
        # 1. Supersede any existing active workflow
        active = await cls.get_active_workflow(db, conversation_id)
        if active:
            active.status = WorkflowState.CANCELLED.value
            active.error_message = f"Superseded by new workflow intent: {intent}"
            ev = AppointmentWorkflowEvent(
                workflow_id=active.id,
                from_status=active.status,
                to_status=WorkflowState.CANCELLED.value,
                event_type="workflow_superseded",
                actor_type=actor_type,
                notes=f"New workflow started with intent '{intent}'.",
            )
            db.add(ev)
            await db.flush()

        # 2. Resolve Contact and Patient
        stmt_c = select(WhatsAppContact).options(selectinload(WhatsAppContact.patient)).where(WhatsAppContact.id == contact_id)
        contact = (await db.execute(stmt_c)).scalar_one_or_none()
        patient_id = None
        if contact:
            if contact.patient:
                patient_id = contact.patient.id
            else:
                p_stmt = select(Patient).where(Patient.phone_number == contact.wa_id)
                pat = (await db.execute(p_stmt)).scalars().first()
                if pat:
                    patient_id = pat.id

        # 3. Resolve initial state based on intent and provided parameters
        initial_status = WorkflowState.COLLECTING_INFORMATION.value
        if intent == WorkflowIntent.CHECK_AVAILABILITY.value:
            initial_status = WorkflowState.CHECKING_AVAILABILITY.value
        elif intent == WorkflowIntent.BOOK_APPOINTMENT.value:
            if target_date:
                initial_status = WorkflowState.CHECKING_AVAILABILITY.value
            else:
                initial_status = WorkflowState.COLLECTING_INFORMATION.value
        elif intent == WorkflowIntent.REQUEST_HUMAN_ASSISTANCE.value:
            initial_status = WorkflowState.HUMAN_HANDOFF.value

        settings_obj = await cls.get_or_create_settings(db)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings_obj.workflow_expiry_minutes)

        collected = collected_data or {}
        if target_date:
            collected["target_date"] = target_date
        if preferred_time:
            collected["preferred_time"] = preferred_time

        workflow = AppointmentAIWorkflow(
            conversation_id=conversation_id,
            contact_id=contact_id,
            patient_id=patient_id,
            appointment_id=appointment_id,
            intent=intent,
            status=initial_status,
            workflow_version=1,
            practitioner_name=practitioner_name,
            service_type=service_type or "Initial Physiotherapy Assessment",
            duration_minutes=duration_minutes,
            collected_data=collected,
            proposed_changes={},
            confirmation_status="pending",
            approval_status="not_required",
            expires_at=expires_at,
        )
        db.add(workflow)
        await db.flush()

        event = AppointmentWorkflowEvent(
            workflow_id=workflow.id,
            from_status=None,
            to_status=workflow.status,
            event_type="workflow_started",
            actor_type=actor_type,
            payload={
                "intent": intent,
                "target_date": target_date,
                "preferred_time": preferred_time,
                "initial_status": initial_status,
            },
            notes=f"Started {intent} workflow.",
        )
        db.add(event)
        await db.commit()
        await db.refresh(workflow)
        return workflow

    @classmethod
    async def select_slot(
        cls,
        db: AsyncSession,
        workflow_id: uuid.UUID,
        slot_start: datetime,
        slot_end: Optional[datetime] = None,
        actor_type: str = "patient",
    ) -> AppointmentAIWorkflow:
        """Select a verified slot and prepare patient confirmation summary."""
        workflow = await cls.get_workflow_by_id(db, workflow_id)
        if not workflow:
            raise WorkflowError("Workflow not found.", code="WORKFLOW_NOT_FOUND")

        if workflow.status in [WorkflowState.CONFIRMED.value, WorkflowState.CANCELLED.value, WorkflowState.EXPIRED.value]:
            raise WorkflowStateError(f"Cannot select slot in terminal state '{workflow.status}'.")

        slot_start_utc = normalize_to_utc(slot_start)
        duration = workflow.duration_minutes or 45
        slot_end_utc = slot_start_utc + timedelta(minutes=duration) if not slot_end else normalize_to_utc(slot_end)

        # 1. Validate slot availability via AppointmentService
        local_date = normalize_to_clinic_tz(slot_start_utc).date()
        avail = await AppointmentService.get_daily_availability(
            db=db,
            target_date=local_date,
            duration_minutes=duration,
            practitioner_name=workflow.practitioner_name,
        )

        if not avail.is_open:
            raise SundayRestrictionError(avail.message or "Clinic is closed on requested date.")

        # Check if selected slot matches an available slot
        is_matched = False
        for s in avail.slots:
            if s.is_available:
                s_start = ensure_utc_aware(s.start_time)
                if abs((s_start - slot_start_utc).total_seconds()) < 60:
                    is_matched = True
                    break

        if not is_matched:
            raise AppointmentConflictError("The requested slot is no longer available. Please select another time.")

        # 2. Update workflow proposal
        workflow.selected_slot_start = slot_start_utc
        workflow.selected_slot_end = slot_end_utc
        workflow.workflow_version += 1

        local_start_str = normalize_to_clinic_tz(slot_start_utc).strftime("%A, %b %d, %Y at %I:%M %p")
        proposed = {
            "practitioner": workflow.practitioner_name,
            "service_type": workflow.service_type,
            "start_time_iso": slot_start_utc.isoformat(),
            "end_time_iso": slot_end_utc.isoformat(),
            "formatted_display": local_start_str,
            "duration_minutes": duration,
        }
        workflow.proposed_changes = proposed

        # 3. Generate confirmation token and summary
        settings_obj = await cls.get_or_create_settings(db)
        conf_token = uuid.uuid4().hex[:12].upper()
        conf_expiry = datetime.now(timezone.utc) + timedelta(minutes=settings_obj.confirmation_expiry_minutes)

        summary_text = (
            f"Please confirm your appointment for {workflow.service_type} on {local_start_str} "
            f"with {workflow.practitioner_name}. Reply YES to confirm or NO to cancel."
        )

        confirmation = AppointmentConfirmation(
            workflow_id=workflow.id,
            confirmation_token=conf_token,
            summary_text=summary_text,
            slot_start=slot_start_utc,
            slot_end=slot_end_utc,
            is_confirmed=False,
            expires_at=conf_expiry,
        )
        db.add(confirmation)

        old_status = workflow.status
        workflow.status = WorkflowState.AWAITING_PATIENT_CONFIRMATION.value
        workflow.confirmation_status = "pending"
        workflow.confirmation_token = conf_token
        workflow.confirmation_requested_at = datetime.now(timezone.utc)

        # Invalidate previous approvals if version changed
        workflow.approval_status = "not_required"
        workflow.approved_by_id = None
        workflow.approved_at = None

        event = AppointmentWorkflowEvent(
            workflow_id=workflow.id,
            from_status=old_status,
            to_status=workflow.status,
            event_type="slot_selected",
            actor_type=actor_type,
            payload={
                "slot_start": slot_start_utc.isoformat(),
                "slot_end": slot_end_utc.isoformat(),
                "confirmation_token": conf_token,
                "version": workflow.workflow_version,
            },
            notes=f"Selected slot {local_start_str}. Awaiting patient confirmation.",
        )
        db.add(event)
        await db.commit()
        await db.refresh(workflow)
        return workflow

    @classmethod
    async def process_patient_confirmation(
        cls,
        db: AsyncSession,
        workflow_id: uuid.UUID,
        is_confirmed: bool,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Handle patient explicit confirmation or rejection message."""
        workflow = await cls.get_workflow_by_id(db, workflow_id)
        if not workflow:
            raise WorkflowError("Workflow not found.", code="WORKFLOW_NOT_FOUND")

        if workflow.status != WorkflowState.AWAITING_PATIENT_CONFIRMATION.value:
            raise WorkflowStateError(f"Workflow is not awaiting confirmation (status: '{workflow.status}').")

        now_utc = datetime.now(timezone.utc)

        if not is_confirmed:
            # Patient rejected / declined proposed slot
            old_status = workflow.status
            workflow.status = WorkflowState.CANCELLED.value
            workflow.confirmation_status = "rejected"
            event = AppointmentWorkflowEvent(
                workflow_id=workflow.id,
                from_status=old_status,
                to_status=workflow.status,
                event_type="patient_rejected",
                actor_type="patient",
                notes=notes or "Patient rejected proposed appointment.",
            )
            db.add(event)
            await db.commit()
            return {"status": "rejected", "message": "Appointment proposal cancelled per patient request."}

        # Patient confirmed!
        workflow.confirmation_status = "confirmed"
        workflow.confirmed_at = now_utc

        # Update confirmation entity
        stmt_conf = (
            select(AppointmentConfirmation)
            .where(
                AppointmentConfirmation.workflow_id == workflow.id,
                AppointmentConfirmation.confirmation_token == workflow.confirmation_token,
            )
            .order_by(AppointmentConfirmation.created_at.desc())
        )
        conf_record = (await db.execute(stmt_conf)).scalar_one_or_none()
        if conf_record:
            conf_record.is_confirmed = True
            conf_record.confirmed_at = now_utc

        settings_obj = await cls.get_or_create_settings(db)
        policy_mode = settings_obj.policy_mode

        old_status = workflow.status

        # Evaluate Policy Routing
        if policy_mode == AutomationPolicyMode.MODE_B_STAFF_APPROVAL.value:
            # Queue for staff review
            workflow.status = WorkflowState.AWAITING_STAFF_APPROVAL.value
            workflow.approval_status = "pending"

            # Create approval request
            approval_req = AppointmentApprovalRequest(
                workflow_id=workflow.id,
                workflow_version=workflow.workflow_version,
                operation=workflow.intent,
                status="pending",
                proposal_summary=workflow.proposed_changes,
                notes="Patient confirmed. Awaiting clinic staff review.",
            )
            db.add(approval_req)

            event = AppointmentWorkflowEvent(
                workflow_id=workflow.id,
                from_status=old_status,
                to_status=workflow.status,
                event_type="patient_confirmed",
                actor_type="patient",
                payload={"policy_mode": policy_mode, "workflow_version": workflow.workflow_version},
                notes="Patient confirmed. Operation queued for staff approval.",
            )
            db.add(event)
            await db.commit()
            return {
                "status": "awaiting_staff_approval",
                "message": "Appointment confirmed by patient. Waiting for clinic staff approval.",
            }

        elif policy_mode == AutomationPolicyMode.MODE_C_CONTROLLED_AUTOMATIC.value:
            # Auto-commit if all preconditions pass
            workflow.status = WorkflowState.READY_TO_COMMIT.value
            workflow.approval_status = "not_required"

            event = AppointmentWorkflowEvent(
                workflow_id=workflow.id,
                from_status=old_status,
                to_status=workflow.status,
                event_type="patient_confirmed",
                actor_type="patient",
                payload={"policy_mode": policy_mode},
                notes="Patient confirmed. Proceeding to automatic commit.",
            )
            db.add(event)
            await db.commit()

            # Execute transactional commit
            return await cls.commit_workflow(db, workflow.id, actor_type="system")

        else:
            # Mode A (Read Only) - Default!
            # Under Mode A, autonomous mutations are strictly disabled.
            workflow.status = WorkflowState.AWAITING_STAFF_APPROVAL.value
            workflow.approval_status = "pending"

            approval_req = AppointmentApprovalRequest(
                workflow_id=workflow.id,
                workflow_version=workflow.workflow_version,
                operation=workflow.intent,
                status="pending",
                proposal_summary=workflow.proposed_changes,
                notes="Mode A Read Only: Staff manual approval required before mutation.",
            )
            db.add(approval_req)

            event = AppointmentWorkflowEvent(
                workflow_id=workflow.id,
                from_status=old_status,
                to_status=workflow.status,
                event_type="patient_confirmed",
                actor_type="patient",
                payload={"policy_mode": policy_mode},
                notes="Patient confirmed. Auto-commit disabled in Mode A; staff approval required.",
            )
            db.add(event)
            await db.commit()
            return {
                "status": "awaiting_staff_approval",
                "message": "Appointment details confirmed. Clinic staff will verify and finalize your booking.",
            }

    @classmethod
    async def approve_proposal(
        cls,
        db: AsyncSession,
        workflow_id: uuid.UUID,
        staff_user: User,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Staff approves a pending appointment workflow proposal."""
        workflow = await cls.get_workflow_by_id(db, workflow_id)
        if not workflow:
            raise WorkflowError("Workflow not found.", code="WORKFLOW_NOT_FOUND")

        if workflow.status != WorkflowState.AWAITING_STAFF_APPROVAL.value:
            raise WorkflowStateError(f"Workflow is not awaiting staff approval (status: '{workflow.status}').")

        # Find pending approval request matching latest version
        stmt_apr = (
            select(AppointmentApprovalRequest)
            .where(
                AppointmentApprovalRequest.workflow_id == workflow.id,
                AppointmentApprovalRequest.workflow_version == workflow.workflow_version,
                AppointmentApprovalRequest.status == "pending",
            )
            .order_by(AppointmentApprovalRequest.created_at.desc())
        )
        approval_req = (await db.execute(stmt_apr)).scalar_one_or_none()
        if not approval_req:
            raise WorkflowError("No matching pending approval request found for current workflow version.")

        now_utc = datetime.now(timezone.utc)
        approval_req.status = "approved"
        approval_req.staff_id = staff_user.id
        approval_req.decision_at = now_utc
        approval_req.notes = notes

        workflow.approval_status = "approved"
        workflow.approved_by_id = staff_user.id
        workflow.approved_at = now_utc
        workflow.status = WorkflowState.READY_TO_COMMIT.value

        event = AppointmentWorkflowEvent(
            workflow_id=workflow.id,
            from_status=WorkflowState.AWAITING_STAFF_APPROVAL.value,
            to_status=WorkflowState.READY_TO_COMMIT.value,
            event_type="staff_approved",
            actor_type="staff",
            actor_id=staff_user.id,
            payload={"version": workflow.workflow_version},
            notes=notes or f"Approved by staff member {staff_user.full_name}.",
        )
        db.add(event)
        await db.commit()

        # Commit approved workflow
        return await cls.commit_workflow(
            db=db,
            workflow_id=workflow.id,
            actor_type="staff",
            actor_id=staff_user.id,
        )

    @classmethod
    async def reject_proposal(
        cls,
        db: AsyncSession,
        workflow_id: uuid.UUID,
        staff_user: User,
        reason: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Staff rejects a pending appointment workflow proposal."""
        workflow = await cls.get_workflow_by_id(db, workflow_id)
        if not workflow:
            raise WorkflowError("Workflow not found.", code="WORKFLOW_NOT_FOUND")

        if workflow.status != WorkflowState.AWAITING_STAFF_APPROVAL.value:
            raise WorkflowStateError(f"Workflow is not awaiting staff approval (status: '{workflow.status}').")

        stmt_apr = (
            select(AppointmentApprovalRequest)
            .where(
                AppointmentApprovalRequest.workflow_id == workflow.id,
                AppointmentApprovalRequest.workflow_version == workflow.workflow_version,
                AppointmentApprovalRequest.status == "pending",
            )
        )
        approval_req = (await db.execute(stmt_apr)).scalar_one_or_none()
        now_utc = datetime.now(timezone.utc)
        if approval_req:
            approval_req.status = "rejected"
            approval_req.staff_id = staff_user.id
            approval_req.decision_at = now_utc
            approval_req.notes = notes or reason

        workflow.approval_status = "rejected"
        workflow.rejection_reason = reason or "Rejected by clinic staff."
        workflow.status = WorkflowState.CANCELLED.value

        event = AppointmentWorkflowEvent(
            workflow_id=workflow.id,
            from_status=WorkflowState.AWAITING_STAFF_APPROVAL.value,
            to_status=WorkflowState.CANCELLED.value,
            event_type="staff_rejected",
            actor_type="staff",
            actor_id=staff_user.id,
            payload={"reason": reason},
            notes=notes or f"Rejected by staff member {staff_user.full_name}: {reason}",
        )
        db.add(event)
        await db.commit()
        return {"status": "rejected", "reason": reason}

    @classmethod
    async def request_clarification(
        cls,
        db: AsyncSession,
        workflow_id: uuid.UUID,
        staff_user: User,
        notes: str,
    ) -> Dict[str, Any]:
        """Staff requests additional clarification from patient."""
        workflow = await cls.get_workflow_by_id(db, workflow_id)
        if not workflow:
            raise WorkflowError("Workflow not found.", code="WORKFLOW_NOT_FOUND")

        stmt_apr = (
            select(AppointmentApprovalRequest)
            .where(
                AppointmentApprovalRequest.workflow_id == workflow.id,
                AppointmentApprovalRequest.workflow_version == workflow.workflow_version,
                AppointmentApprovalRequest.status == "pending",
            )
        )
        approval_req = (await db.execute(stmt_apr)).scalar_one_or_none()
        now_utc = datetime.now(timezone.utc)
        if approval_req:
            approval_req.status = "clarification_requested"
            approval_req.staff_id = staff_user.id
            approval_req.decision_at = now_utc
            approval_req.notes = notes

        workflow.approval_status = "clarification_requested"
        workflow.clarification_notes = notes
        workflow.status = WorkflowState.COLLECTING_INFORMATION.value

        event = AppointmentWorkflowEvent(
            workflow_id=workflow.id,
            from_status=WorkflowState.AWAITING_STAFF_APPROVAL.value,
            to_status=WorkflowState.COLLECTING_INFORMATION.value,
            event_type="clarification_requested",
            actor_type="staff",
            actor_id=staff_user.id,
            payload={"notes": notes},
            notes=f"Clarification requested by {staff_user.full_name}: {notes}",
        )
        db.add(event)
        await db.commit()
        return {"status": "clarification_requested", "notes": notes}

    @classmethod
    async def commit_workflow(
        cls,
        db: AsyncSession,
        workflow_id: uuid.UUID,
        actor_type: str = "system",
        actor_id: Optional[uuid.UUID] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute authoritative mutation against AppointmentService within transactional boundaries."""
        workflow = await cls.get_workflow_by_id(db, workflow_id)
        if not workflow:
            raise WorkflowError("Workflow not found.", code="WORKFLOW_NOT_FOUND")

        if workflow.status != WorkflowState.READY_TO_COMMIT.value:
            raise WorkflowStateError(
                f"Workflow must be in 'ready_to_commit' state before mutation (current: '{workflow.status}')."
            )

        # 1. Idempotency Check
        idem_key = idempotency_key or f"wf_commit_{workflow.id}_v{workflow.workflow_version}"
        stmt_idem = select(AppointmentOperationIdempotency).where(
            AppointmentOperationIdempotency.idempotency_key == idem_key
        )
        existing_idem = (await db.execute(stmt_idem)).scalar_one_or_none()
        if existing_idem:
            if existing_idem.status == "completed":
                logger.info(f"Idempotent retry detected for key '{idem_key}'. Returning stored result.")
                return existing_idem.result or {"status": "completed", "already_processed": True}
            elif existing_idem.status == "in_progress":
                raise WorkflowError("Operation currently in progress. Please wait.", code="CONCURRENT_OPERATION")

        idem_record = AppointmentOperationIdempotency(
            idempotency_key=idem_key,
            workflow_id=workflow.id,
            operation=workflow.intent,
            status="in_progress",
        )
        db.add(idem_record)
        await db.flush()

        old_status = workflow.status
        workflow.status = WorkflowState.COMMITTING.value
        await db.flush()

        try:
            # 2. Re-resolve Patient Record
            patient_id = workflow.patient_id
            if not patient_id:
                # Lookup or create patient from contact
                stmt_c = select(WhatsAppContact).where(WhatsAppContact.id == workflow.contact_id)
                contact = (await db.execute(stmt_c)).scalar_one_or_none()
                if contact:
                    pat_name = workflow.collected_data.get("patient_name") or contact.full_name or "WhatsApp Patient"
                    pat_phone = contact.phone_number
                    # Look up existing patient by phone
                    pat_stmt = select(Patient).where(Patient.phone_number == pat_phone)
                    pat = (await db.execute(pat_stmt)).scalars().first()
                    if pat:
                        patient_id = pat.id
                    else:
                        new_pat = Patient(
                            contact_id=contact.id,
                            full_name=pat_name,
                            phone_number=pat_phone,
                        )
                        db.add(new_pat)
                        await db.flush()
                        patient_id = new_pat.id
                    workflow.patient_id = patient_id

            # 3. Route to Authoritative Operation in AppointmentService
            committed_appointment: Optional[Appointment] = None
            result_payload: Dict[str, Any] = {}

            if workflow.intent == WorkflowIntent.BOOK_APPOINTMENT.value:
                if not workflow.selected_slot_start:
                    raise WorkflowError("Cannot book appointment without a selected slot.")

                create_req = AppointmentCreate(
                    patient_id=patient_id,
                    practitioner_name=workflow.practitioner_name,
                    service_type=workflow.service_type,
                    start_time=ensure_utc_aware(workflow.selected_slot_start),
                    duration_minutes=workflow.duration_minutes,
                    notes=f"Booked via Deepti AI Receptionist (Workflow {workflow.id})",
                    booked_by="deepti_agent",
                )
                committed_appointment = await AppointmentService.create_appointment(
                    db=db,
                    data=create_req,
                    actor_type=actor_type,
                )
                workflow.appointment_id = committed_appointment.id
                result_payload = {
                    "operation": "booked",
                    "appointment_id": str(committed_appointment.id),
                    "patient_id": str(patient_id),
                    "start_time": committed_appointment.start_time.isoformat(),
                    "end_time": committed_appointment.end_time.isoformat(),
                    "practitioner": committed_appointment.practitioner_name,
                    "service_type": committed_appointment.service_type,
                    "status": committed_appointment.status,
                }

            elif workflow.intent == WorkflowIntent.RESCHEDULE_APPOINTMENT.value:
                if not workflow.appointment_id:
                    raise WorkflowError("Rescheduling requires an identified appointment_id.")
                if not workflow.selected_slot_start:
                    raise WorkflowError("Rescheduling requires a selected new slot.")

                reschedule_req = AppointmentRescheduleRequest(
                    new_start_time=ensure_utc_aware(workflow.selected_slot_start),
                    duration_minutes=workflow.duration_minutes,
                    reason=workflow.collected_data.get("reason") or "Patient requested reschedule via Deepti AI",
                )
                committed_appointment = await AppointmentService.reschedule_appointment(
                    db=db,
                    appointment_id=workflow.appointment_id,
                    data=reschedule_req,
                    actor_type=actor_type,
                )
                result_payload = {
                    "operation": "rescheduled",
                    "appointment_id": str(committed_appointment.id),
                    "start_time": committed_appointment.start_time.isoformat(),
                    "end_time": committed_appointment.end_time.isoformat(),
                    "status": committed_appointment.status,
                }

            elif workflow.intent == WorkflowIntent.CANCEL_APPOINTMENT.value:
                if not workflow.appointment_id:
                    raise WorkflowError("Cancellation requires an identified appointment_id.")

                cancel_req = AppointmentCancelRequest(
                    reason=workflow.collected_data.get("cancellation_reason") or "Patient requested cancellation via Deepti AI",
                    notes="Cancelled via Deepti AI Receptionist workflow",
                )
                committed_appointment = await AppointmentService.cancel_appointment(
                    db=db,
                    appointment_id=workflow.appointment_id,
                    data=cancel_req,
                    actor_type=actor_type,
                )
                result_payload = {
                    "operation": "cancelled",
                    "appointment_id": str(committed_appointment.id),
                    "cancelled_at": committed_appointment.cancelled_at.isoformat() if committed_appointment.cancelled_at else None,
                    "status": committed_appointment.status,
                }
            else:
                raise WorkflowError(f"Unsupported intent for commit: '{workflow.intent}'")

            # 4. Finalize Workflow State
            workflow.status = WorkflowState.CONFIRMED.value
            workflow.error_message = None

            idem_record.status = "completed"
            idem_record.result = result_payload

            event = AppointmentWorkflowEvent(
                workflow_id=workflow.id,
                from_status=old_status,
                to_status=WorkflowState.CONFIRMED.value,
                event_type="workflow_committed",
                actor_type=actor_type,
                actor_id=actor_id,
                payload=result_payload,
                notes=f"Successfully committed {workflow.intent}.",
            )
            db.add(event)
            await db.commit()
            return {
                "success": True,
                "status": "confirmed",
                "workflow_id": str(workflow.id),
                "result": result_payload,
            }

        except Exception as exc:
            logger.exception("Failed to commit appointment workflow %s: %s", workflow.id, str(exc))
            workflow.status = WorkflowState.FAILED.value
            workflow.error_message = str(exc)
            idem_record.status = "failed"
            idem_record.result = {"error": str(exc)}

            event = AppointmentWorkflowEvent(
                workflow_id=workflow.id,
                from_status=old_status,
                to_status=WorkflowState.FAILED.value,
                event_type="workflow_commit_failed",
                actor_type=actor_type,
                actor_id=actor_id,
                payload={"error": str(exc)},
                notes=f"Commit failure: {str(exc)}",
            )
            db.add(event)
            await db.commit()
            raise
