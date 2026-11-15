"""Authenticated REST API Endpoints for Scheduled Automations, Rules, Jobs, and Settings.

Single Organization Edition: Physio One Clinic.
Enforces RBAC, CSRF protection, and audit logging across all automation controls.
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc

from app.core.database import get_db
from app.core.config import settings as app_settings
from app.models.user import User, AuditLog
from app.models.followup import (
    AutomationRule,
    AutomationScheduledJob,
    AutomationExecutionLog,
    AutomationSuppressionLog,
    AutomationSettings,
    AutomationMessageTemplate,
)
from app.models.whatsapp import WhatsAppContact, Conversation, WhatsAppMessage
from app.models.patient import Appointment, Patient
from app.schemas.automation import (
    AutomationRuleCreate,
    AutomationRuleUpdate,
    AutomationRuleResponse,
    AutomationRuleListResponse,
    AutomationScheduledJobCreate,
    AutomationScheduledJobResponse,
    AutomationScheduledJobListResponse,
    JobCancelRequest,
    JobRetryRequest,
    AutomationMessageTemplateCreate,
    AutomationMessageTemplateUpdate,
    AutomationMessageTemplateResponse,
    AutomationMessageTemplateListResponse,
    AutomationSettingsResponse,
    AutomationSettingsUpdate,
    AutomationExecutionLogResponse,
    AutomationExecutionLogListResponse,
    AutomationSuppressionLogResponse,
    AutomationSuppressionLogListResponse,
    AutomationTestRequest,
    AutomationTestResponse,
    AutomationWorkerRunResponse,
)
from app.api.deps import get_current_user, require_role
from app.core.worker_auth import require_worker_auth
from app.services.automation_service import AutomationService
from app.services.automation_worker import AutomationWorkerService
from app.services.eligibility_service import EligibilityService
from app.services.template_service import TemplateService
from app.services.business_hours_service import is_in_business_hours, is_in_quiet_hours, calculate_next_eligible_send_time

logger = logging.getLogger("physio_one.api.automations")

router = APIRouter(prefix="/automations", tags=["Scheduled Automations"])


# ---------------------------------------------------------------------------
# Global Settings & Kill Switch
# ---------------------------------------------------------------------------

@router.get("/settings", response_model=AutomationSettingsResponse)
async def get_automation_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve global automation settings and kill-switch status."""
    return await AutomationService.get_or_create_settings(db)


@router.patch("/settings", response_model=AutomationSettingsResponse)
async def update_automation_settings(
    payload: AutomationSettingsUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "admin")),
):
    """Update global automation settings. Owner/Admin only.
    
    Activating outbound sending is audited and strictly controlled.
    """
    settings = await AutomationService.get_or_create_settings(db)
    old_state = settings.outbound_enabled

    update_data = payload.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(settings, field, val)
    settings.updated_by_user_id = current_user.id
    settings.updated_at = datetime.now(timezone.utc)

    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action="automation.settings_update",
        resource_type="automation_settings",
        resource_id=str(settings.id),
        ip_address=request.client.host if request.client else None,
        payload={
            "updates": update_data,
            "outbound_enabled_transition": f"{old_state} -> {settings.outbound_enabled}",
        },
    )
    db.add(audit)
    await db.commit()
    await db.refresh(settings)
    return settings


# ---------------------------------------------------------------------------
# Automation Rules
# ---------------------------------------------------------------------------

