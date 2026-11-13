# PRD: WhatsApp AI Agent Platform (Single Organization Edition)

## Overview
A production-ready, modular, Docker-based WhatsApp AI Agent platform designed for single-business deployment (initial reference implementation: **Physio One Clinic**). Replaces legacy n8n workflows with a high-performance, maintainable, versioned software product built with Next.js, FastAPI, PostgreSQL (pgvector), Redis, Celery, and a provider-independent LLM/WhatsApp gateway.

---

## Architectural Principles & Strict Constraints
- **Single-Organization Only**: Strictly NO multi-tenancy. No `organization_id` or `tenant_id` columns in the database. No tenant switching or SaaS billing complexity. Each organization receives an independent instance, database, and credential set.
- **Deterministic Validation Rules**: Sensitive business decisions (Sunday clinic closures, appointment slot validation, follow-up opt-out checks, campaign eligibility) are hardcoded in deterministic backend Python logic. The LLM handles conversational synthesis and intent extraction, but never authorization or rule override.
- **Data Protection & Persistence**: Version upgrades and migrations must follow expand-and-contract patterns. No data loss of patient records, chat histories, or configurations during upgrades.
- **Extensible & Generic**: All clinic-specific variables (clinic name, working hours, services, prompts) are driven by configuration and database settings, allowing zero-code re-branding for other businesses.

---

## Task 1: Architecture Specification and Repository Scaffolding (Phase 1)
Establish the architectural blueprint, repository layout, baseline specifications, and design documents.
- Inspect the workspace and initialize git branches (`main`, `development`).
- Scaffold directory structure:
  - `backend/app/` (core, api, models, schemas, services, agents, tools, workers)
  - `frontend/` (Next.js, components, hooks, lib, styles)
  - `docker/` (Dockerfile.api, Dockerfile.frontend, Dockerfile.worker)
  - `scripts/` (backup, restore, migrate, update)
  - `docs/` (comprehensive documentation)
- Generate core architecture documentation:
  - `ARCHITECTURE.md` - Modular system architecture, layer diagrams, and service interactions.
  - `DATABASE.md` - Complete schema design for all 30 single-tenant entities with pgvector.
  - `API.md` - REST API specification for auth, inbox, agents, appointments, campaigns, updates.
  - `DOCKER.md` - Multi-container architecture, persistent volumes, environment configs.
  - `UPDATE.md` - Semantic versioning, expand-and-contract migration strategy, rollback protocol.
  - `ROADMAP.md` - Step-by-step phased execution roadmap.
  - `SECURITY.md` - Threat model, credential handling, token safety, data isolation.
  - `CHANGELOG.md` - Initial changelog starting at `v1.0.0-draft`.
- Present architecture for user approval before coding Phase 2.

---

## Task 2: Core Database Schema and Alembic Migrations (Phase 2 - Part 1)
Implement the relational database foundation using PostgreSQL 16, pgvector, SQLAlchemy 2.0 (async), and Alembic.
- Define UUID primary keys, foreign key relationships, indexes, and UTC timestamp mixins.
- Implement the 30 single-business entities:
  - `users`, `roles`, `permissions`
  - `whatsapp_accounts`, `whatsapp_contacts`, `whatsapp_messages`, `whatsapp_templates`
  - `conversations`, `conversation_summaries`, `conversation_memory` (with pgvector embedding column)
  - `patients`, `patient_consents`, `appointments`
  - `ai_agents`, `ai_agent_versions`, `ai_models`, `ai_provider_configs`, `ai_tool_definitions`, `ai_tool_executions`
  - `campaigns`, `campaign_templates`, `campaign_deliveries`
  - `automation_rules`, `automation_executions`, `scheduled_followups`, `message_debounce`
  - `knowledge_bases`, `knowledge_documents`, `knowledge_chunks` (with pgvector embeddings)
  - `integrations`, `system_settings`, `audit_logs`, `background_jobs`
- Setup Alembic migration environment and generate baseline migration script.
- Create automated database seeding script for default roles, permissions, system settings, and initial Physio One configuration.

---

## Task 3: Authentication, RBAC, and User Management API (Phase 2 - Part 2)
Implement secure session management, JWT authentication with HTTP-only cookies, and Role-Based Access Control (RBAC).
- Password hashing with Argon2id / bcrypt.
- Roles: `Super Admin`, `Administrator`, `Manager`, `Operator`, `Viewer`.
- Endpoints:
  - `POST /api/v1/auth/login` - Secure session issuance with HTTP-only cookie & CSRF protection.
  - `POST /api/v1/auth/logout` - Session invalidation and cookie clearing.
  - `POST /api/v1/auth/refresh` - Refresh access token.
  - `GET /api/v1/auth/me` - Current authenticated user & permissions.
  - `GET /api/v1/users`, `POST /api/v1/users`, `PUT /api/v1/users/:id`, `DELETE /api/v1/users/:id`
  - `GET /api/v1/roles`, `PUT /api/v1/roles/:id/permissions`
