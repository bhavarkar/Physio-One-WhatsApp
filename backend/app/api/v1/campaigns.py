"""Campaign Management, Instagram Re-engagement, and Legacy Cutover REST API Router.

Single Organization Edition: Physio One Clinic.
Provides RBAC-protected endpoints for:
1. Media library assets (Instagram reels, videos, clinical content).
2. Campaign definitions, versioning, and Owner/Admin approvals.
3. Audience evaluation, safety suppression previews, and CSV contact imports.
4. Execution controls (schedule, pause, resume, cancel).
5. Delivery and conversion analytics.
6. Legacy YCloud/n8n cutover state machine.
"""
import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, status, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.config import settings as app_settings
from app.models.user import User
from app.models.campaign import (
    Campaign,
    CampaignMedia,
    CampaignVersion,
    CampaignRecipient,
    CampaignApproval,
    LegacyWorkflowMigration,
)
from app.schemas.campaign import (
    CampaignCreate,
    CampaignUpdate,
    CampaignResponse,
    CampaignListResponse,
    CampaignMediaCreate,
    CampaignMediaUpdate,
    CampaignMediaResponse,
    CampaignMediaListResponse,
    CampaignApprovalRequest,
    CampaignApprovalResponse,
    CampaignPreviewResponse,
    CampaignImportResponse,
    CampaignAnalyticsResponse,
    CampaignRecipientResponse,
    CampaignRecipientListResponse,
    LegacyMigrationStatusResponse,
    LegacyMigrationDryRunResponse,
    LegacyMigrationCutoverRequest,
)
from app.services.campaign_service import CampaignService
from app.api.deps import get_current_user, require_role

router = APIRouter(tags=["campaigns"])


# ---------------------------------------------------------------------------
# Media Library Endpoints
# ---------------------------------------------------------------------------

@router.get("/campaign-media", response_model=CampaignMediaListResponse)
async def list_campaign_media(
    media_type: Optional[str] = Query(None, description="Filter by media_type (e.g. instagram_reel)"),
    is_archived: bool = Query(False),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List active or archived media items."""
    items, total = await CampaignService.list_media(
        db, media_type=media_type, is_archived=is_archived, limit=limit, offset=offset
    )
    return CampaignMediaListResponse(
        items=[CampaignMediaResponse.model_validate(m) for m in items],
        total=total,
    )


@router.post("/campaign-media", response_model=CampaignMediaResponse, status_code=status.HTTP_201_CREATED)
async def create_campaign_media(
    payload: CampaignMediaCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "admin", "operator")),
):
    """Create/register media item (Instagram reel link or uploaded asset)."""
    try:
        media = await CampaignService.create_media(
            db,
            title=payload.title,
            caption=payload.caption,
            media_type=payload.media_type,
            external_url=payload.external_url,
            storage_path=payload.storage_path,
            thumbnail_url=payload.thumbnail_url,
            file_size_bytes=payload.file_size_bytes,
            mime_type=payload.mime_type,
            tags=payload.tags,
            user_id=current_user.id,
        )
        return CampaignMediaResponse.model_validate(media)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.patch("/campaign-media/{id}/archive", response_model=CampaignMediaResponse)
async def archive_campaign_media(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "admin")),
):
    """Archive a media item."""
    media = await CampaignService.archive_media(db, id)
    if not media:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found.")
    return CampaignMediaResponse.model_validate(media)


# ---------------------------------------------------------------------------
# Campaign Management Endpoints
# ---------------------------------------------------------------------------

@router.get("/campaigns", response_model=CampaignListResponse)
async def list_campaigns(
    status_filter: Optional[str] = Query(None, alias="status"),
    campaign_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List campaigns with pagination and filtering."""
    query = select(Campaign)
    if status_filter:
        query = query.where(Campaign.status == status_filter)
    if campaign_type:
        query = query.where(Campaign.campaign_type == campaign_type)

    count_query = select(func.count(Campaign.id))
    if status_filter:
        count_query = count_query.where(Campaign.status == status_filter)
    if campaign_type:
        count_query = count_query.where(Campaign.campaign_type == campaign_type)

    total = (await db.scalar(count_query)) or 0
    items = (await db.execute(query.order_by(Campaign.created_at.desc()).offset(offset).limit(limit))).scalars().all()

    return CampaignListResponse(
        items=[CampaignResponse.model_validate(c) for c in items],
        total=total,
    )


@router.post("/campaigns", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    payload: CampaignCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "admin", "operator")),
):
    """Create a new campaign. Defaults strictly to draft status."""
    try:
        campaign = await CampaignService.create_campaign(
            db, payload.model_dump(), user_id=current_user.id
        )
        return CampaignResponse.model_validate(campaign)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/campaigns/{id}", response_model=CampaignResponse)
