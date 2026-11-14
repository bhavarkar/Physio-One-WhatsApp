# Physio One — Clinical WhatsApp AI Platform

> **Single Organization Edition** • High-reliability, modular, versioned WhatsApp AI Agent platform engineered for clinical practice management, intelligent triage, appointment scheduling, and patient re-engagement.

[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-14.2%20App%20Router-black.svg)](https://nextjs.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16%20%2B%20pgvector-336791.svg)](https://www.postgresql.org/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-3.4-38B2AC.svg)](https://tailwindcss.com/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## 1. System Vision & Paradigm

The **Physio One WhatsApp AI Platform** replaces legacy, fragile n8n workflows with a production-grade, containerized software product. It combines:
- **Deterministic Clinical Business Rules**: Hard constraints (e.g. Sunday clinic closure, operating hours, double-booking prevention) are enforced authoritatively in backend Python services and database constraints—never delegated to an LLM.
- **Provider-Independent WhatsApp Transport**: Decoupled messaging adapters supporting both the **Official Meta WhatsApp Cloud API** (Graph API v20.0) and **YCloud** (preserving existing Physio One operations).
- **Extensible LLM & Agent Runtime**: Clean abstraction supporting Meta Muse, OpenAI, Anthropic, and custom endpoints with prompt versioning and tool execution sandboxing.
- **Strict Single-Organization Architecture**: Zero multi-tenancy. No `organization_id` or `tenant_id` columns exist in the schema. The clinic maintains full data ownership, with zero SaaS lock-in or tenant switching overhead.

---

## 2. Project Status & Roadmap

The project follows a 15-task development plan. Every milestone produces verified code backed by automated test suites.

### Current Implementation Status

| Milestone | Subsystem | Status | Description |
| :--- | :--- | :---: | :--- |
| **Task 1** | **Architecture & Scaffolding** | Completed | Full architecture specifications, PRD, roadmap, security model, and directory layout. |
| **Task 2** | **Database Schema & Migrations** | Completed | 33 initial SQLAlchemy models, `pgvector(1536)` embeddings, Alembic migrations, test suite. |
| **Task 3** | **Authentication, RBAC & Users** | Completed | Argon2id hashing, secure session management, CSRF defense, 4-tier RBAC (`Owner`, `Admin`, `Operator`, `Viewer`), audit logging. |
| **Task 4** | **Frontend Foundation & Auth Shell** | Completed | Next.js 14 App Router, clinical theme tokens, UI component library, setup wizard (`/setup`), login (`/login`), user management (`/users`). |
| **Task 5** | **WhatsApp Provider Integration** | Completed | `MetaCloudProvider` and `YCloudProvider` adapters, Fernet credential encryption at rest, HMAC webhook signature verification, deduplication, live test messaging UI (`/settings`). |
| **Task 6** | **Clinical Appointments Engine** | Completed | Availability slot generator (09:00 - 20:00 IST), Sunday closure invariant (`Asia/Kolkata`), ACID range exclusion locks, full lifecycle (`created`, `rescheduled`, `cancelled`, `completed`, `no-show`), Next.js management dashboard (`/appointments`). |
| **Task 7** | **Multi-Provider LLM Gateway** | Next Up | Unified LLM abstraction (Muse, OpenAI, Anthropic) with rate-limit fallbacks and structured tool invocation. |
| **Task 8** | **pgvector Memory & Tool Registry** | Planned | Semantic patient memory chunking, conversation summarization, sandboxed tool definitions. |
| **Task 9** | **Deepti Receptionist Agent** | Planned | Multilingual clinic persona (Hindi, English, Hinglish), triage workflows, human handoff. |
| **Task 10** | **3-Touch Follow-Up Engine** | Planned | Inactivity follow-ups (2h, 24h, 48h) with strict pre-flight suppression filters. |
| **Task 11** | **Instagram Campaigns** | Planned | Reel broadcasts, audience eligibility windows (09:00 - 21:00 IST), Celery Beat scheduler. |
| **Task 12** | **Analytics & Execution Logs** | Planned | Booking conversion funnels, latency metrics, token consumption, audit query interface. |
| **Task 13** | **Production Docker Deployment** | Planned | Multi-container Docker Compose, optimized Dockerfiles, Cloud Run blueprint. |
| **Task 14** | **Versioned Update Manager** | Planned | Expand-and-contract migrations, automated snapshot backups, rollback safety. |
| **Task 15** | **E2E Testing & Release Packaging** | Planned | Playwright UI suite, OWASP security audit, v1.0.0 release candidate. |

---

## 3. Technology Stack

```
┌────────────────────────────────────────────────────────┐
│                   Next.js 14 Frontend                  │
│       App Router • TypeScript • Tailwind CSS • shadcn   │
└───────────────────────────┬────────────────────────────┘
                            │ REST / JSON (Session + CSRF)
                            ▼
┌────────────────────────────────────────────────────────┐
│                   FastAPI Backend API                  │
│     Pydantic v2 • SQLAlchemy 2.0 (Async) • Alembic      │
├────────────────────────────┬───────────────────────────┤
│   Clinical Rules Engine    │   WhatsApp Adapter Engine │
│  - Sunday Closure (IST)    │  - Meta Cloud API v20.0   │
│  - Slot Concurrency Locks  │  - YCloud Integration     │
│  - RBAC Permission Matrix  │  - Fernet Crypto at Rest  │
└─────────────┬──────────────┴─────────────┬─────────────┘
              │                            │
              ▼                            ▼
┌────────────────────────────┐ ┌─────────────────────────┐
│     PostgreSQL 16 DB       │ │      Redis 7 Queue      │
│  - 34 Relational Entities  │ │  - Message Debouncing   │
│  - pgvector HNSW Indexes   │ │  - Celery Async Tasks   │
│  - btree_gist Exclusions   │ │  - Rate Limiting Cache  │
└────────────────────────────┘ └─────────────────────────┘
```

---

## 4. Key Architectural Invariants & Business Rules

1. **Strict Single-Organization Isolation**: Every database table directly represents Physio One. No `tenant_id` exists anywhere.
2. **Authoritative Sunday Restriction**: Physio One is strictly closed on Sundays.
   - Evaluated authoritatively in `AppointmentService` using the clinic's local timezone (`Asia/Kolkata` / UTC+05:30), irrespective of server timezone.
   - Enforced across creation and rescheduling via API, dashboard, and AI agent tool calling layers.
   - Backed by PostgreSQL table check constraint `chk_appointment_no_sunday`.
3. **Triple-Layer Concurrency Defense**:
   - Layer 1: In-process async slot locks (`_booking_locks`).
   - Layer 2: PostgreSQL transactional advisory locks (`pg_advisory_xact_lock`).
   - Layer 3: PostgreSQL `btree_gist` range exclusion constraint (`uq_no_overlapping_active_appointments`).
4. **Zero Physical Deletions**: Appointments, audit logs, and cancellation reasons are never physically deleted. Cancellations require a mandatory reason code and preserve full audit history.
5. **Least-Privilege RBAC**:
   - `Viewer`: Read-only access to appointments, logs, and settings.
   - `Operator`: Full appointment lifecycle operations, live chat, and patient lookup.
   - `Admin`: User management, connection configuration, system settings.
   - `Owner`: Primary clinic administrator with complete system governance.

---

## 5. Getting Started (Local Development)

### Prerequisites
- **Node.js**: v18.0.0+ (v20+ recommended)
- **Python**: 3.11+
- **Docker & Docker Compose** (Optional for local PostgreSQL/Redis; SQLite dev mode is supported out-of-the-box)

### Step 1: Clone Repository
```bash
git clone https://github.com/bhavarkar/Physio-One-WhatsApp.git
cd Physio-One-WhatsApp
git checkout development
```

### Step 2: Backend Setup
```bash
# Navigate to backend directory
cd backend

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows:
.\.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start backend development server (defaults to local SQLite if PostgreSQL is not running)
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
Interactive Swagger API documentation will be available at: **[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)**.

### Step 3: Frontend Setup
```bash
# Open a new terminal and navigate to frontend directory
cd frontend

# Install npm dependencies
npm install

# Start Next.js development server
npm run dev
```
Open your browser to: **[http://localhost:3000](http://localhost:3000)**.

### Step 4: First-Time Setup Wizard
1. On your first visit, navigate to **[http://localhost:3000/setup](http://localhost:3000/setup)** (or visit `/login` which will automatically redirect you).
2. Enter the clinic administrator's Full Name, Email, and Master Password.
3. Click **"Initialize Physio One System"**.
4. The system creates the initial **Owner** account and logs you directly into the dashboard.

---

## 6. Verification & Automated Testing

The repository maintains automated test suites across both backend and frontend.

```bash
# Run complete backend test suite (47 tests across database, auth, whatsapp, appointments)
.\backend\.venv\Scripts\python.exe -m pytest backend/tests -v

# Run frontend typecheck
cd frontend
npm run typecheck

# Run frontend Jest test suite (22 tests across 7 test suites)
npm test

# Dry-run Alembic migration SQL generation
.\backend\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head --sql
```

---

## 7. Project Documentation

Comprehensive architectural blueprints and technical specifications reside in the root directory:

- [ARCHITECTURE.md](ARCHITECTURE.md) — 17 modular subsystems (A through Q), sequence diagrams, and guardrails.
- [DATABASE.md](DATABASE.md) — Entity-relationship diagrams, table breakdown (34 entities), and migration protocols.
- [API.md](API.md) — REST API specification, request/response models, RBAC rules, and error schemas.
- [SECURITY.md](SECURITY.md) — Threat modeling, credential encryption at rest, session/CSRF defense, and audit logging.
- [ROADMAP.md](ROADMAP.md) — 15-phase task progression matrix and gate criteria.
- [CHANGELOG.md](CHANGELOG.md) — Keep-a-Changelog release notes organized by milestone.
- [DOCKER.md](DOCKER.md) — Multi-container containerization specification and volumes.
- [UPDATE.md](UPDATE.md) — Safe lifecycle update protocol and zero-downtime database migrations.
- [PRD.md](PRD.md) — Product Requirements Document and Ralph Loop task breakdown.

---

## 8. License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