- Audit log middleware capturing user logins, role modifications, and administrative operations.
- Unit tests for authentication and authorization scopes.

---

## Task 4: Next.js Dashboard Foundation & Auth Shell (Phase 3 - Part 1)
Build the frontend application shell using Next.js 14+ (App Router), TypeScript, Tailwind CSS, and shadcn/ui.
- Setup modern layout with collapsible sidebar, header with user profile menu, breadcrumbs, and live connection status indicator.
- Implement authentication state management (React Query + Context), protected route middleware, and login view.
- Theme system supporting Light/Dark modes.
- Implement core UI primitives: Data table with sorting/filtering/pagination, modal dialogs, status badges, toast notifications.

---

## Task 5: Dashboard UI Sections (Inbox, Contacts, Appointments, Settings) (Phase 3 - Part 2)
Develop the core operational views connected to real backend endpoints.
- **Overview Dashboard**: Key metrics (active chats, appointments booked, follow-up conversion, response times), recent activity feed.
- **WhatsApp Inbox**: Two-pane chat UI (conversation list with search/filters, active message thread, patient summary card, human takeover toggle, template quick-send).
- **Contacts & Patients**: Searchable patient table, medical note summary, consent status, appointment history drawer.
- **Appointments Calendar**: Day/Week/Month view, status filters (Confirmed, Pending, Cancelled), manual booking/rescheduling modal with Sunday blackout enforcement.
- **System Settings**: Business profile (Physio One), working hours, WhatsApp API credentials, LLM keys, storage settings.

---

## Task 6: WhatsApp Cloud API & Webhook Adapter Engine (Phase 4)
Build the WhatsApp integration layer with provider-agnostic adapter interfaces.
- Webhook verification endpoint (`GET /api/v1/whatsapp/webhook`).
- Inbound payload processing (`POST /api/v1/whatsapp/webhook`):
  - Immediate 200 OK acknowledgement.
  - Asynchronous background dispatch via Celery & Redis.
  - Duplicate prevention & message debouncing (Redis-backed window).
  - Media & voice-note processing: download media via Cloud API, store in Supabase/S3, transcribe voice notes using Whisper / LLM audio API.
- Outbound WhatsApp adapter supporting:
  - Official Meta Cloud API.
  - YCloud adapter.
  - Template messages and interactive button/list messages.
  - Delivery status updates (`sent`, `delivered`, `read`, `failed`).

---

## Task 7: Multi-Provider LLM Gateway & Agent Runtime (Phase 5)
Implement an extensible, resilient LLM abstraction layer and agent execution runtime.
- Provider-agnostic gateway interface supporting:
  - Meta Model API (Muse).
  - OpenAI (GPT-4o, etc.).
  - Anthropic (Claude 3.5 Sonnet, etc.).
  - Generic OpenAI-compatible local/cloud endpoints.
- Per-agent configuration: model name, temperature, max tokens, timeout, retry strategy with exponential backoff, rate-limit fallback chain.
- Agent Runtime:
  - Context assembly (system instructions, patient profile, recent conversation history, retrieved memory chunks, available tools).
  - Streaming token support.
  - Structured tool calling and parsing.
  - Fallback mechanisms when a provider experiences outage or quota exhaustion.

---

## Task 8: Conversation Memory (pgvector) & Extensible Tool Registry (Phase 6)
Build the cognitive memory subsystem and secure tool execution framework.
- **Conversation Memory**:
  - Short-term sliding window of recent messages.
  - Asynchronous background conversation summarization.
  - Semantic memory using `pgvector` embeddings for patient preferences, past clinical complaints, and FAQ context.
- **Secure Tool Registry**:
  - Strict schema-validated tool definitions.
  - Initial registered tools:
    - `find_patient` (by phone or name)
    - `register_patient` (name, age, gender, contact)
    - `check_availability` (date, time slot, practitioner)
    - `book_appointment` (date, time, service, notes)
    - `reschedule_appointment` (appointment_id, new_date, new_time)
    - `cancel_appointment` (appointment_id, reason)
    - `search_knowledge_base` (semantic query)
    - `request_human_handoff` (reason, priority)
  - Strict sandboxing: tools execute pre-compiled Python services; zero arbitrary SQL execution.
  - Audit logging of tool inputs, outputs, execution duration, and errors.

---

## Task 9: Deepti Receptionist & Clinic Rules Engine (Phase 7)
Implement the specialized AI receptionist persona ("Deepti") for Physio One.
- Multilingual conversational capabilities: Hindi, Hinglish, and English.
- System prompt and clinical guardrails: friendly, polite, empathetic, professional receptionist tone.
- **Mandatory Business Rule Validation**:
  - Sunday booking rejection hardcoded in backend verification (`weekday == 6` -> reject).
  - Working hours validation (e.g., 09:00 AM - 08:00 PM).
  - Slot collision prevention with database row locking.
  - Require explicit patient confirmation before committing appointments.
  - Medical advice disclaimer: Deepti never prescribes medicines or diagnoses; guides patients to book consultation.
- Human escalation trigger: detect patient frustration, urgent emergency requests, or explicit requests for a human doctor/staff member.

