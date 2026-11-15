# Staging Pilot Verification Checklist

**Project:** Physio One WhatsApp AI Platform  
**Purpose:** Pre-flight gate checklist to verify system health before starting the controlled staging pilot.  
**Rule:** Every item must be verified and checked off. Any failure halts pilot activation.

---

## 1. Infrastructure & Connectivity

- [ ] **PostgreSQL 16 Connection:**
  - Database reachable over TLS via Cloud SQL Auth Proxy.
  - Connection pool limits configured (min: 5, max: 20).
  - pgvector extension active (`CREATE EXTENSION IF NOT EXISTS vector;`).
- [ ] **Alembic Migration State:**
  - Current database migration matches head: `008_campaigns_instagram_reengagement.py`.
  - Exactly 63 database tables present.
  - HNSW index on `kb_document_chunks (embedding vector_cosine_ops)` active.
- [ ] **Redis / Celery Connectivity:**
  - Redis ping latency < 5ms.
  - Memory limit set with `volatile-lru` eviction policy.
- [ ] **Cloud Storage / Media:**
  - Bucket accessible with uniform bucket-level access enabled.
  - Test upload and signed download URL generation verified.

---

## 2. Security Hardening & Safe Defaults

- [ ] **Global Outbound Kill Switch:**
  - `SELECT outbound_enabled FROM automation_settings;` returns `false`.
  - Attempting scheduled dispatches without admin activation is logged as suppressed.
- [ ] **AI Orchestration Mode:**
  - `SELECT ai_mode FROM ai_inbound_settings;` returns `disabled` (or `shadow` for passive logging).
  - In `shadow` mode, AIResponseDraft records are generated but `dispatched` is strictly `false`.
- [ ] **Appointment Workflow Mode:**
  - `SELECT policy_mode FROM appointment_workflow_settings;` returns `mode_a_read_only`.
  - Autonomous database mutations are completely disabled.
- [ ] **Campaign Manager State:**
  - All existing campaigns are in `draft` or `paused` status.
  - `SELECT is_approved FROM campaigns;` returns `false` for unapproved items.
- [ ] **Legacy n8n/YCloud Migration State:**
  - `legacy_workflow_migrations.cutover_state` is `legacy_active` or `shadow_comparison`.
  - Live cutover has NOT been executed.
- [ ] **Worker Route Authentication:**
  - Calling `/api/v1/automations/process-due` without credentials returns `401 Unauthorized`.
  - Calling with invalid `X-Worker-Token` returns `401 Unauthorized`.
  - Calling with verified Google OIDC service account token returns `200 OK`.
- [ ] **Session Security & RBAC:**
  - Secure session cookies have `HttpOnly`, `SameSite=Lax`, and `Secure=true`.
  - Non-admin users cannot access `/api/v1/users` or `/api/v1/automations/settings`.

---

## 3. End-to-End Functional Verification (Synthetic Data)

- [ ] **Webhook Signature Verification:**
  - Simulated webhook with invalid `X-Hub-Signature-256` is rejected with `401/403`.
  - Valid signed webhook payload is ingested and enqueued in < 100ms.
- [ ] **Message Deduplication:**
  - Replaying identical `provider_message_id` within 24 hours does not create duplicate messages.
- [ ] **Human Takeover & AI Pause:**
  - Marking a conversation `is_human_takeover = true` immediately blocks Deepti draft generation and responses.
- [ ] **Appointment Confirmation & Reschedule Invalidation:**
  - Rescheduling a confirmed appointment automatically cancels old pending reminder jobs (`appointment_reminder_2h`, `appointment_reminder_24h`).
- [ ] **Patient STOP Opt-Out:**
  - Sending "STOP" from a synthetic contact immediately sets `opted_out_all = true`.
  - All subsequent scheduled follow-up and campaign sends are suppressed.
- [ ] **Worker Crash & Lease Timeout Recovery:**
  - Stranded jobs with expired `locked_until` timestamps are automatically recovered during the next worker cycle (`recovered_leases_count >= 1`).

---

## 4. Frontend Dashboard Verification

- [ ] Next.js production build exits code 0 (`npm run build`).
- [ ] Production server starts without errors (`npm start`).
- [ ] Login screen renders properly with CSRF token and Argon2id authentication.
- [ ] Navigation to `/inbox`, `/appointments`, `/campaigns`, `/automations`, `/knowledge`, `/users`, and `/settings` succeeds without client-side React errors.
- [ ] Real-time approvals badge shows pending items awaiting staff review.

---

## 5. Sign-Off & Approvals

| Role | Name | Signature / Approval Date | Status |
|---|---|---|---|
| Clinic Technical Lead | | | Pending |
| Clinic Medical Director | | | Pending |
| Security Officer | | | Pending |
