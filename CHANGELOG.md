# CHANGELOG: WhatsApp AI Agent (Single Organization Edition)

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0-draft] - 2026-11-13

### Added
- **Task 5: WhatsApp Provider Integration (Meta Cloud API & YCloud)**:
  - Implemented common internal provider contract `WhatsAppProvider` in `backend/app/providers/base.py` defining standardized methods: `validate_connection()`, `send_text_message()`, `send_template_message()`, `send_media_message()`, `verify_webhook_signature()`, `parse_inbound_webhook()`, and `parse_status_update()`.
  - Implemented `MetaCloudProvider` adapter (`backend/app/providers/meta.py`) targeting official Meta WhatsApp Cloud API (Graph API v20.0) with support for text, media, interactive messages, `hub.challenge` verification, and `X-Hub-Signature-256` HMAC-SHA256 signature validation.
  - Implemented `YCloudProvider` adapter (`backend/app/providers/ycloud.py`) preserving existing Physio One clinical operations with `X-API-Key` headers, `YCloud-Signature` HMAC-SHA256 signature validation, and normalized inbound/status payload parsing.
  - Implemented provider factory `get_provider_adapter(account)` resolving accounts, decrypting stored credentials on-the-fly, and instantiating appropriate provider adapters.
  - Implemented symmetric credential encryption via Fernet (AES-128-CBC + HMAC-SHA256) in `backend/app/core/crypto.py` with deterministic SHA-256 key derivation from application secret. Zero plaintext credentials at rest or in API schemas.
  - Created durable webhook ingestion and processing service (`WhatsAppMessagingService`) in `backend/app/services/whatsapp_service.py` with idempotency deduplication in `webhook_events`, automatic contact & conversation upserting, outbound dispatch, and delivery status tracking (`sent` -> `delivered` -> `read` / `failed`).
  - Implemented RBAC-protected connection management API (`/api/v1/whatsapp/connections`) for Owner/Admin roles with test handshake and test dispatch endpoints.
  - Implemented public webhook receivers under `/api/v1/webhooks/whatsapp/meta` (GET subscription challenge + POST event ingestion) and `/api/v1/webhooks/whatsapp/ycloud` (POST event ingestion).
  - Built comprehensive frontend WhatsApp connection management dashboard under `/settings` with Meta vs YCloud badges, handshake verification, live test message modal, activation toggles, and masked credential displays.
  - Implemented automated test suite with 10 unit and integration tests in `backend/tests/test_whatsapp_provider.py` (33/33 backend tests passing total).
  - Implemented frontend unit tests in `frontend/src/app/(dashboard)/settings/settings.test.tsx` (6/6 test suites, 19/19 tests passing).

- **Task 4: Frontend Foundation and Authentication UI**:
  - Implemented Next.js 14 App Router application structure in `frontend/` with TypeScript strict mode and Tailwind CSS.
  - Designed clinical SaaS theme tokens and built reusable UI component library: `Button`, `Input`, `Card`, `Badge`, `Alert`, `Dialog`, and `Table`.
  - Built centralized typed API client (`api-client.ts`) enforcing `credentials: 'include'` for HttpOnly cookies and double-submit `X-CSRF-Token` header injection on state-mutating requests (`POST`, `PUT`, `PATCH`, `DELETE`).
  - Implemented React `AuthProvider` with automatic backend session verification via `/api/v1/auth/me`.
  - Created Staff Sign In (`/login`) with password visibility toggle, client validation, disabled state during submission, and generic error messaging.
  - Implemented Initial Administrator Setup Wizard (`/setup`) with automatic redirect from login when uninitialized, and access lock when initialized.
  - Implemented Password Reset Notice (`/forgot-password`) adhering to clinical PHI security standards.
  - Created responsive application shell layout (`(dashboard)/layout.tsx`) with brand navigation, mobile drawer, user profile mini-card, and role-based route visibility.
  - Created Clinical Operations Overview dashboard (`/dashboard`) with non-operational placeholder cards for upcoming pipeline stages.
  - Built Staff Profile & Security management (`/profile`) with password change form and active session viewer/revocation controls.
  - Built Staff User Management interface (`/users`) with search, role-based creation modal, Admin privilege escalation prevention (disabling Owner role creation), account deactivation/reactivation confirmation modals, and session revocation controls.
  - Created multi-stage `docker/Dockerfile.frontend` and integrated `frontend` container service into `docker-compose.yml`.
  - Automated Jest test suite covering API client, login, setup wizard, role-based layout navigation, and user management (16/16 tests passing, 100% pass rate).
  - Next.js production build verified (`npm run build` outputting 16 static routes with 0 errors).