async def get_campaign(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get single campaign details."""
    campaign = await db.get(Campaign, id)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found.")
    return CampaignResponse.model_validate(campaign)


@router.patch("/campaigns/{id}", response_model=CampaignResponse)
async def update_campaign(
    id: uuid.UUID,
    payload: CampaignUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "admin", "operator")),
):
    """Update campaign definition. Increments version and invalidates previous approval."""
    try:
        updated = await CampaignService.update_campaign(
            db, id, payload.model_dump(exclude_unset=True), user_id=current_user.id
        )
        return CampaignResponse.model_validate(updated)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/campaigns/{id}/preview", response_model=CampaignPreviewResponse)
async def preview_campaign_audience(
    id: uuid.UUID,
    persist: bool = Query(True, description="Save evaluated recipients to database"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "admin", "operator")),
):
    """Evaluate campaign audience, run 12 safety checks, and preview sample rendering."""
    try:
        preview = await CampaignService.evaluate_campaign_audience(
            db, id, persist_recipients=persist
        )
        campaign = await db.get(Campaign, id)
        media = await db.get(CampaignMedia, campaign.media_id) if campaign.media_id else None

        return CampaignPreviewResponse(
            campaign_id=campaign.id,
            campaign_title=campaign.title,
            version=campaign.current_version,
            total_evaluated=preview["total_evaluated"],
            eligible_count=preview["eligible_count"],
            suppressed_count=preview["suppressed_count"],
            suppression_breakdown=preview["suppression_breakdown"],
            rendered_preview_sample=preview["sample_rendered"],
            template_name=campaign.template_name,
            media_title=media.title if media else None,
            media_url=media.external_url if media else None,
            sending_window=preview["sending_window"],
            can_schedule=preview["can_schedule"],
            blocking_reasons=preview["blocking_reasons"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post("/campaigns/{id}/approve", response_model=CampaignResponse)
async def approve_campaign(
    id: uuid.UUID,
    payload: CampaignApprovalRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "admin")),
):
    """Owner/Admin explicit approval or rejection of immutable campaign version."""
    try:
        approved = await CampaignService.approve_campaign(
            db, id, decision=payload.decision, user_id=current_user.id, notes=payload.notes
        )
        return CampaignResponse.model_validate(approved)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/campaigns/{id}/schedule", response_model=CampaignResponse)
async def schedule_campaign(
    id: uuid.UUID,
    scheduled_for: Optional[str] = Query(None, description="ISO format send timestamp"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "admin", "operator")),
):
    """Schedule an approved campaign for background execution."""
    target_dt = None
    if scheduled_for:
        try:
            target_dt = datetime.fromisoformat(scheduled_for.replace("Z", "+00:00"))
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ISO timestamp format.")

    try:
        scheduled = await CampaignService.schedule_campaign(
            db, id, scheduled_for=target_dt, user_id=current_user.id
        )
        return CampaignResponse.model_validate(scheduled)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/campaigns/{id}/pause", response_model=CampaignResponse)
async def pause_campaign(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "admin", "operator")),
):
    """Pause an active or scheduled campaign."""
    try:
        paused = await CampaignService.pause_campaign(db, id)
        return CampaignResponse.model_validate(paused)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/campaigns/{id}/resume", response_model=CampaignResponse)
async def resume_campaign(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "admin", "operator")),
):
    """Resume a paused campaign."""
    try:
        resumed = await CampaignService.resume_campaign(db, id)
        return CampaignResponse.model_validate(resumed)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/campaigns/{id}/cancel", response_model=CampaignResponse)
async def cancel_campaign(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "admin", "operator")),
):
    """Cancel a campaign and terminate pending recipient jobs."""
    try:
        cancelled = await CampaignService.cancel_campaign(db, id)
        return CampaignResponse.model_validate(cancelled)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/campaigns/{id}/recipients", response_model=CampaignRecipientListResponse)
async def list_campaign_recipients(
    id: uuid.UUID,
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List recipients for a specific campaign with suppression reasons."""
    query = select(CampaignRecipient).where(CampaignRecipient.campaign_id == id)
    if status_filter:
        query = query.where(CampaignRecipient.status == status_filter)

    count_query = select(func.count(CampaignRecipient.id)).where(CampaignRecipient.campaign_id == id)
    if status_filter:
        count_query = count_query.where(CampaignRecipient.status == status_filter)

    total = (await db.scalar(count_query)) or 0
    items = (await db.execute(query.order_by(CampaignRecipient.created_at.desc()).offset(offset).limit(limit))).scalars().all()

    return CampaignRecipientListResponse(
        items=[CampaignRecipientResponse.model_validate(r) for r in items],
        total=total,
    )


@router.get("/campaigns/{id}/analytics", response_model=CampaignAnalyticsResponse)
async def get_campaign_analytics(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve delivery performance and conversion metrics with 72h attribution."""
    try:
        stats = await CampaignService.get_campaign_analytics(db, id)
        return CampaignAnalyticsResponse(**stats)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


# ---------------------------------------------------------------------------
# CSV Contact Import
# ---------------------------------------------------------------------------

@router.post("/campaigns/import", response_model=CampaignImportResponse)
async def import_campaign_contacts_csv(
    file: UploadFile = File(...),
    campaign_id: Optional[uuid.UUID] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "admin", "operator")),
):
    """Import and normalize contacts from CSV with E.164 sanitization."""
    if not file.filename.endswith((".csv", ".txt")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be a CSV format.")

    try:
        content_bytes = await file.read()
        csv_text = content_bytes.decode("utf-8", errors="replace")
        report = await CampaignService.import_csv_contacts(
            db, csv_content=csv_text, campaign_id=campaign_id, user_id=current_user.id
        )
        return CampaignImportResponse(**report)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to parse CSV: {exc}")


# ---------------------------------------------------------------------------
# Legacy Workflow Migration & Cutover Endpoints
# ---------------------------------------------------------------------------

@router.get("/legacy-migration/status", response_model=LegacyMigrationStatusResponse)
async def get_legacy_migration_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Check YCloud/n8n legacy re-engagement migration state machine."""
    migration = await CampaignService.get_or_create_legacy_migration(db)
    return LegacyMigrationStatusResponse.model_validate(migration)


@router.post("/legacy-migration/dry-run", response_model=LegacyMigrationDryRunResponse)
async def run_legacy_dry_run(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "admin")),
):
    """Execute shadow dry-run comparison between legacy n8n and new engine."""
    results = await CampaignService.run_legacy_dry_run_comparison(db)
    return LegacyMigrationDryRunResponse(**results)


@router.post("/legacy-migration/cutover", response_model=LegacyMigrationStatusResponse)
async def set_legacy_cutover_state(
    payload: LegacyMigrationCutoverRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "admin")),
):
    """Owner/Admin explicit transition of cutover state machine."""
    try:
        migration = await CampaignService.update_legacy_cutover_state(
            db, target_state=payload.target_state, user_id=current_user.id, notes=payload.notes
        )
        return LegacyMigrationStatusResponse.model_validate(migration)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# ---------------------------------------------------------------------------
# Worker & Scheduler Triggers
# ---------------------------------------------------------------------------

@router.post("/campaigns/worker/run")
async def trigger_reengagement_cycle(
    limit: int = Query(25, ge=1, le=100),
    x_worker_token: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """Execute one 30-minute re-engagement campaign dispatch cycle."""
    authorized = False
    if current_user and current_user.role.name in ["owner", "admin", "operator"]:
        authorized = True
    elif x_worker_token and x_worker_token == app_settings.AUTOMATION_WORKER_SECRET_TOKEN:
        authorized = True

    if not authorized:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized service caller. Valid worker token or admin session required.",
        )

    result = await CampaignService.run_reengagement_cycle(db, limit=limit)
    return result
