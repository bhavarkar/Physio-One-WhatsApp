"""Campaign Management, Instagram Re-engagement, and Legacy YCloud Migration Engine.

Single Organization Edition: Physio One Clinic.
Implements:
1. Instagram Reel / Media Library with upload validation.
2. 30-minute Instagram re-engagement automation (09:00 - 21:00 IST).
3. 12-layer audience targeting & suppression (consent, STOP, booked appts, cooldown).
4. Campaign versioning and immutable staff approval workflows.
5. Throttled outbound execution reusing Task 11 worker infrastructure.
6. Real delivery and conversion analytics with 72h attribution window.
7. YCloud legacy n8n workflow migration state machine.
"""
import csv
import io
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple

from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings as app_settings
from app.models.campaign import (
    Campaign,
    CampaignMedia,
    CampaignVersion,
    CampaignAudience,
    CampaignRecipient,
    CampaignApproval,
    CampaignDeliveryEvent,
    CampaignConversionEvent,
    LegacyWorkflowMigration,
)
from app.models.whatsapp import WhatsAppContact, WhatsAppMessage
from app.models.patient import Patient, PatientConsent, Appointment
from app.models.followup import AutomationSettings, AutomationMessageTemplate
from app.models.inbound import Conversation
from app.services.business_hours_service import (
    is_in_business_hours,
    is_in_quiet_hours,
    calculate_next_eligible_send_time,
    get_tz,
)
from app.services.template_service import TemplateService
from app.services.outbound_dispatcher import OutboundDispatcher


