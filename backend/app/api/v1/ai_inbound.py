"""Inbound AI Orchestration Settings & Queue Control API Endpoints.

Single Organization Edition: Physio One Clinic.
RBAC:
- View settings & drafts: require_role(Owner, Admin, Operator, Viewer)
- Update settings (AI mode, activation, debounce): require_role(Owner, Admin)
- Trigger processing: require_role(Owner, Admin, Operator)
"""
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.api.deps import require_role, get_current_user
from app.core.rbac import ROLE_OWNER, ROLE_ADMIN, ROLE_OPERATOR, ROLE_VIEWER
from app.models.user import User
from app.models.inbound import AIInboundSettings, AIResponseDraft, InboundProcessingJob
from app.models.ai import AIAgent
from app.schemas.inbound import (
    AIInboundSettingsResponse,
    AIInboundSettingsUpdateRequest,
    AIResponseDraftResponse,
)
from app.services.inbound_queue import InboundQueueService
from app.services.inbound_orchestrator import InboundOrchestrator
from app.services.auth_service import log_audit_event

router = APIRouter(prefix="/ai-inbound", tags=["Inbound AI Orchestration"])


@router.get("/settings", response_model=AIInboundSettingsResponse)
async def get_inbound_settings(
    current_user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN, ROLE_OPERATOR, ROLE_VIEWER)),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve current Inbound AI Orchestration settings (default mode: disabled)."""
    settings = await InboundQueueService.get_or_create_settings(db)
    
    agent_name = None
    if settings.active_agent_id:
        stmt_a = select(AIAgent.name).where(AIAgent.id == settings.active_agent_id)
        agent_name = (await db.execute(stmt_a)).scalar_one_or_none()

    return AIInboundSettingsResponse(
        id=settings.id,
        account_id=settings.account_id,
        ai_mode=settings.ai_mode,
        active_agent_id=settings.active_agent_id,
        active_agent_name=agent_name,
        debounce_seconds=settings.debounce_seconds,
        max_ai_steps=settings.max_ai_steps,
        processing_timeout_seconds=settings.processing_timeout_seconds,
        opt_out_keywords=settings.opt_out_keywords or [],
        emergency_keywords=settings.emergency_keywords or [],
        is_active=settings.is_active,
        updated_at=settings.updated_at,
    )


@router.patch("/settings", response_model=AIInboundSettingsResponse)
async def update_inbound_settings(
    payload: AIInboundSettingsUpdateRequest,
    current_user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Update Inbound AI Orchestration settings (Owner and Admin only).
    
    Permitted modes: 'disabled', 'shadow', 'live'.
    """
    settings = await InboundQueueService.get_or_create_settings(db)

    old_mode = settings.ai_mode

    if payload.ai_mode is not None:
        clean_mode = payload.ai_mode.lower().strip()
        if clean_mode not in ("disabled", "shadow", "live"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid ai_mode. Must be 'disabled', 'shadow', or 'live'.",
            )
        settings.ai_mode = clean_mode

    if payload.active_agent_id is not None:
        stmt_chk = select(AIAgent).where(AIAgent.id == payload.active_agent_id)
        agent = (await db.execute(stmt_chk)).scalar_one_or_none()
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent with ID '{payload.active_agent_id}' not found.",
            )
        settings.active_agent_id = payload.active_agent_id

    if payload.debounce_seconds is not None:
        settings.debounce_seconds = payload.debounce_seconds
    if payload.max_ai_steps is not None:
        settings.max_ai_steps = payload.max_ai_steps
    if payload.processing_timeout_seconds is not None:
        settings.processing_timeout_seconds = payload.processing_timeout_seconds
    if payload.opt_out_keywords is not None:
        settings.opt_out_keywords = payload.opt_out_keywords
    if payload.emergency_keywords is not None:
        settings.emergency_keywords = payload.emergency_keywords
    if payload.is_active is not None:
        settings.is_active = payload.is_active

    await db.commit()
    await db.refresh(settings)

    # Log audit event for AI mode or configuration modification
    await log_audit_event(
        db=db,
        action="AI_INBOUND_SETTINGS_UPDATED",
        resource_type="ai_inbound_settings",
        resource_id=str(settings.id),
        user_id=current_user.id,
        payload={
            "old_mode": old_mode,
            "new_mode": settings.ai_mode,
            "debounce_seconds": settings.debounce_seconds,
        },
    )
    await db.commit()

    agent_name = None
    if settings.active_agent_id:
        stmt_a = select(AIAgent.name).where(AIAgent.id == settings.active_agent_id)
        agent_name = (await db.execute(stmt_a)).scalar_one_or_none()

    return AIInboundSettingsResponse(
        id=settings.id,
        account_id=settings.account_id,
        ai_mode=settings.ai_mode,
        active_agent_id=settings.active_agent_id,
        active_agent_name=agent_name,
        debounce_seconds=settings.debounce_seconds,
        max_ai_steps=settings.max_ai_steps,
        processing_timeout_seconds=settings.processing_timeout_seconds,
        opt_out_keywords=settings.opt_out_keywords or [],
        emergency_keywords=settings.emergency_keywords or [],
        is_active=settings.is_active,
        updated_at=settings.updated_at,
    )


@router.post("/process-due")
async def trigger_process_due_jobs(
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN, ROLE_OPERATOR)),
    db: AsyncSession = Depends(get_db),
):
    """Trigger execution of due debounced inbound jobs."""
    jobs = await InboundQueueService.fetch_and_lock_due_jobs(db, limit=limit)
    results = []
    for job in jobs:
        outcome = await InboundOrchestrator.process_job(db, job)
        results.append({"job_id": str(job.id), "outcome": outcome})
    return {"processed_count": len(results), "jobs": results}


@router.get("/drafts", response_model=List[AIResponseDraftResponse])
async def list_drafts(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    dispatched: Optional[bool] = Query(None),
    current_user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN, ROLE_OPERATOR, ROLE_VIEWER)),
    db: AsyncSession = Depends(get_db),
):
    """List AI generated drafts for audit and review."""
    stmt = select(AIResponseDraft).order_by(AIResponseDraft.created_at.desc())
    if dispatched is not None:
        stmt = stmt.where(AIResponseDraft.dispatched == dispatched)
    stmt = stmt.offset(offset).limit(limit)
    drafts = (await db.execute(stmt)).scalars().all()
    return [AIResponseDraftResponse.from_orm(d) for d in drafts]
