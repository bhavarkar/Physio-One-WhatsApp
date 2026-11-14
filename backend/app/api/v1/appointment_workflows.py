"""Appointment Workflows and Approvals API Endpoints.

Single Organization Edition: Physio One Clinic.
Provides authenticated endpoints for inspecting appointment workflows, managing the human
approval queue, approving or rejecting proposals, and configuring automation policies.
"""
from typing import Optional, List
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload, joinedload

from app.core.database import get_db
from app.api.deps import get_current_user, require_permission
from app.models.user import User
from app.models.workflow import (
    AppointmentAIWorkflow,
    AppointmentWorkflowSettings,
    AppointmentApprovalRequest,
)
from app.models.patient import Patient
from app.schemas.workflow import (
    AppointmentWorkflowResponse,
    AppointmentWorkflowListResponse,
    AppointmentWorkflowSettingsResponse,
    AppointmentWorkflowSettingsUpdate,
    ApprovalActionRequest,
    WorkflowEventResponse,
    AppointmentConfirmationResponse,
    AppointmentApprovalRequestResponse,
)
from app.services.workflow_service import AppointmentWorkflowService, WorkflowError

router = APIRouter(prefix="/appointment-workflows", tags=["Appointment Workflows"])


def _serialize_workflow(wf: AppointmentAIWorkflow) -> AppointmentWorkflowResponse:
    """Helper to convert workflow entity to response model."""
    pat_name = wf.patient.full_name if wf.patient else wf.collected_data.get("patient_name")
    pat_phone = wf.patient.phone_number if wf.patient else wf.collected_data.get("patient_phone")

    events = [
        WorkflowEventResponse.model_validate(e)
        for e in (wf.events or [])
    ]
    confirmations = [
        AppointmentConfirmationResponse.model_validate(c)
        for c in (wf.confirmations or [])
    ]
    approvals = [
        AppointmentApprovalRequestResponse.model_validate(a)
        for a in (wf.approval_requests or [])
    ]

    return AppointmentWorkflowResponse(
        id=wf.id,
        conversation_id=wf.conversation_id,
        contact_id=wf.contact_id,
        patient_id=wf.patient_id,
        patient_name=pat_name,
        patient_phone=pat_phone,
        appointment_id=wf.appointment_id,
        intent=wf.intent,
        status=wf.status,
        workflow_version=wf.workflow_version,
        selected_slot_start=wf.selected_slot_start,
        selected_slot_end=wf.selected_slot_end,
        practitioner_name=wf.practitioner_name,
        service_type=wf.service_type,
        duration_minutes=wf.duration_minutes,
        collected_data=wf.collected_data or {},
        proposed_changes=wf.proposed_changes or {},
        confirmation_status=wf.confirmation_status,
        confirmation_token=wf.confirmation_token,
        confirmation_requested_at=wf.confirmation_requested_at,
        confirmed_at=wf.confirmed_at,
        approval_status=wf.approval_status,
        approved_by_id=wf.approved_by_id,
        approved_at=wf.approved_at,
        rejection_reason=wf.rejection_reason,
        clarification_notes=wf.clarification_notes,
        expires_at=wf.expires_at,
        error_message=wf.error_message,
        created_at=wf.created_at,
        updated_at=wf.updated_at,
        events=events,
        confirmations=confirmations,
        approval_requests=approvals,
    )


@router.get(
    "/settings",
    response_model=AppointmentWorkflowSettingsResponse,
    dependencies=[Depends(require_permission("appointments", "read"))],
)
async def get_workflow_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve system-wide appointment automation policy settings."""
    settings_obj = await AppointmentWorkflowService.get_or_create_settings(db)
    return AppointmentWorkflowSettingsResponse.model_validate(settings_obj)


@router.patch(
    "/settings",
    response_model=AppointmentWorkflowSettingsResponse,
    dependencies=[Depends(require_permission("settings", "update"))],
)
async def update_workflow_settings(
    payload: AppointmentWorkflowSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update appointment automation policy mode and timeouts (Owner/Admin only)."""
    settings_obj = await AppointmentWorkflowService.get_or_create_settings(db)

    if payload.policy_mode is not None:
        settings_obj.policy_mode = payload.policy_mode.value
    if payload.require_patient_confirmation is not None:
        settings_obj.require_patient_confirmation = payload.require_patient_confirmation
    if payload.workflow_expiry_minutes is not None:
        settings_obj.workflow_expiry_minutes = payload.workflow_expiry_minutes
    if payload.confirmation_expiry_minutes is not None:
        settings_obj.confirmation_expiry_minutes = payload.confirmation_expiry_minutes
    if payload.max_reschedule_count is not None:
        settings_obj.max_reschedule_count = payload.max_reschedule_count
    if payload.allow_cancellation_within_hours is not None:
        settings_obj.allow_cancellation_within_hours = payload.allow_cancellation_within_hours

    await db.commit()
    await db.refresh(settings_obj)
    return AppointmentWorkflowSettingsResponse.model_validate(settings_obj)


