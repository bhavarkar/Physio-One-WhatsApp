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
- **Task 18**: Final Staging Security Gate, Terraform State Audit & Deployment Dry Run [COMPLETED]
- **Task 19**: Correct Cloud Staging Bootstrap, Prepare Windows PowerShell Deployment & Final Release Gate [COMPLETED - STANDING BY AT APPROVAL GATE]
- **Task 20**: Migrate Cloud Run Deployment Architecture to Hostinger Ubuntu VPS (Docker Compose) [COMPLETED - STANDING BY AT VPS APPROVAL GATE]
- **Task 21**: Hostinger VPS Local Integration Rehearsal, Security Audit & Deployment Approval Gate [COMPLETED - STANDING BY AT VPS PREFLIGHT GATE]
- **Task 22**: Hostinger Ubuntu VPS Read-Only Infrastructure Preflight & Deployment Readiness Audit [COMPLETED - PREFLIGHT METRICS VERIFIED]
- **Task 23**: Prepare Physio One for Existing Hostinger VPS (Host Nginx + Host PostgreSQL + n8n Coexistence) [COMPLETED - STANDING BY AT DEPLOYMENT APPROVAL GATE]

---

## Task 19 Status (2026-11-18)
Staging deployment bootstrap dependencies corrected, Windows PowerShell 5.1 native tooling (`scripts/deploy-staging.ps1` and `scripts/verify-staging.ps1`) authored and verified, Cloud Scheduler paused invariant (`paused = true`) enforced in Terraform, migration-before-ingress sequencing guaranteed, and database credential residual risks documented. All verifications passed cleanly: 238 backend tests (100% pass rate), 53 frontend tests across 12 Jest suites, 0 TypeScript errors, 18 Next.js static routes compiled, and Docker Compose healthy. Standing by at the Task 19 Operator Approval Gate (`STAGING_DEPLOYMENT_APPROVAL.md`). Cloud provisioning strictly pending explicit operator sign-off. Zero billable GCP resources created. Zero real WhatsApp messages sent.

---

## Task 20 Status (2026-11-18)
Migrated staging and production deployment target architecture from Google Cloud Run to a dedicated Hostinger Ubuntu Linux VPS (Ubuntu 22.04/24.04 LTS, 4 GB RAM, 50 GB storage) using Docker Compose and Caddy. Multi-container stack designed with strict resource limits: total container memory capped at 2.4 GB, reserving 1.6 GB (40%) free memory for OS and buffers. Implemented private network isolation (PostgreSQL port 5432 strictly unexposed to host). Authored 7 operational bash scripts in `deploy/vps/scripts/` (`preflight.sh`, `deploy.sh`, `migrate.sh`, `backup.sh`, `restore.sh`, `verify.sh`, `rollback.sh`). Replaced Cloud Tasks and Cloud Scheduler with continuous background daemon `app.workers.runner` backed by durable PostgreSQL state tables. Added `test_vps_deployment_architecture.py` with 10 automated unit tests (all passing). Full regression passed: 248 backend tests passed (100%), 53 frontend tests passed across 12 Jest suites, TypeScript 0 errors, Next.js build clean. Standing by at the Task 20 VPS Operator Approval Gate. Zero remote SSH connections made. Zero remote infrastructure modified. Zero real WhatsApp messages sent.

---

## Task 21 Status (2026-11-18)
Rehearsed the complete Hostinger VPS Docker Compose stack on a disposable local environment (`compose.rehearsal.yaml`). Successfully verified PostgreSQL 16 + pgvector, migration to head (64 tables across revisions 001–008), FastAPI backend, Next.js frontend, worker daemon, and Caddy reverse proxy routing. Hardened queue concurrency across `AutomationWorkerService`, `InboundQueueService`, and `CampaignService` with row-level atomic locking (`.with_for_update(skip_locked=True)`). Created 7 new concurrency and reliability tests (`test_vps_queue_concurrency_and_reliability.py`), reaching 255/255 passing backend tests (100%). Performed live backup and restore rehearsal on a clean disposable database, verifying 64 tables and pgvector extension restoration. Measured live container idle memory at 323 MiB total, validating suitability for the 4 GB Hostinger VPS budget. Audited deployment bash scripts, validated syntax, and hardened `--dry-run` modes. Authored read-only preflight inspection checklist `deploy/vps/HOSTINGER_PREFLIGHT_CHECKLIST.md` for Task 22. Cleaned up all disposable rehearsal resources without affecting existing development volumes. Full test scorecard: 255 backend tests passed (100%), 53 frontend tests passed across 12 Jest suites, 0 TypeScript errors, 18 Next.js static routes compiled cleanly. Standing by at the Task 21 VPS Preflight Approval Gate. Zero remote SSH connections made. Zero remote infrastructure modified. Zero real WhatsApp messages sent.

---

## Task 22 Status (2026-11-18)
Executed read-only infrastructure preflight and readiness audit for the Hostinger KVM 1 Ubuntu 24.04.5 LTS VPS. Verified host baseline specifications: 1 vCPU, 3.8 GiB RAM (2.6 GiB currently available), 26 GB free disk, 4 GB swap (521 MiB used). Identified active workloads: existing `n8n` container (`n8n.dataagent.in`) running behind host Nginx (ports 80 & 443), host PostgreSQL 16 running on port 5432 with pgvector 0.6.0 available, Hermes stopped, FreeHire containers removed. Identified critical security finding: host UFW firewall is currently inactive. Documented detailed findings in `deploy/vps/HOSTINGER_VPS_AUDIT.md`. Zero remote changes made.

---

## Task 23 Status (2026-11-18)
Adapted deployment architecture for safe coexistence on the Hostinger KVM 1 VPS alongside existing `n8n.dataagent.in`. Created dedicated Compose profile `deploy/vps/compose.hostinger.yaml` omitting Caddy, binding ingress strictly to `127.0.0.1:3000` (frontend) and `127.0.0.1:8000` (API) to prevent Docker iptables exposure on hosts with inactive UFW, and connecting to host PostgreSQL 16 via `host.docker.internal:5432` (`host-gateway`). Evaluated pgvector 0.6.0 compatibility: confirmed 100% sufficiency for 1536-dimensional embeddings and HNSW cosine indexing. Authored database initialization script `init_host_postgres.sql`, verification probe `verify_host_postgres.sql`, backup runner `backup_host_db.sh`, and restore runner `restore_host_db.sh`. Created separate host Nginx virtual host `deploy/vps/nginx/physio.conf` with 15MB request limits and Certbot setup guide, ensuring zero impact on active n8n workflows. Authored deployment orchestrator `deploy_hostinger.sh` and rollback script `rollback_hostinger.sh`. Full test validation: 255 backend tests passed (100%), 53 frontend tests passed across 12 Jest suites, TypeScript 0 errors, Next.js 18 static routes compiled cleanly, compose configurations validated. Authored operator action plan in `deploy/vps/VPS_DEPLOYMENT_APPROVAL.md`. Standing by at Task 23 Operator Approval Gate. Zero remote commands executed. Zero live WhatsApp messages sent.