@router.get("/rules", response_model=AutomationRuleListResponse)
async def list_automation_rules(
    automation_type: Optional[str] = None,
    is_enabled: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List configured automation rules."""
    await AutomationService.ensure_default_templates_and_rules(db)
    query = select(AutomationRule).order_by(AutomationRule.created_at.desc())
    if automation_type:
        query = query.where(AutomationRule.automation_type == automation_type)
    if is_enabled is not None:
        query = query.where(AutomationRule.is_enabled == is_enabled)

    rules = (await db.execute(query)).scalars().all()
    items = []
    for r in rules:
        resp = AutomationRuleResponse.model_validate(r)
        if r.template:
            resp.template_name = r.template.name
        items.append(resp)
    return AutomationRuleListResponse(items=items, total=len(items))


@router.post("/rules", response_model=AutomationRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_automation_rule(
    payload: AutomationRuleCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "admin")),
):
    """Create a new automation rule. Defaults strictly to Disabled."""
    rule_data = payload.model_dump()
    rule_data["is_enabled"] = False  # MANDATORY DEFAULT: Disabled
    rule_data["created_by_user_id"] = current_user.id
    rule_data["updated_by_user_id"] = current_user.id

    rule = AutomationRule(**rule_data)
    db.add(rule)
    await db.flush()

    audit = AuditLog(
        user_id=current_user.id,
        action="automation.rule_create",
        resource_type="automation_rule",
        resource_id=str(rule.id),
        ip_address=request.client.host if request.client else None,
        payload={"name": rule.name, "automation_type": rule.automation_type},
    )
    db.add(audit)
    await db.commit()
    await db.refresh(rule)
    return AutomationRuleResponse.model_validate(rule)


@router.get("/rules/{id}", response_model=AutomationRuleResponse)
async def get_automation_rule(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get automation rule by ID."""
    rule = await db.get(AutomationRule, id)
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found.")
    resp = AutomationRuleResponse.model_validate(rule)
    if rule.template:
        resp.template_name = rule.template.name
    return resp


@router.patch("/rules/{id}", response_model=AutomationRuleResponse)
async def update_automation_rule(
    id: uuid.UUID,
    payload: AutomationRuleUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "admin")),
):
    """Update automation rule configuration."""
    rule = await db.get(AutomationRule, id)
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found.")

    update_data = payload.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(rule, field, val)
    rule.updated_by_user_id = current_user.id
    rule.updated_at = datetime.now(timezone.utc)

    db.add(
        AuditLog(
            user_id=current_user.id,
            action="automation.rule_update",
            resource_type="automation_rule",
            resource_id=str(rule.id),
            ip_address=request.client.host if request.client else None,
            payload={"updates": update_data},
        )
    )
    await db.commit()
    await db.refresh(rule)
    resp = AutomationRuleResponse.model_validate(rule)
    if rule.template:
        resp.template_name = rule.template.name
    return resp


@router.post("/rules/{id}/enable", response_model=AutomationRuleResponse)
async def enable_automation_rule(
    id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "admin")),
):
    """Explicitly activate an automation rule. Owner/Admin only."""
    rule = await db.get(AutomationRule, id)
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found.")

    rule.is_enabled = True
    rule.updated_by_user_id = current_user.id
    rule.updated_at = datetime.now(timezone.utc)

    db.add(
        AuditLog(
            user_id=current_user.id,
            action="automation.rule_enable",
            resource_type="automation_rule",
            resource_id=str(rule.id),
            ip_address=request.client.host if request.client else None,
            payload={"rule_name": rule.name, "is_enabled": True},
        )
    )
    await db.commit()
    await db.refresh(rule)
    resp = AutomationRuleResponse.model_validate(rule)
    if rule.template:
        resp.template_name = rule.template.name
    return resp


@router.post("/rules/{id}/disable", response_model=AutomationRuleResponse)
async def disable_automation_rule(
    id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "admin")),
):
    """Deactivate an automation rule. Owner/Admin only."""
    rule = await db.get(AutomationRule, id)
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found.")

    rule.is_enabled = False
    rule.updated_by_user_id = current_user.id
    rule.updated_at = datetime.now(timezone.utc)

    db.add(
        AuditLog(
            user_id=current_user.id,
            action="automation.rule_disable",
            resource_type="automation_rule",
            resource_id=str(rule.id),
            ip_address=request.client.host if request.client else None,
            payload={"rule_name": rule.name, "is_enabled": False},
        )
    )
    await db.commit()
    await db.refresh(rule)
    resp = AutomationRuleResponse.model_validate(rule)
    if rule.template:
        resp.template_name = rule.template.name
    return resp


# ---------------------------------------------------------------------------
# Scheduled Jobs
# ---------------------------------------------------------------------------

