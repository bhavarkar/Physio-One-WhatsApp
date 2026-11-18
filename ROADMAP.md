# ROADMAP: 13-Phase Development Plan (Single Organization Edition)

## Overview & Execution Protocol
The development follows a phased, incremental methodology. Each phase produces working, tested, and verifiable components. No Phase is skipped, and no placeholder mock data is committed.

---

## Phase Matrix

| Phase | Milestone Name | Key Deliverables | Verification & Gate Criteria |
| :--- | :--- | :--- | :--- |
| **Phase 1** | **Architecture & Scaffolding** | `ARCHITECTURE.md`, `DATABASE.md`, `API.md`, `DOCKER.md`, `UPDATE.md`, `ROADMAP.md`, `SECURITY.md`, `CHANGELOG.md`, directory layout. | Peer review and user approval. |
| **Phase 2** | **Database & Authentication** | PostgreSQL 16 + pgvector schema, 30 entities in SQLAlchemy, Alembic migrations, Argon2id auth, JWT cookies, RBAC endpoints. | Alembic migration applies cleanly; auth unit tests pass. |
| **Phase 3** | **Modern Admin Dashboard** | Next.js 14 App Router, shadcn/ui components, Auth shell, Live WhatsApp Inbox, Patients table, Appointment calendar, Settings views. | Frontend builds with zero TypeScript errors; mocks replaced with real API hooks. |
| **Phase 4** | **WhatsApp Integration & Ingress**| Webhook HMAC verification, Celery inbound worker, Redis debouncing, Voice-note Whisper transcription, Meta/YCloud outbound adapter. | Webhook returns 200 OK under 200ms; inbound media downloaded and transcribed. |
| **Phase 5** | **LLM Gateway & AI Runtime** | Provider-agnostic gateway (Muse, OpenAI, Anthropic), rate-limiting fallback chain, multi-turn context staging, function-calling loop. | Gateway handles simulated provider outage by falling back smoothly. |
| **Phase 6** | **Memory & Tool Registry** | `pgvector` semantic memory, conversation summaries, sandboxed Tool Registry (find_patient, book_appointment, etc.) with audit logging. | Cosine similarity query returns relevant context; tools execute with strict parameter typing. |
| **Phase 7** | **Deepti Receptionist Engine** | Physio One multilingual agent (Hindi, Hinglish, English), deterministic Sunday closure rule, working hours validation, human escalation. | Sunday booking attempt raises deterministic error; valid weekday booking succeeds. |
| **Phase 8** | **3-Touch Follow-up Automation** | Inactivity triggers (2h, 24h, 48h), pre-flight safety filter (opt-out, confirmed appointments, active takeover), Celery Beat evaluator. | Follow-up suppressed when patient books an appointment; generated copy adheres to context. |
| **Phase 9** | **Instagram Re-engagement Campaigns** | Reel broadcast manager, audience eligibility filter (24-48h window, no upcoming booking, 09:00-21:00 IST), Celery Beat 30-min cron. | Campaign message delivers only to eligible audience during legal hours. |
| **Phase 10**| **Analytics & Execution Logs** | Inbound/outbound metrics, booking conversion funnel, latency percentiles, searchable execution log, administrative audit trail. | Analytics queries return accurate aggregates; audit log records every admin modification. |
| **Phase 11**| **Production Docker Deployment** | Multi-container Docker Compose, optimized multi-stage Dockerfiles, persistent volumes, Cloud Run & VPS deployment blueprints. | `docker compose up` starts all 6 containers with healthy status checks. |
| **Phase 12**| **Update Manager & Migration Safety**| In-app version manager, `version.json`, automated `pg_dump` pre-update script, expand-and-contract migration enforcement. | Upgrade dry-run creates valid backup and executes migration without data loss. |
| **Phase 13**| **E2E Testing & Security Audit** | Pytest backend suite, Playwright E2E UI suite, OWASP Top 10 security audit, PII masking, final v1.0.0 release packaging. | 100% test pass rate across critical booking and authentication flows. |

---

## Detailed Task Breakdown for Ralph Loop
Each phase corresponds to discrete tasks defined in `PRD.md`:
- **Task 1**: Architecture & Scaffolding [COMPLETED]
- **Task 2**: Core Database Schema & Migrations [COMPLETED]
- **Task 3**: Authentication & RBAC API [COMPLETED]
- **Task 4**: Next.js Dashboard Foundation & Auth Shell [COMPLETED]
- **Task 5**: WhatsApp Provider Integration (Meta Cloud API & YCloud) [COMPLETED]
- **Task 6**: Clinical Appointments Engine & Availability Rules [COMPLETED]
- **Task 7**: Multi-Provider LLM Gateway & Agent Runtime [COMPLETED]
- **Task 8**: pgvector Memory & Clinic Knowledge Base (RAG) [COMPLETED]
- **Task 9**: Inbound WhatsApp AI Receptionist (Deepti) [COMPLETED]
- **Task 10**: Controlled Appointment Management Through Deepti AI Receptionist [COMPLETED]
- **Task 11**: Durable Scheduling, Appointment Reminders & Scheduled Follow-up Automation [COMPLETED]
- **Task 12**: Instagram Re-engagement, YCloud Migration & Controlled WhatsApp Campaigns [COMPLETED]
- **Task 13**: Production Readiness, Security Hardening & End-to-End Integration [COMPLETED]
- **Task 14**: Staging Infrastructure, Container Verification & PostgreSQL Validation [COMPLETED]
- **Task 15**: Production Security Hardening, Cloud Staging Preflight & Deployment Approval Gate [COMPLETED]
- **Task 16**: Google Cloud Staging Deployment Readiness, Integration Verification & Approval Gate [COMPLETED]
- **Task 17**: Resolve Staging Deployment Blockers and Prepare a Safe Google Cloud Launch [COMPLETED]
- **Task 18**: Final Staging Security Gate, Terraform State Audit & Deployment Dry Run [COMPLETED - STANDING BY AT APPROVAL GATE]

---

## Task 18 Status (2026-11-18)
Final staging security gaps closed, Terraform state audited, and deployment dry run completed across 225 backend tests (100% pass rate), 53 frontend tests, 0 TypeScript errors, 18 Next.js static routes, and running Docker containers. Absolute zero-secret Terraform state enforced (`google_sql_user` excised; database user bootstrapped out-of-band via `gcloud sql users create` from Secret Manager), fail-closed WhatsApp isolation with deny-all default allowlist verified, disposable database migration test (`001→008` and rollback/re-upgrade) verified, and complete 43-instance Terraform resource graph audited. Standing by at the Task 18 Operator Approval Gate (`STAGING_DEPLOYMENT_APPROVAL.md`). Cloud provisioning strictly pending explicit operator sign-off. Zero billable GCP resources created. Zero real WhatsApp messages sent.