@router.get(
    "/approvals",
    response_model=List[AppointmentWorkflowResponse],
    dependencies=[Depends(require_permission("appointments", "read"))],
)
async def list_pending_approvals(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all appointment workflows currently awaiting staff approval."""
    stmt = (
        select(AppointmentAIWorkflow)
        .options(
            selectinload(AppointmentAIWorkflow.events),
            selectinload(AppointmentAIWorkflow.confirmations),
            selectinload(AppointmentAIWorkflow.approval_requests),
            joinedload(AppointmentAIWorkflow.patient),
        )
        .where(AppointmentAIWorkflow.status == "awaiting_staff_approval")
        .order_by(AppointmentAIWorkflow.created_at.desc())
    )
    workflows = (await db.execute(stmt)).scalars().all()
    return [_serialize_workflow(w) for w in workflows]


@router.get(
    "",
    response_model=AppointmentWorkflowListResponse,
    dependencies=[Depends(require_permission("appointments", "read"))],
)
async def list_workflows(
    status: Optional[str] = Query(None),
    intent: Optional[str] = Query(None),
    conversation_id: Optional[uuid.UUID] = Query(None),
    patient_id: Optional[uuid.UUID] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List appointment workflows with filtering and pagination."""
    query = (
        select(AppointmentAIWorkflow)
        .options(
            selectinload(AppointmentAIWorkflow.events),
            selectinload(AppointmentAIWorkflow.confirmations),
            selectinload(AppointmentAIWorkflow.approval_requests),
            joinedload(AppointmentAIWorkflow.patient),
        )
    )

    filters = []
    if status:
        filters.append(AppointmentAIWorkflow.status == status)
    if intent:
        filters.append(AppointmentAIWorkflow.intent == intent)
    if conversation_id:
        filters.append(AppointmentAIWorkflow.conversation_id == conversation_id)
    if patient_id:
        filters.append(AppointmentAIWorkflow.patient_id == patient_id)

    if filters:
        query = query.where(and_(*filters))

    # Total count
    count_stmt = select(func.count(AppointmentAIWorkflow.id))
    if filters:
        count_stmt = count_stmt.where(and_(*filters))
    total = (await db.scalar(count_stmt)) or 0

    query = query.order_by(AppointmentAIWorkflow.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(query)).scalars().all()

    return AppointmentWorkflowListResponse(
        items=[_serialize_workflow(w) for w in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{workflow_id}",
    response_model=AppointmentWorkflowResponse,
    dependencies=[Depends(require_permission("appointments", "read"))],
)
async def get_workflow_details(
    workflow_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve full details, events, and approval history for a specific workflow."""
    workflow = await AppointmentWorkflowService.get_workflow_by_id(db, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Appointment workflow not found.")
    return _serialize_workflow(workflow)


@router.get(
    "/{workflow_id}/history",
    response_model=List[WorkflowEventResponse],
    dependencies=[Depends(require_permission("appointments", "read"))],
)
async def get_workflow_history(
    workflow_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve audit timeline for an appointment workflow."""
    workflow = await AppointmentWorkflowService.get_workflow_by_id(db, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Appointment workflow not found.")
    return [WorkflowEventResponse.model_validate(e) for e in (workflow.events or [])]


@router.post(
    "/{workflow_id}/approve",
    dependencies=[Depends(require_permission("appointments", "update"))],
)
async def approve_workflow(
    workflow_id: uuid.UUID,
    payload: ApprovalActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Approve a pending workflow proposal and commit appointment mutation."""
    try:
        result = await AppointmentWorkflowService.approve_proposal(
            db=db,
            workflow_id=workflow_id,
            staff_user=current_user,
            notes=payload.notes,
        )
        return {"success": True, "result": result}
    except WorkflowError as e:
        raise HTTPException(status_code=400, detail={"code": e.code, "message": e.message, "details": e.details})


@router.post(
    "/{workflow_id}/reject",
    dependencies=[Depends(require_permission("appointments", "update"))],
)
async def reject_workflow(
    workflow_id: uuid.UUID,
    payload: ApprovalActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reject a proposed appointment operation."""
    try:
        result = await AppointmentWorkflowService.reject_proposal(
            db=db,
            workflow_id=workflow_id,
            staff_user=current_user,
            reason=payload.reason or "Rejected by clinic staff.",
            notes=payload.notes,
        )
        return {"success": True, "result": result}
    except WorkflowError as e:
        raise HTTPException(status_code=400, detail={"code": e.code, "message": e.message, "details": e.details})


@router.post(
    "/{workflow_id}/request-clarification",
    dependencies=[Depends(require_permission("appointments", "update"))],
)
async def request_clarification(
    workflow_id: uuid.UUID,
    payload: ApprovalActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Request clarification on proposed workflow from patient."""
    notes = payload.notes or payload.reason or "Staff requested additional information."
    try:
        result = await AppointmentWorkflowService.request_clarification(
            db=db,
            workflow_id=workflow_id,
            staff_user=current_user,
            notes=notes,
        )
        return {"success": True, "result": result}
    except WorkflowError as e:
        raise HTTPException(status_code=400, detail={"code": e.code, "message": e.message, "details": e.details})