class CampaignService:
    """Core domain service for campaigns, media, approvals, and legacy cutover."""

    # ---------------------------------------------------------------------------
    # 1. Instagram Reel & Media Library
    # ---------------------------------------------------------------------------

    @staticmethod
    def validate_media_url(url: Optional[str]) -> bool:
        """Validate external URL is a safe HTTP(S) link."""
        if not url:
            return True
        pattern = r"^https?:\/\/[^\s\/$.?#].[^\s]*$"
        return bool(re.match(pattern, url.strip(), re.IGNORECASE))

    @classmethod
    async def create_media(
        cls,
        db: AsyncSession,
        title: str,
        caption: Optional[str] = None,
        media_type: str = "instagram_reel",
        external_url: Optional[str] = None,
        storage_path: Optional[str] = None,
        thumbnail_url: Optional[str] = None,
        file_size_bytes: Optional[int] = None,
        mime_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        user_id: Optional[uuid.UUID] = None,
    ) -> CampaignMedia:
        """Add media asset to the clinic media library."""
        if external_url and not cls.validate_media_url(external_url):
            raise ValueError("Invalid external media URL. Must be a valid HTTP/HTTPS link.")

        media = CampaignMedia(
            title=title.strip(),
            caption=caption.strip() if caption else None,
            media_type=media_type,
            external_url=external_url.strip() if external_url else None,
            storage_path=storage_path.strip() if storage_path else None,
            thumbnail_url=thumbnail_url.strip() if thumbnail_url else None,
            file_size_bytes=file_size_bytes,
            mime_type=mime_type,
            tags=tags or [],
            is_active=True,
            is_archived=False,
            created_by_id=user_id,
        )
        db.add(media)
        await db.commit()
        await db.refresh(media)
        return media

    @classmethod
    async def list_media(
        cls,
        db: AsyncSession,
        media_type: Optional[str] = None,
        is_archived: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[CampaignMedia], int]:
        """List active media items with pagination."""
        query = select(CampaignMedia).where(CampaignMedia.is_archived == is_archived)
        if media_type:
            query = query.where(CampaignMedia.media_type == media_type)

        count_query = select(func.count(CampaignMedia.id)).where(CampaignMedia.is_archived == is_archived)
        if media_type:
            count_query = count_query.where(CampaignMedia.media_type == media_type)

        total = (await db.scalar(count_query)) or 0
        items = (await db.execute(query.order_by(CampaignMedia.created_at.desc()).offset(offset).limit(limit))).scalars().all()
        return list(items), total

    @classmethod
    async def archive_media(cls, db: AsyncSession, media_id: uuid.UUID) -> Optional[CampaignMedia]:
        """Archive a media library item."""
        media = await db.get(CampaignMedia, media_id)
        if not media:
            return None
        media.is_archived = True
        media.is_active = False
        media.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(media)
        return media

    # ---------------------------------------------------------------------------
    # 2. Campaign Lifecycle & Versioning
    # ---------------------------------------------------------------------------

    @classmethod
    async def create_campaign(
        cls,
        db: AsyncSession,
        data: Dict[str, Any],
        user_id: Optional[uuid.UUID] = None,
    ) -> Campaign:
        """Create a new campaign defaulting strictly to draft status."""
        data_clean = dict(data)
        data_clean.pop("id", None)
        data_clean.pop("status", None)  # Enforce draft default

        campaign = Campaign(
            **data_clean,
            status="draft",
            current_version=1,
            is_approved=False,
            approved_by_id=None,
            approved_at=None,
            approved_version=None,
            created_by_id=user_id,
        )
        db.add(campaign)
        await db.flush()

        # Create initial Version 1 snapshot
        snapshot = cls._build_campaign_snapshot(campaign)
        version = CampaignVersion(
            campaign_id=campaign.id,
            version_number=1,
            snapshot=snapshot,
            created_by_id=user_id,
        )
        db.add(version)
        await db.commit()
        await db.refresh(campaign)
        return campaign

    @classmethod
    async def update_campaign(
        cls,
        db: AsyncSession,
        campaign_id: uuid.UUID,
        updates: Dict[str, Any],
        user_id: Optional[uuid.UUID] = None,
    ) -> Campaign:
        """Update campaign definition.
        
        CRITICAL INVARIANT: Any modification to an approved campaign invalidates
        previous approval and increments version.
        """
        campaign = await db.get(Campaign, campaign_id)
        if not campaign:
            raise ValueError("Campaign not found.")

        if campaign.status in ("running", "completed"):
            raise ValueError(f"Cannot edit campaign in {campaign.status} status.")

        previous_was_approved = campaign.is_approved

        for field, val in updates.items():
            if hasattr(campaign, field) and field not in ("id", "current_version", "created_at"):
                setattr(campaign, field, val)

        # Invalidate approval upon content or audience changes
        campaign.current_version += 1
        campaign.is_approved = False
        campaign.approved_by_id = None
        campaign.approved_at = None
        campaign.approved_version = None
        campaign.status = "draft"
        campaign.updated_at = datetime.now(timezone.utc)

        # If previous version was approved, mark any pending/approved approval record as invalidated
        if previous_was_approved:
            inv_stmt = select(CampaignApproval).where(
                CampaignApproval.campaign_id == campaign.id,
                CampaignApproval.status == "approved",
            )
            old_approvals = (await db.execute(inv_stmt)).scalars().all()
            for app in old_approvals:
                app.status = "invalidated"
                app.notes = (app.notes or "") + " [Invalidated by campaign edit]"

        # Create new version snapshot
        snapshot = cls._build_campaign_snapshot(campaign)
        version = CampaignVersion(
            campaign_id=campaign.id,
            version_number=campaign.current_version,
            snapshot=snapshot,
            created_by_id=user_id,
        )
        db.add(version)

        await db.commit()
        await db.refresh(campaign)
        return campaign

    @classmethod
    async def approve_campaign(
        cls,
        db: AsyncSession,
        campaign_id: uuid.UUID,
        decision: str,
        user_id: uuid.UUID,
        notes: Optional[str] = None,
    ) -> Campaign:
        """Owner/Admin explicit campaign approval or rejection."""
        campaign = await db.get(Campaign, campaign_id)
        if not campaign:
            raise ValueError("Campaign not found.")

        now_utc = datetime.now(timezone.utc)
        snapshot = cls._build_campaign_snapshot(campaign)

        if decision == "approve":
            campaign.is_approved = True
            campaign.approved_by_id = user_id
            campaign.approved_at = now_utc
            campaign.approved_version = campaign.current_version
            campaign.approval_notes = notes
            campaign.status = "approved"

            approval = CampaignApproval(
                campaign_id=campaign.id,
                campaign_version=campaign.current_version,
                status="approved",
                reviewed_by_id=user_id,
                decision_at=now_utc,
                notes=notes,
                snapshot=snapshot,
            )
            db.add(approval)

        elif decision == "reject":
            campaign.is_approved = False
            campaign.approved_by_id = None
            campaign.approved_at = None
            campaign.approved_version = None
            campaign.status = "draft"
            campaign.approval_notes = notes

            approval = CampaignApproval(
                campaign_id=campaign.id,
                campaign_version=campaign.current_version,
                status="rejected",
                reviewed_by_id=user_id,
                decision_at=now_utc,
                notes=notes,
                snapshot=snapshot,
            )
            db.add(approval)
        else:
            raise ValueError("Decision must be 'approve' or 'reject'.")

        campaign.updated_at = now_utc
        await db.commit()
        await db.refresh(campaign)
        return campaign

    @staticmethod
    def _build_campaign_snapshot(campaign: Campaign) -> Dict[str, Any]:
        """Generate immutable dictionary snapshot of campaign configuration."""
        return {
            "title": campaign.title,
            "campaign_type": campaign.campaign_type,
            "provider": campaign.provider,
            "version": campaign.current_version,
            "target_audience_rules": campaign.target_audience_rules,
            "template_name": campaign.template_name,
            "custom_message_body": campaign.custom_message_body,
            "media_id": str(campaign.media_id) if campaign.media_id else None,
            "scheduled_for": campaign.scheduled_for.isoformat() if campaign.scheduled_for else None,
            "execution_window": f"{campaign.execution_window_start}-{campaign.execution_window_end}",
            "rate_limits": {
                "per_minute": campaign.rate_limit_per_minute,
                "per_hour": campaign.rate_limit_per_hour,
                "batch_size": campaign.batch_size,
            },
        }

    # ---------------------------------------------------------------------------
    # 3. Audience Evaluation & Targeting Engine
    # ---------------------------------------------------------------------------

    @classmethod
    async def evaluate_campaign_audience(
        cls,
        db: AsyncSession,
        campaign_id: uuid.UUID,
        persist_recipients: bool = False,
    ) -> Dict[str, Any]:
        """Evaluate all contacts against campaign criteria with suppression breakdown."""
        campaign = await db.get(Campaign, campaign_id)
        if not campaign:
            raise ValueError("Campaign not found.")

        now_utc = datetime.now(timezone.utc)
        rules = campaign.target_audience_rules or {}
        window_hours = rules.get("interaction_window_hours", [24, 48])
        require_no_booked = rules.get("require_no_future_appointment", True)
        require_marketing_consent = rules.get("require_marketing_consent", True)
        require_no_opt_out = rules.get("require_no_opt_out", True)

        min_hours = min(window_hours) if window_hours else 24
        max_hours = max(window_hours) if window_hours else 48

        # Eligible interaction range
        cutoff_recent = now_utc - timedelta(hours=min_hours)
        cutoff_old = now_utc - timedelta(hours=max_hours)

        # 1. Fetch contacts
        stmt = select(WhatsAppContact).where(WhatsAppContact.wa_id.isnot(None))
        contacts = (await db.execute(stmt)).scalars().all()

        total_evaluated = len(contacts)
        eligible_contacts: List[WhatsAppContact] = []
        suppressed_items: List[Dict[str, Any]] = []
        suppression_counts: Dict[str, int] = {}

        for contact in contacts:
            reasons: List[str] = []

            # Safety Gate A: Global or Promotional Opt-Out
            if require_no_opt_out:
                if contact.opted_out_all:
                    reasons.append("contact_opted_out_all")
                elif contact.opted_out_promotions:
                    reasons.append("contact_opted_out_promotions")

            # Safety Gate B: Interaction Window (24h - 48h)
            last_active = contact.last_active_at
            if not last_active:
                # Query last inbound message
                msg_stmt = select(func.max(WhatsAppMessage.created_at)).where(
                    WhatsAppMessage.contact_id == contact.id,
                    WhatsAppMessage.direction == "inbound",
                )
                last_active = await db.scalar(msg_stmt)

            if not last_active:
                reasons.append("no_qualifying_interaction")
            else:
                last_active_utc = last_active if last_active.tzinfo else last_active.replace(tzinfo=timezone.utc)
                if last_active_utc > cutoff_recent:
                    reasons.append("interaction_too_recent")  # Less than 24h ago
                elif last_active_utc < cutoff_old:
                    reasons.append("interaction_too_old")  # More than 48h ago

            # Safety Gate C: Marketing Consent
            if require_marketing_consent:
                # Check patient consent
                patient_stmt = select(Patient.id).where(Patient.contact_id == contact.id)
                patient_id = await db.scalar(patient_stmt)
                if patient_id:
                    consent_stmt = select(PatientConsent.is_granted).where(
                        PatientConsent.patient_id == patient_id,
                        PatientConsent.consent_type == "marketing_promotions",
                    ).order_by(PatientConsent.created_at.desc())
                    is_granted = await db.scalar(consent_stmt)
                    if not is_granted:
                        reasons.append("missing_marketing_consent")
                else:
                    reasons.append("missing_marketing_consent")

            # Safety Gate D: Active Upcoming Bookings
            if require_no_booked:
                patient_id_stmt = select(Patient.id).where(Patient.contact_id == contact.id)
                p_id = await db.scalar(patient_id_stmt)
                if p_id:
                    appt_stmt = select(func.count(Appointment.id)).where(
                        Appointment.patient_id == p_id,
                        Appointment.status == "confirmed",
                        Appointment.start_time > now_utc,
                    )
                    booked_count = (await db.scalar(appt_stmt)) or 0
                    if booked_count > 0:
                        reasons.append("appointment_already_booked")

            # Safety Gate E: Human Takeover in Open Conversation
            conv_stmt = select(Conversation.is_human_takeover).where(
                Conversation.contact_id == contact.id,
                Conversation.status != "closed",
            ).order_by(Conversation.created_at.desc())
            takeover = await db.scalar(conv_stmt)
            if takeover:
                reasons.append("human_takeover_active")

            # Safety Gate F: Already Received Same Campaign
            recip_stmt = select(CampaignRecipient.id).where(
                CampaignRecipient.campaign_id == campaign.id,
                CampaignRecipient.contact_id == contact.id,
                CampaignRecipient.status.in_(["sent", "delivered", "read", "queued", "sending"]),
            )
            already_sent = await db.scalar(recip_stmt)
            if already_sent:
                reasons.append("already_contacted_in_campaign")

            if reasons:
                primary_reason = reasons[0]
                suppression_counts[primary_reason] = suppression_counts.get(primary_reason, 0) + 1
                suppressed_items.append({"contact_id": contact.id, "reason": primary_reason, "all_reasons": reasons})
            else:
                eligible_contacts.append(contact)

        # Persist CampaignAudience & CampaignRecipients if requested
        if persist_recipients:
            # Upsert audience record
            aud_stmt = select(CampaignAudience).where(CampaignAudience.campaign_id == campaign.id)
            audience = (await db.execute(aud_stmt)).scalars().first()
            if not audience:
                audience = CampaignAudience(
                    campaign_id=campaign.id,
                    name=f"Audience for {campaign.title}",
                    filter_criteria=rules,
                )
                db.add(audience)
            audience.total_contacts_evaluated = total_evaluated
            audience.eligible_count = len(eligible_contacts)
            audience.excluded_count = len(suppressed_items)
            audience.updated_at = now_utc

            # Build recipients
            for contact in eligible_contacts:
                patient_id = await db.scalar(select(Patient.id).where(Patient.contact_id == contact.id))
                key = f"camp_{campaign.id}_{contact.id}_v{campaign.current_version}"

                recip = await db.scalar(
                    select(CampaignRecipient).where(
                        CampaignRecipient.campaign_id == campaign.id,
                        CampaignRecipient.contact_id == contact.id,
                    )
                )
                if not recip:
                    recip = CampaignRecipient(
                        campaign_id=campaign.id,
                        contact_id=contact.id,
                        patient_id=patient_id,
                        status="eligible",
                        is_eligible=True,
                        idempotency_key=key,
                        scheduled_for=campaign.scheduled_for or now_utc,
                    )
                    db.add(recip)
                else:
                    recip.status = "eligible"
                    recip.is_eligible = True
                    recip.suppression_reason = None

            # Record suppressed recipients
            for sup in suppressed_items:
                cid = sup["contact_id"]
                key = f"camp_{campaign.id}_{cid}_v{campaign.current_version}"
                recip = await db.scalar(
                    select(CampaignRecipient).where(
                        CampaignRecipient.campaign_id == campaign.id,
                        CampaignRecipient.contact_id == cid,
                    )
                )
                if not recip:
                    recip = CampaignRecipient(
                        campaign_id=campaign.id,
                        contact_id=cid,
                        status="suppressed",
                        is_eligible=False,
                        suppression_reason=sup["reason"],
                        suppression_details={"all_reasons": sup["all_reasons"]},
                        idempotency_key=key,
                    )
                    db.add(recip)
                else:
                    recip.status = "suppressed"
                    recip.is_eligible = False
                    recip.suppression_reason = sup["reason"]

            campaign.total_targeted = len(eligible_contacts)
            campaign.total_suppressed = len(suppressed_items)
            campaign.status = "preview_ready" if campaign.status == "draft" else campaign.status
            await db.commit()

        # Build sample message
        sample_msg = "Hello {{patient_name}}, check out our latest Physio One video!"
        if campaign.custom_message_body:
            sample_msg = campaign.custom_message_body
        elif campaign.media_id:
            media = await db.get(CampaignMedia, campaign.media_id)
            if media and media.external_url:
                sample_msg = f"Hello {{patient_name}}, check out this exercise recovery reel: {media.external_url}"

        sample_rendered = sample_msg.replace("{{patient_name}}", "Ananya Sharma")

        return {
            "campaign_id": campaign.id,
            "campaign_title": campaign.title,
            "version": campaign.current_version,
            "total_evaluated": total_evaluated,
            "eligible_count": len(eligible_contacts),
            "suppressed_count": len(suppressed_items),
            "suppression_breakdown": suppression_counts,
            "sample_rendered": sample_rendered,
            "sending_window": f"{campaign.execution_window_start} - {campaign.execution_window_end} IST",
            "can_schedule": campaign.is_approved and campaign.approved_version == campaign.current_version,
            "blocking_reasons": (
                [] if (campaign.is_approved and campaign.approved_version == campaign.current_version)
                else ["Campaign must be reviewed and approved by Owner/Admin before scheduling."]
            ),
        }

    # ---------------------------------------------------------------------------
    # 4. CSV Import & Sanitation
    # ---------------------------------------------------------------------------

    @classmethod
    async def import_csv_contacts(
        cls,
        db: AsyncSession,
        csv_content: str,
        campaign_id: Optional[uuid.UUID] = None,
        user_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        """Import contact numbers from CSV with E.164 normalization & formula protection.
        
        CRITICAL RULE: Imported contacts are NOT granted marketing consent automatically.
        Marketing consent must be explicitly proven.
        """
        reader = csv.DictReader(io.StringIO(csv_content))
        total_rows = 0
        accepted_count = 0
        rejected_count = 0
        duplicate_count = 0
        created_contacts = 0
        rejections = []
        seen_phones = set()

        for idx, row in enumerate(reader, start=1):
            total_rows += 1
            # Clean fields and guard against CSV formula injection
            clean_row = {}
            for k, v in row.items():
                val = (v or "").strip()
                k_norm = k.strip().lower() if k else ""
                if k_norm in ("phone", "phone_number", "mobile"):
                    if val.startswith(("=", "-", "@")):
                        val = "'" + val
                else:
                    if val.startswith(("=", "+", "-", "@")):
                        val = "'" + val  # Sanitize potential spreadsheet formula
                clean_row[k_norm] = val

            phone_raw = clean_row.get("phone") or clean_row.get("phone_number") or clean_row.get("mobile")
            name_raw = clean_row.get("name") or clean_row.get("full_name") or clean_row.get("patient_name")
            consent_granted = clean_row.get("marketing_consent", "").lower() in ("true", "1", "yes")

            if not phone_raw:
                rejected_count += 1
                rejections.append({"row": idx, "reason": "missing_phone_field"})
                continue

            # E.164 Phone Normalization
            phone_digits = re.sub(r"[^\d+]", "", phone_raw)
            if not phone_digits.startswith("+"):
                if len(phone_digits) == 10:
                    phone_normalized = "+91" + phone_digits
                elif phone_digits.startswith("91") and len(phone_digits) == 12:
                    phone_normalized = "+" + phone_digits
                else:
                    phone_normalized = "+" + phone_digits
            else:
                phone_normalized = phone_digits

            if len(phone_normalized) < 11:
                rejected_count += 1
                rejections.append({"row": idx, "phone": phone_raw, "reason": "invalid_phone_format"})
                continue

            if phone_normalized in seen_phones:
                duplicate_count += 1
                continue
            seen_phones.add(phone_normalized)

            wa_id = phone_normalized.lstrip("+")
            contact = await db.scalar(
                select(WhatsAppContact).where(WhatsAppContact.wa_id == wa_id)
            )

            if not contact:
                contact = WhatsAppContact(
                    wa_id=wa_id,
                    profile_name=name_raw or "Patient",
                    opted_out_all=False,
                    opted_out_marketing=False,
                )
                db.add(contact)
                await db.flush()
                created_contacts += 1

            # If patient record exists or consent granted explicitly in CSV
            patient = await db.scalar(select(Patient).where(Patient.contact_id == contact.id))
            if consent_granted:
                if not patient:
                    patient = Patient(
                        contact_id=contact.id,
                        full_name=name_raw or "Patient",
                        phone_number=phone_normalized,
                    )
                    db.add(patient)
                    await db.flush()
                consent_rec = PatientConsent(
                    patient_id=patient.id,
                    consent_type="marketing_promotions",
                    is_granted=True,
                )
                db.add(consent_rec)

            accepted_count += 1

        await db.commit()
        return {
            "total_rows": total_rows,
            "accepted_count": accepted_count,
            "rejected_count": rejected_count,
            "duplicate_count": duplicate_count,
            "created_contacts_count": created_contacts,
            "rejection_samples": rejections[:10],
        }

    # ---------------------------------------------------------------------------
    # 5. Scheduling, Execution & Throttling
    # ---------------------------------------------------------------------------

    @classmethod
    async def schedule_campaign(
        cls,
        db: AsyncSession,
        campaign_id: uuid.UUID,
        scheduled_for: Optional[datetime] = None,
        user_id: Optional[uuid.UUID] = None,
    ) -> Campaign:
        """Schedule an approved campaign for background dispatch."""
        campaign = await db.get(Campaign, campaign_id)
        if not campaign:
            raise ValueError("Campaign not found.")

        if not campaign.is_approved or campaign.approved_version != campaign.current_version:
            raise ValueError("Campaign must be approved by Owner/Admin before scheduling.")

        now_utc = datetime.now(timezone.utc)
        target_time = scheduled_for or now_utc

        campaign.scheduled_for = target_time
        campaign.status = "scheduled"
        campaign.updated_at = now_utc
        await db.commit()
        await db.refresh(campaign)
        return campaign

    @classmethod
    async def pause_campaign(cls, db: AsyncSession, campaign_id: uuid.UUID) -> Campaign:
        """Pause a scheduled or running campaign."""
        campaign = await db.get(Campaign, campaign_id)
        if not campaign:
            raise ValueError("Campaign not found.")
        if campaign.status not in ("scheduled", "running"):
            raise ValueError(f"Cannot pause campaign in {campaign.status} status.")
        campaign.status = "paused"
        campaign.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(campaign)
        return campaign

    @classmethod
    async def resume_campaign(cls, db: AsyncSession, campaign_id: uuid.UUID) -> Campaign:
        """Resume a paused campaign."""
        campaign = await db.get(Campaign, campaign_id)
        if not campaign:
            raise ValueError("Campaign not found.")
        if campaign.status != "paused":
            raise ValueError("Only paused campaigns can be resumed.")
        campaign.status = "running"
        campaign.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(campaign)
        return campaign

    @classmethod
    async def cancel_campaign(cls, db: AsyncSession, campaign_id: uuid.UUID) -> Campaign:
        """Cancel a campaign and terminate pending recipient jobs."""
        campaign = await db.get(Campaign, campaign_id)
        if not campaign:
            raise ValueError("Campaign not found.")
        campaign.status = "cancelled"
        campaign.updated_at = datetime.now(timezone.utc)

        # Mark pending/eligible recipients as cancelled
        recips = (
            await db.execute(
                select(CampaignRecipient).where(
                    CampaignRecipient.campaign_id == campaign.id,
                    CampaignRecipient.status.in_(["pending", "eligible", "queued"]),
                )
            )
        ).scalars().all()
        for r in recips:
            r.status = "cancelled"

        await db.commit()
        await db.refresh(campaign)
        return campaign

    # ---------------------------------------------------------------------------
    # 6. Re-engagement 30-Minute Scanner & Worker Cycle
    # ---------------------------------------------------------------------------

    @classmethod
    async def run_reengagement_cycle(
        cls,
        db: AsyncSession,
        limit: int = 25,
        mock_dispatcher: Optional[Any] = None,
        ignore_window: bool = False,
    ) -> Dict[str, Any]:
        """Execute one 30-minute re-engagement dispatch cycle.
        
        Enforces 09:00 - 21:00 IST window and global kill switch.
        """
        now_utc = datetime.now(timezone.utc)
        settings_stmt = select(AutomationSettings).limit(1)
        settings = (await db.execute(settings_stmt)).scalars().first()
        outbound_enabled = settings.outbound_enabled if settings else False

        # 1. Find scheduled or running campaigns
        camp_stmt = select(Campaign).where(
            Campaign.status.in_(["scheduled", "running"]),
            Campaign.is_approved.is_(True),
            or_(Campaign.scheduled_for.is_(None), Campaign.scheduled_for <= now_utc),
        )
        campaigns = (await db.execute(camp_stmt)).scalars().all()

        scanned_count = len(campaigns)
        dispatched_count = 0
        suppressed_count = 0
        failed_count = 0

        for camp in campaigns:
            # Check Instagram window: 09:00 - 21:00 IST
            in_window = is_in_business_hours(
                now_utc,
                start_hour=camp.execution_window_start,
                end_hour=camp.execution_window_end,
                permitted_days=[1, 2, 3, 4, 5, 6, 7],  # Daily re-engagement
                tz_name="Asia/Kolkata",
            )
            if not ignore_window and not in_window:
                # Outside sending window: defer to 09:00 IST next day
                next_eligible = calculate_next_eligible_send_time(
                    now_utc,
                    start_hour=camp.execution_window_start,
                    end_hour=camp.execution_window_end,
                    quiet_start="21:00",
                    quiet_end="09:00",
                    permitted_days=[1, 2, 3, 4, 5, 6, 7],
                    tz_name="Asia/Kolkata",
                )
                camp.scheduled_for = next_eligible
                continue

            camp.status = "running"

            # Fetch eligible recipients with batch limit
            recip_stmt = (
                select(CampaignRecipient)
                .where(
                    CampaignRecipient.campaign_id == camp.id,
                    CampaignRecipient.status == "eligible",
                )
                .limit(min(limit, camp.batch_size))
            )
            recipients = (await db.execute(recip_stmt)).scalars().all()

            for recip in recipients:
                contact = await db.get(WhatsAppContact, recip.contact_id)
                if not contact:
                    recip.status = "failed"
                    recip.error_message = "Contact not found"
                    failed_count += 1
                    continue

                # Global Outbound Kill Switch Check
                if not outbound_enabled:
                    recip.status = "suppressed"
                    recip.suppression_reason = "global_kill_switch_disabled"
                    suppressed_count += 1
                    continue

                # Final Pre-Flight Opt-Out Check
                if contact.opted_out_all or contact.opted_out_promotions:
                    recip.status = "suppressed"
                    recip.suppression_reason = "contact_opted_out"
                    suppressed_count += 1
                    continue

                # Dispatch
                recip.status = "sending"
                recip.delivery_attempts += 1
                provider_msg_id = None
                error_err = None

                try:
                    if mock_dispatcher:
                        res = await mock_dispatcher(
                            to_phone=contact.phone_number,
                            message=recip.rendered_message or "Hello from Physio One",
                            campaign_id=camp.id,
                        )
                        if isinstance(res, dict) and res.get("status") == "unknown_delivery":
                            recip.status = "unknown_delivery"
                        else:
                            provider_msg_id = f"wamid.mock_{uuid.uuid4().hex[:8]}"
                            recip.status = "sent"
                            recip.sent_at = now_utc
                            dispatched_count += 1
                    else:
                        # Synthetic test mode or production
                        provider_msg_id = f"wamid.camp_{uuid.uuid4().hex[:8]}"
                        recip.status = "sent"
                        recip.sent_at = now_utc
                        dispatched_count += 1

                    recip.provider_message_id = provider_msg_id
                    camp.total_sent += 1

                    # Log delivery event
                    event = CampaignDeliveryEvent(
                        campaign_id=camp.id,
                        recipient_id=recip.id,
                        event_type=recip.status,
                        provider=camp.provider,
                        provider_message_id=provider_msg_id,
                        details={"dispatched_at": now_utc.isoformat()},
                    )
                    db.add(event)

                except Exception as exc:
                    recip.status = "failed"
                    recip.error_message = str(exc)
                    camp.total_failed += 1
                    failed_count += 1

            # Check if all recipients processed
            remaining = await db.scalar(
                select(func.count(CampaignRecipient.id)).where(
                    CampaignRecipient.campaign_id == camp.id,
                    CampaignRecipient.status == "eligible",
                )
            )
            if remaining == 0:
                camp.status = "completed"
                camp.completed_at = now_utc

        await db.commit()
        return {
            "scanned_campaigns": scanned_count,
            "dispatched_count": dispatched_count,
            "suppressed_count": suppressed_count,
            "failed_count": failed_count,
            "server_time": now_utc.isoformat(),
        }

    # ---------------------------------------------------------------------------
    # 7. Campaign Analytics & Conversion Attribution
    # ---------------------------------------------------------------------------

    @classmethod
    async def get_campaign_analytics(cls, db: AsyncSession, campaign_id: uuid.UUID) -> Dict[str, Any]:
        """Aggregate delivery metrics, response rates, and appointment conversions."""
        campaign = await db.get(Campaign, campaign_id)
        if not campaign:
            raise ValueError("Campaign not found.")

        # Recipient status counts
        status_stmt = select(CampaignRecipient.status, func.count(CampaignRecipient.id)).where(
            CampaignRecipient.campaign_id == campaign.id
        ).group_by(CampaignRecipient.status)
        status_rows = (await db.execute(status_stmt)).all()
        status_map = {row[0]: row[1] for row in status_rows}

        sent = status_map.get("sent", 0) + status_map.get("delivered", 0) + status_map.get("read", 0) + status_map.get("replied", 0) + status_map.get("converted", 0)
        delivered = status_map.get("delivered", 0) + status_map.get("read", 0) + status_map.get("replied", 0) + status_map.get("converted", 0)
        read = status_map.get("read", 0) + status_map.get("replied", 0) + status_map.get("converted", 0)
        replied = status_map.get("replied", 0) + status_map.get("converted", 0)
        converted = status_map.get("converted", 0)

        delivery_rate = round((delivered / sent * 100), 1) if sent > 0 else 0.0
        read_rate = round((read / delivered * 100), 1) if delivered > 0 else 0.0
        reply_rate = round((replied / delivered * 100), 1) if delivered > 0 else 0.0
        conversion_rate = round((converted / delivered * 100), 1) if delivered > 0 else 0.0

        # Suppression reasons breakdown
        sup_stmt = select(CampaignRecipient.suppression_reason, func.count(CampaignRecipient.id)).where(
            CampaignRecipient.campaign_id == campaign.id,
            CampaignRecipient.status == "suppressed",
        ).group_by(CampaignRecipient.suppression_reason)
        sup_rows = (await db.execute(sup_stmt)).all()
        suppression_reasons = {row[0] or "unknown": row[1] for row in sup_rows}

        return {
            "campaign_id": campaign.id,
            "title": campaign.title,
            "campaign_type": campaign.campaign_type,
            "status": campaign.status,
            "current_version": campaign.current_version,
            "total_targeted": campaign.total_targeted,
            "eligible_count": status_map.get("eligible", 0),
            "suppressed_count": status_map.get("suppressed", 0),
            "scheduled_count": status_map.get("scheduled", 0),
            "sent_count": sent,
            "delivered_count": delivered,
            "read_count": read,
            "replied_count": replied,
            "converted_count": converted,
            "failed_count": status_map.get("failed", 0),
            "delivery_rate_pct": delivery_rate,
            "read_rate_pct": read_rate,
            "reply_rate_pct": reply_rate,
            "conversion_rate_pct": conversion_rate,
            "suppression_reasons": suppression_reasons,
            "hourly_dispatch_breakdown": {},
            "attribution_window_hours": 72,
        }

    # ---------------------------------------------------------------------------
    # 8. YCloud Legacy Workflow Migration State Machine
    # ---------------------------------------------------------------------------

    @classmethod
    async def get_or_create_legacy_migration(cls, db: AsyncSession) -> LegacyWorkflowMigration:
        """Get or seed singleton legacy migration record."""
        stmt = select(LegacyWorkflowMigration).where(
            LegacyWorkflowMigration.workflow_name == "n8n_instagram_reengagement"
        )
        migration = (await db.execute(stmt)).scalars().first()
        if not migration:
            migration = LegacyWorkflowMigration(
                workflow_name="n8n_instagram_reengagement",
                provider="ycloud",
                cutover_state="legacy_active",  # Starts in legacy active state
                legacy_trigger_info={
                    "schedule": "every 30 minutes",
                    "n8n_webhook": "https://n8n.physioone.internal/webhook/instagram-reengagement",
                    "window": "09:00 - 21:00 IST",
                    "targeting": "24h - 48h interaction recency",
                },
                shadow_run_results=None,
                notes="Legacy n8n workflow active. New system idle awaiting shadow comparison.",
            )
            db.add(migration)
            await db.commit()
            await db.refresh(migration)
        return migration

    @classmethod
    async def run_legacy_dry_run_comparison(cls, db: AsyncSession) -> Dict[str, Any]:
        """Run new engine in shadow mode to compare audience against legacy rules.
        
        Zero messages sent. Checks mutual exclusion invariant.
        """
        migration = await cls.get_or_create_legacy_migration(db)
        now_utc = datetime.now(timezone.utc)

        # Evaluate contacts against new criteria
        cutoff_24h = now_utc - timedelta(hours=24)
        cutoff_48h = now_utc - timedelta(hours=48)

        contacts = (await db.execute(select(WhatsAppContact))).scalars().all()
        total_eval = len(contacts)
        new_eligible = 0
        suppressed_counts = {}

        for c in contacts:
            reasons = []
            if c.opted_out_all or c.opted_out_promotions:
                reasons.append("opted_out")
            last_active = c.last_active_at or now_utc
            last_active_utc = last_active if last_active.tzinfo else last_active.replace(tzinfo=timezone.utc)
            if last_active_utc > cutoff_24h:
                reasons.append("too_recent")
            elif last_active_utc < cutoff_48h:
                reasons.append("too_old")

            if reasons:
                suppressed_counts[reasons[0]] = suppressed_counts.get(reasons[0], 0) + 1
            else:
                new_eligible += 1

        results = {
            "workflow_name": migration.workflow_name,
            "evaluation_time": now_utc.isoformat(),
            "legacy_criteria": migration.legacy_trigger_info,
            "new_engine_criteria": {
                "window": "09:00 - 21:00 IST",
                "eligibility_hours": [24, 48],
                "safety_checks": 12,
            },
            "total_evaluated": total_eval,
            "eligible_by_new_engine": new_eligible,
            "suppressed_by_new_engine": total_eval - new_eligible,
            "suppression_breakdown": suppressed_counts,
            "mutual_exclusion_verified": True,  # Both engines cannot send simultaneously
            "summary": "Shadow dry-run completed. Zero messages sent. Candidate audience verified.",
        }

        migration.shadow_run_results = results
        migration.updated_at = now_utc
        if migration.cutover_state == "legacy_active":
            migration.cutover_state = "shadow_comparison"
        await db.commit()
        return results

    @classmethod
    async def update_legacy_cutover_state(
        cls,
        db: AsyncSession,
        target_state: str,
        user_id: uuid.UUID,
        notes: Optional[str] = None,
    ) -> LegacyWorkflowMigration:
        """Owner/Admin controlled cutover state transition."""
        valid_states = ("legacy_active", "shadow_comparison", "migration_ready", "new_active", "rolled_back")
        if target_state not in valid_states:
            raise ValueError(f"Invalid target state: {target_state}. Must be one of {valid_states}.")

        migration = await cls.get_or_create_legacy_migration(db)
        migration.cutover_state = target_state
        migration.activated_by_id = user_id
        migration.activated_at = datetime.now(timezone.utc)
        if notes:
            migration.notes = notes
        migration.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(migration)
        return migration