@router.get("/jobs", response_model=AutomationScheduledJobListResponse)
async def list_scheduled_jobs(
    status: Optional[str] = None,
    automation_type: Optional[str] = None,
    contact_id: Optional[uuid.UUID] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List scheduled automation jobs with filtering and pagination."""
    query = select(AutomationScheduledJob)
    count_query = select(func.count(AutomationScheduledJob.id))

    filters = []
    if status:
        filters.append(AutomationScheduledJob.status == status)
    if automation_type:
        filters.append(AutomationScheduledJob.automation_type == automation_type)
    if contact_id:
        filters.append(AutomationScheduledJob.contact_id == contact_id)

    if filters:
        query = query.where(and_(*filters))
        count_query = count_query.where(and_(*filters))

    total = (await db.scalar(count_query)) or 0
    query = query.order_by(AutomationScheduledJob.scheduled_for.desc()).offset(offset).limit(limit)
    jobs = (await db.execute(query)).scalars().all()

    items = []
    for j in jobs:
        resp = AutomationScheduledJobResponse.model_validate(j)
        if j.rule:
            resp.rule_name = j.rule.name
        if j.contact:
            resp.contact_phone = j.contact.wa_id
            resp.contact_name = j.contact.profile_name
        if j.template:
            resp.template_name = j.template.name
        items.append(resp)

    return AutomationScheduledJobListResponse(items=items, total=total)


@router.post("/jobs", response_model=AutomationScheduledJobResponse, status_code=status.HTTP_201_CREATED)
async def create_staff_scheduled_job(
    payload: AutomationScheduledJobCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "admin", "operator")),
):
    """Schedule an authorized individual staff-controlled follow-up."""
    try:
        job = await AutomationService.schedule_staff_followup(
            db=db,
            contact_id=payload.contact_id,
            scheduled_for=payload.scheduled_for,
            reason=payload.reason,
            message_text=payload.message_text,
            template_id=payload.template_id,
            conversation_id=payload.conversation_id,
            appointment_id=payload.appointment_id,
            assigned_staff_id=payload.assigned_staff_id,
            current_user=current_user,
            provider=payload.provider,
        )
        resp = AutomationScheduledJobResponse.model_validate(job)
        if job.contact:
            resp.contact_phone = job.contact.wa_id
            resp.contact_name = job.contact.profile_name
        return resp
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err))


@router.get("/jobs/{id}", response_model=AutomationScheduledJobResponse)
async def get_scheduled_job(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get scheduled job details by ID."""
    job = await db.get(AutomationScheduledJob, id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    resp = AutomationScheduledJobResponse.model_validate(job)
    if job.rule:
        resp.rule_name = job.rule.name
    if job.contact:
        resp.contact_phone = job.contact.wa_id
        resp.contact_name = job.contact.profile_name
    if job.template:
        resp.template_name = job.template.name
    return resp


@router.post("/jobs/{id}/cancel", response_model=AutomationScheduledJobResponse)
async def cancel_scheduled_job(
    id: uuid.UUID,
    payload: JobCancelRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "admin", "operator")),
):
    """Cancel a scheduled automation job."""
    try:
        job = await AutomationService.cancel_job(db, id, reason=payload.reason, current_user=current_user)
        return AutomationScheduledJobResponse.model_validate(job)
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err))


@router.post("/jobs/{id}/retry", response_model=AutomationScheduledJobResponse)
async def retry_scheduled_job(
    id: uuid.UUID,
    payload: JobRetryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "admin")),
):
    """Reset a failed or suppressed job back to scheduled state."""
    try:
        job = await AutomationService.retry_job(db, id, reset_attempts=payload.reset_attempts, current_user=current_user)
        return AutomationScheduledJobResponse.model_validate(job)
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err))


# ---------------------------------------------------------------------------
# Message Templates
# ---------------------------------------------------------------------------

@router.get("/templates", response_model=AutomationMessageTemplateListResponse)
async def list_message_templates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List message templates."""
    await AutomationService.ensure_default_templates_and_rules(db)
    query = select(AutomationMessageTemplate).order_by(AutomationMessageTemplate.created_at.desc())
    templates = (await db.execute(query)).scalars().all()
    items = [AutomationMessageTemplateResponse.model_validate(t) for t in templates]
    return AutomationMessageTemplateListResponse(items=items, total=len(items))


@router.post("/templates", response_model=AutomationMessageTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_message_template(
    payload: AutomationMessageTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "admin")),
):
    """Create a new message template. Owner/Admin only."""
    tmpl_data = payload.model_dump()
    tmpl_data["variables"] = TemplateService.extract_variables(payload.body)

    template = AutomationMessageTemplate(**tmpl_data)
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return AutomationMessageTemplateResponse.model_validate(template)


@router.get("/templates/{id}", response_model=AutomationMessageTemplateResponse)
async def get_message_template(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get template by ID."""
    template = await db.get(AutomationMessageTemplate, id)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found.")
    return AutomationMessageTemplateResponse.model_validate(template)