- **Task 3: Authentication, RBAC, and User Management API**:
  - Implemented secure password hashing via Argon2id with automatic resilient fallback to Python standard library `hashlib.scrypt` when environment policies restrict native C-extensions.
  - Implemented controlled initial system setup flow (`GET /api/v1/auth/setup-status`, `POST /api/v1/auth/setup`) enforcing one-time initialization of the primary Owner.
  - Built secure session management with SHA-256 session token hashing, HttpOnly/Secure/SameSite cookie issuance, optional Bearer header support, and active session listing/revocation.
  - Implemented CSRF defense for cookie-based state-changing requests using double-submit CSRF cookie & `X-CSRF-Token` headers.
  - Implemented in-memory brute-force rate limiter (`LoginRateLimiter`) with IP-based exponential backoff/lockout and generic authentication error messages.
  - Implemented explicit 4-tier Role-Based Access Control matrix (`Owner`, `Admin`, `Operator`, `Viewer`) with granular permission dependencies and authorization decorators.
  - Built User Management REST API (`/api/v1/users`) supporting listing, creation, updates, activation/deactivation, password resets, and session revocations.
  - Enforced critical security invariants: last active Owner protection, strict privilege escalation prevention, self-deactivation prevention, and disabled user session rejection.
  - Structured security audit logging via `audit_logs` table recording all authentication, user modifications, and permission checks with sensitive field redaction.
  - Comprehensive automated test suite with 10 async test scenarios in `backend/tests/test_auth_rbac.py` achieving 100% pass rate (23/23 tests passed total across database and auth).

- **Task 2: Database Schema & Alembic Migrations**:
  - Implemented 33 SQLAlchemy 2.0 models across 8 domain modules (zero `tenant_id` columns).
  - Added dual WhatsApp provider support (Meta WhatsApp Cloud API and YCloud) with encrypted credential storage.
  - Implemented webhook deduplication (`webhook_events`) and provider message deduplication (`whatsapp_messages`).
  - Implemented `pgvector` vector embeddings (`vector(1536)`) and HNSW cosine similarity index definitions for semantic memory and knowledge chunks.
  - Configured Alembic migration environment and generated initial migration `001_initial_schema.py` enabling pgvector extension and building all 33 tables.
  - Created automated test suite with 13 comprehensive tests in `backend/tests/test_database.py` (100% pass rate).
  - Configured `docker-compose.yml` with `pgvector/pgvector:pg16`, `redis:7-alpine`, and one-shot migration runner.
  - Scaffolding `docker/Dockerfile.api` with multi-stage build.

- **Task 1: Architecture Specification & Scaffolding**:
  - Initialized git repository on branch `main` and branched to `development`.
  - Comprehensive architectural blueprint in `ARCHITECTURE.md` detailing all 17 independent subsystems (A through Q).
  - Database schema specification in `DATABASE.md` detailing 30 single-organization entities, UUID keys, and `pgvector` index designs.
  - REST API specification in `API.md` covering authentication, WhatsApp webhook, live inbox, appointments, AI tools, and updates.
  - Containerization blueprint in `DOCKER.md` with multi-container topology (`frontend`, `api`, `worker`, `scheduler`, `postgres`, `redis`).
  - Safe lifecycle and update protocol in `UPDATE.md` with expand-and-contract migration rules and automated backup verification.
  - Phased development roadmap in `ROADMAP.md` covering 13 development phases.
  - Threat modeling and data security guidelines in `SECURITY.md`.
  - Directory layout scaffolding for backend (`core`, `api`, `models`, `schemas`, `services`, `agents`, `tools`, `workers`), frontend (`src`), docker, scripts, and docs.
  - Ralph Loop configuration with `PRD.md`, `progress.txt`, and `prompt.md`.
  - Centralized version manifest `version.json` and template configuration `.env.example`.