---

## Task 10: 3-Touch Follow-Up Engine & Scheduler (Phase 8)
Build the automated re-engagement engine replacing the legacy n8n follow-up workflow.
- Three-touch follow-up sequence:
  - **Touch 1**: Triggered after 2 hours of conversation inactivity without completed booking.
  - **Touch 2**: Configurable interval (e.g. 24 hours later) offering assistance or slot options.
  - **Touch 3**: Final gentle follow-up (e.g. 48 hours later / 5 hours inactivity rule).
- **Deterministic Pre-flight Verification**:
  - Verify patient has NOT opted out of messages.
  - Verify NO future confirmed appointment already exists.
  - Verify NO active human operator takeover is engaged.
  - Verify message is within allowable business hours (09:00 - 20:00 IST).
  - Verify duplicate lock in Redis.
- Copywriting Agent generates personalized messages based on prior discussion while adhering to template guidelines.

---

## Task 11: Instagram Re-engagement Campaign Engine (Phase 9)
Implement marketing campaign broadcast and engagement tracking for social leads.
- Campaign management interface: Reel URL, thumbnail, headline, campaign goal, audience filter.
- Dynamic message personalization via Campaign Agent.
- **Eligibility Engine (Evaluated every 30 mins via Celery Beat)**:
  - Patient interacted 24–48 hours ago.
  - No active future appointment.
  - No marketing opt-out.
  - Never previously delivered for this specific campaign ID.
  - Strict time window compliance: 09:00 – 21:00 Asia/Kolkata.
- WhatsApp Cloud API template dispatch with rate limiting and delivery tracking.

---

## Task 12: Analytics Engine, Execution Logs & Audit Trail (Phase 10)
Develop operational reporting, performance telemetry, and diagnostic logs.
- **Analytics Metrics**:
  - Message volumes (inbound vs outbound).
  - Agent response latency (p50, p95).
  - Appointment conversion rates (inquiries -> bookings).
  - Follow-up touchpoint effectiveness.
  - Token consumption and provider cost estimation.
- **Execution Logs View**:
  - Searchable log of every incoming webhook, tool execution, LLM call, and error stack trace.
  - Filterable by conversation ID, patient phone number, status, or date range.
- **Audit Trail**:
  - Tamper-evident log of all administrative actions, credential updates, role changes, and manual appointment overrides.

---

## Task 13: Production Docker Compose & Multi-Platform Deployment (Phase 11)
Package the entire solution for reliable, reproducible containerized deployment.
- Multi-container architecture:
  - `web` (Next.js frontend)
  - `api` (FastAPI backend)
  - `worker` (Celery background processor)
  - `scheduler` (Celery Beat cron runner)
  - `postgres` (PostgreSQL 16 with pgvector)
  - `redis` (Redis 7 for queues and debouncing)
- Configured files:
  - `Dockerfile.api`, `Dockerfile.frontend`, `Dockerfile.worker`
  - `docker-compose.yml` (local development)
  - `docker-compose.prod.yml` (production hardening with health checks and restart policies)
  - `.env.example` with full configuration schema
- Multi-platform deployment blueprints:
  - Dedicated VPS / VM via Docker Compose.
  - Google Cloud Run (split frontend/api containers with Cloud SQL and Memorystore).
  - Vercel/Netlify frontend + Cloud Run backend.

---

## Task 14: Versioned Update Manager & Database Migration Safeguards (Phase 12)
Implement semantic versioning (`v1.0.0`), in-app update checks, and bulletproof database migration protocols.
- Centralized version manifest (`version.json`) and system update dashboard.
- Update Manager automated pipeline:
  1. Check remote registry/git for newer release tag.
  2. Display release notes and schema change warnings.
  3. Pre-update automated database snapshot/backup (`pg_dump` with verification).
  4. Pull updated Docker images.
  5. Run Alembic migrations (expand-and-contract / forward-compatible).
  6. Service health check verification.
  7. Rollback protocol if health checks fail.
- Critical Data Protection Safeguards:
  - Explicit prohibitions against dropping columns containing historical data.
  - Automated pre-migration backup validation before applying DDL changes.
  - Standalone scripts: `scripts/backup.sh`, `scripts/restore.sh`, `scripts/update.sh`.

---

## Task 15: End-to-End Testing, Security Hardening & Release Packaging (Phase 13)
Final verification, quality assurance, security audit, and formal release.
- **Test Suites**:
  - Pytest unit and integration tests (Auth, Webhook handling, Sunday clinic rules, Appointment booking, Follow-up locks).
  - Frontend component tests and mock API integration.
  - Playwright end-to-end tests covering login, inbox messaging, and appointment booking flows.
- **Security Hardening**:
  - OWASP Top 10 mitigation (CSRF, XSS, SQL injection prevention, rate limiting).
  - Webhook HMAC SHA256 signature verification.
  - Masking of PII (patient phone numbers, health notes) in standard logs.
- Formal release tagging `v1.0.0` with Git release workflow and updated documentation.