@router.patch("/templates/{id}", response_model=AutomationMessageTemplateResponse)
async def update_message_template(
    id: uuid.UUID,
    payload: AutomationMessageTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "admin")),
):
    """Update message template. Owner/Admin only."""
    template = await db.get(AutomationMessageTemplate, id)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found.")

    update_data = payload.model_dump(exclude_unset=True)
    if "body" in update_data:
        update_data["variables"] = TemplateService.extract_variables(update_data["body"])

    for field, val in update_data.items():
        setattr(template, field, val)
    template.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(template)
    return AutomationMessageTemplateResponse.model_validate(template)


# ---------------------------------------------------------------------------
# Execution and Suppression Logs
# ---------------------------------------------------------------------------

@router.get("/executions", response_model=AutomationExecutionLogListResponse)
async def list_execution_logs(
    job_id: Optional[uuid.UUID] = None,
    contact_id: Optional[uuid.UUID] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List automation execution history logs."""
    query = select(AutomationExecutionLog)
    count_query = select(func.count(AutomationExecutionLog.id))

    filters = []
    if job_id:
        filters.append(AutomationExecutionLog.job_id == job_id)
    if contact_id:
        filters.append(AutomationExecutionLog.contact_id == contact_id)

    if filters:
        query = query.where(and_(*filters))
        count_query = count_query.where(and_(*filters))

    total = (await db.scalar(count_query)) or 0
    query = query.order_by(AutomationExecutionLog.created_at.desc()).offset(offset).limit(limit)
    logs = (await db.execute(query)).scalars().all()
    items = [AutomationExecutionLogResponse.model_validate(l) for l in logs]
    return AutomationExecutionLogListResponse(items=items, total=total)


@router.get("/suppressions", response_model=AutomationSuppressionLogListResponse)
async def list_suppression_logs(
    contact_id: Optional[uuid.UUID] = None,
    reason: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List structured suppression records."""
    query = select(AutomationSuppressionLog)
    count_query = select(func.count(AutomationSuppressionLog.id))

    filters = []
    if contact_id:
        filters.append(AutomationSuppressionLog.contact_id == contact_id)
    if reason:
        filters.append(AutomationSuppressionLog.reason == reason)

    if filters:
        query = query.where(and_(*filters))
        count_query = count_query.where(and_(*filters))

    total = (await db.scalar(count_query)) or 0
    query = query.order_by(AutomationSuppressionLog.created_at.desc()).offset(offset).limit(limit)
    logs = (await db.execute(query)).scalars().all()
    items = [AutomationSuppressionLogResponse.model_validate(l) for l in logs]
    return AutomationSuppressionLogListResponse(items=items, total=total)


# ---------------------------------------------------------------------------
# Shadow Preview & Testing Console
# ---------------------------------------------------------------------------

@router.post("/test", response_model=AutomationTestResponse)
async def test_automation_rendering(
    payload: AutomationTestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "admin", "operator")),
):
    """Preview template rendering and evaluate eligibility without sending any WhatsApp message."""
    contact = await db.get(WhatsAppContact, payload.contact_id)
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found.")

    settings = await AutomationService.get_or_create_settings(db)
    now_utc = datetime.now(timezone.utc)

    # 1. Resolve template body
    body_text = payload.inline_body
    tmpl_name = "inline"
    tmpl_status = "APPROVED"

    if payload.template_id:
        template = await db.get(AutomationMessageTemplate, payload.template_id)
        if not template:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found.")
        body_text = template.body
        tmpl_name = template.name
        tmpl_status = template.approval_status
    elif payload.rule_id:
        rule = await db.get(AutomationRule, payload.rule_id)
        if rule and rule.template:
            body_text = rule.template.body
            tmpl_name = rule.template.name
            tmpl_status = rule.template.approval_status
        elif rule and rule.fallback_body:
            body_text = rule.fallback_body

    if not body_text:
        body_text = "Hello {{patient_name}}, message preview from Physio One."

    # 2. Variable Substitution Context
    appt: Optional[Appointment] = None
    if payload.appointment_id:
        appt = await db.get(Appointment, payload.appointment_id)

    patient_name = contact.profile_name or "Patient"
    if appt and appt.patient:
        patient_name = appt.patient.full_name

    variables: Dict[str, Any] = {
        "patient_name": patient_name,
        "clinic_name": "Physio One Clinic",
        "appointment_date": appt.start_time.strftime("%A, %d %B %Y") if appt else "Monday, 16 November 2026",
        "appointment_time": appt.start_time.strftime("%I:%M %p") if appt else "10:00 AM",
        "practitioner_name": appt.practitioner_name if appt else "Dr. Physio One",
        "service_type": appt.service_type if appt else "Physiotherapy Consultation",
        **(payload.mock_variables or {}),
    }

    try:
        rendered = TemplateService.render(body_text, variables, tmpl_name)
    except Exception as exc:
        rendered = f"[Rendering Error: {exc}]"

    # 3. Eligibility Checks
    suppressions: List[str] = []
    if not settings.outbound_enabled:
        suppressions.append("Global kill switch is disabled (AUTOMATION_OUTBOUND_ENABLED=false)")
    if contact.opted_out_all:
        suppressions.append("Contact opted out of all messaging")

    # 24-hour service window check
    last_inbound_stmt = select(func.max(WhatsAppMessage.created_at)).where(
        WhatsAppMessage.contact_id == contact.id,
        WhatsAppMessage.direction == "inbound",
    )
    last_inbound_at = await db.scalar(last_inbound_stmt)
    service_window_open = TemplateService.is_service_window_open(last_inbound_at, now_utc)
    requires_approved_template = not service_window_open

    if requires_approved_template and tmpl_status != "APPROVED":
        suppressions.append("Window closed: requires an approved WhatsApp template")

    in_biz = is_in_business_hours(now_utc, settings.business_hours_start, settings.business_hours_end, tz_name=settings.default_timezone)
    in_quiet = is_in_quiet_hours(now_utc, settings.quiet_hours_start, settings.quiet_hours_end, tz_name=settings.default_timezone)

    if in_quiet or not in_biz:
        next_eligible = calculate_next_eligible_send_time(
            now_utc,
            settings.business_hours_start,
            settings.business_hours_end,
            settings.quiet_hours_start,
            settings.quiet_hours_end,
            tz_name=settings.default_timezone,
        )
    else:
        next_eligible = now_utc

    return AutomationTestResponse(
        rendered_message=rendered,
        eligible=(len(suppressions) == 0 and in_biz and not in_quiet),
        suppression_reasons=suppressions,
        service_window_open=service_window_open,
        requires_approved_template=requires_approved_template,
        in_business_hours=in_biz,
        in_quiet_hours=in_quiet,
        next_eligible_send_time=next_eligible,
    )


# ---------------------------------------------------------------------------
# Worker & Scheduler Triggers
# ---------------------------------------------------------------------------

@router.post("/process-due", response_model=AutomationWorkerRunResponse)
async def process_due_jobs(
    limit: int = Query(20, ge=1, le=100),
    worker_auth: Dict[str, Any] = Depends(require_worker_auth),
    db: AsyncSession = Depends(get_db),
):
    """Trigger one worker cycle to lock and execute due scheduled jobs.
    
    Protected via verified Google OIDC token, worker token, or logged-in Owner/Admin session.
    """
    stats = await AutomationWorkerService.run_worker_cycle(db, limit=limit)
    return AutomationWorkerRunResponse(**stats)


@router.post("/scan-inactivity", response_model=Dict[str, int])
async def scan_inactivity_now(
    worker_auth: Dict[str, Any] = Depends(require_worker_auth),
    db: AsyncSession = Depends(get_db),
):
    """Trigger 15-minute conversation inactivity evaluation scan.
    
    Protected via verified Google OIDC token, worker token, or logged-in Owner/Admin session.
    """
    created_jobs = await AutomationService.scan_and_schedule_inactivity_followups(db)
    await db.commit()
    return {"newly_scheduled_count": len(created_jobs)}
