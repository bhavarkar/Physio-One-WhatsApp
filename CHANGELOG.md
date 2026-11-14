# CHANGELOG: WhatsApp AI Agent (Single Organization Edition)

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0-draft] - 2026-11-14

### Added
- **Task 9: Inbound WhatsApp AI Receptionist (Deepti) Conversation Orchestration**:
  - Authored Alembic migration `005_inbound_ai_orchestration.py` establishing 5 new database tables: `inbound_processing_jobs`, `ai_inbound_settings`, `conversation_handoffs`, `ai_response_drafts`, and `outbound_idempotency_keys` with foreign keys and compound performance indexes (total database tables: 43).
  - Built durable PostgreSQL message queue & debouncer `InboundQueueService` (`backend/app/services/inbound_queue.py`) aggregating rapid patient burst messages within configurable debounce window (default 5s) into a single conversational turn with worker row-locking.
  - Implemented `InboundOrchestrator` (`backend/app/services/inbound_orchestrator.py`) with strict multi-layer safety guardrails:
    - **MANDATORY DEFAULT AI MODE**: Strictly `disabled`. `shadow` and `live` require explicit authorized activation.
    - **Opt-Out Safety**: Case-insensitive keyword detection (STOP, UNSUBSCRIBE, CANCEL MESSAGES) automatically sets `contact.opted_out_all = True`, logs an immutable `ConversationHandoff` audit record, and completely suppresses automated replies.
    - **Emergency Safety**: Emergency keyword detection (emergency, ambulance, severe pain, bleeding, chest pain, unconscious) immediately sets `conversation.is_human_takeover = True`, logs handoff audit event, and drafts emergency hospital guidance (112).
    - **Human Takeover & AI Pause Enforcement**: Conversations with `is_human_takeover=True` or `ai_paused=True` immediately suppress AI processing.
    - **Deepti Agent Runtime Execution**: Integrates conversation history, isolated patient memory, approved clinic RAG knowledge context, and read-only clinical tools (`check_availability` with strict Sunday closure and 09:00 - 20:00 IST operating hours via authoritative `AppointmentService`).
    - **Shadow Mode Drafting**: Generates and persists full AI responses in `ai_response_drafts` for clinic staff review without sending ANY outbound messages to WhatsApp.
    - **Live Mode Dispatch**: Only when explicitly activated, dispatches responses through `OutboundDispatcher`.
  - Implemented `OutboundDispatcher` (`backend/app/services/outbound_dispatcher.py`) enforcing pre-dispatch state re-verification, once-and-only-once delivery via `OutboundIdempotencyKey`, and safe error logging on uncertain provider outcomes to prevent duplicate patient messaging.
  - Integrated inbound message persistence with queueing in `whatsapp_service.py` (`process_incoming_webhook`).
  - Built typed Pydantic schemas (`backend/app/schemas/inbound.py`) for live inbox conversations, messages, drafts, handoffs, and settings.
  - Implemented authenticated REST API endpoints:
    - `backend/app/api/v1/conversations.py`: `GET /api/v1/conversations`, `GET /api/v1/conversations/{id}`, `POST /api/v1/conversations/{id}/reply`, `POST /api/v1/conversations/{id}/takeover`, `POST /api/v1/conversations/{id}/pause-ai`, `POST /api/v1/conversations/{id}/resume-ai`.
    - `backend/app/api/v1/ai_inbound.py`: `GET /api/v1/ai-inbound/settings`, `PATCH /api/v1/ai-inbound/settings` (Owner/Admin only with audit logging), `POST /api/v1/ai-inbound/process-due`, `GET /api/v1/ai-inbound/drafts`.
    - Mounted routers in `backend/app/main.py`.
  - Built frontend typed API client methods in `frontend/src/lib/api-client.ts`.
  - Built full interactive Live Inbox dashboard (`frontend/src/app/(dashboard)/inbox/page.tsx`) with real-time conversations list, unread/draft badges, chat timeline, AI shadow draft viewer with "Use this Draft" shortcut, staff manual reply box with automatic takeover toggle, takeover/pause/resume action buttons, and AI Receptionist Settings modal (Disabled / Shadow / Live).
  - Created automated backend test suite `backend/tests/test_inbound_orchestration.py` (8 integration tests covering debouncing, disabled default, shadow drafting, live dispatch & idempotency, opt-out suppression, emergency takeover, takeover/pause suppression, and API operations) — total backend regression suite: 96/96 passing (100%).
  - Created frontend test suite `frontend/src/app/(dashboard)/inbox/inbox.test.tsx` (6 tests covering rendering, timeline, manual reply, takeover/pause, AI settings modal, and opt-out disabling) — total frontend suite: 36/36 passing across 10 suites (100%).
  - Clean TypeScript verification with zero errors (`tsc --noEmit`).

- **Task 8: pgvector Memory, Clinic Knowledge Base & Semantic Retrieval (RAG)**:
  - Authored Alembic migration `004_knowledge_base_pgvector_rag.py` establishing pgvector extension, adding document ingestion metadata (`source_hash`, `file_type`, `file_size_bytes`, `version`), chunk metadata, `ai_retrieval_logs` audit table, `AIAgent` RAG settings (`knowledge_base_id`, `rag_enabled`, `rag_similarity_threshold`, `rag_top_k`), and pgvector HNSW cosine index `ix_knowledge_chunks_embedding_hnsw` (total database tables: 38).
  - Built provider-independent embedding abstraction: `BaseEmbeddingProvider`, `EmbeddingError`, `EmbeddingDimensionMismatchError`, and `OpenAIEmbeddingProvider` targeting `text-embedding-3-small` (1536 dimensions) with batching and error normalization.
  - Implemented `DeterministicEmbeddingProvider` for offline development and testing with strict production guardrails (raises `EmbeddingError` if `ENVIRONMENT=production` to prevent mock vectors from serving production queries).
  - Built `DocumentProcessor` (`backend/app/services/document_processor.py`) supporting PDF, DOCX, TXT, and Markdown with zero external binary dependencies, magic byte verification, 10MB limit, text extraction, normalization, and chunking with configurable size and overlap.
  - Implemented `KnowledgeService` (`backend/app/services/knowledge_service.py`) for collection CRUD, document ingestion, duplicate prevention via SHA-256 hash, reprocessing, archival, deletion, and physical file cleanup.
  - Implemented `RetrievalService` (`backend/app/services/retrieval_service.py`) for semantic cosine similarity search, threshold filtering, active document enforcement, latency tracking in `ai_retrieval_logs`, and boundary-guarded RAG prompt staging defending against prompt injection.
  - Implemented `MemoryService` (`backend/app/services/memory_service.py`) managing short-term chronological WhatsApp conversation turns (max 10 messages, 4000 char budget) and persistent patient memories strictly isolated by `contact_id`.
  - Implemented `SearchClinicKnowledgeTool` (`backend/app/tools/clinical/knowledge.py`) registered in `ToolRegistry` with caller permission gates (`knowledge:read`).
  - Integrated RAG retrieval context and patient memory context into `AgentRuntime` (`backend/app/agents/runtime.py`).
  - Built authenticated REST API routes (`backend/app/api/v1/knowledge.py`) mounted under `/api/v1/knowledge`: `/bases`, `/bases/{id}`, `/documents/upload`, `/documents/{id}/reprocess`, `/documents/{id}/archive`, `/documents/{id}`, `/search`, `/test-retrieval`, and `/contacts/{id}/memories`.
  - Built frontend typed API client methods in `frontend/src/lib/api-client.ts`.
  - Built complete interactive Knowledge Base dashboard (`frontend/src/app/(dashboard)/knowledge/page.tsx`) with collection switcher, document management table with status badges (`ready`, `processing`, `failed`, `archived`), upload modal with chunking options, and interactive RAG retrieval test console with latency and similarity indicators.
  - Added Knowledge Base link to sidebar navigation (`frontend/src/app/(dashboard)/layout.tsx`) and added Knowledge Base assignment with RAG parameters to Agent modals (`frontend/src/app/(dashboard)/agents/page.tsx`).
  - Created automated backend test suites: `test_document_processor.py` (4 tests), `test_embeddings.py` (7 tests), `test_knowledge_service.py` (2 tests), `test_retrieval_and_rag.py` (3 tests), `test_memory_service.py` (2 tests), `test_knowledge_api.py` (2 tests) — total backend regression suite: 88/88 passing (100%).
  - Added frontend test suite `frontend/src/app/(dashboard)/knowledge/knowledge.test.tsx` (5 tests) — total frontend suite: 30/30 passing across 9 suites (100%).
  - Clean TypeScript check with zero errors (`tsc --noEmit`).

- **Task 7: Multi-Provider LLM Gateway & Agent Runtime**:
  - Implemented Alembic migration `003_ai_agent_sessions_and_usage.py` creating `ai_agent_sessions`, `ai_agent_executions`, `llm_usage_logs` and altering `ai_providers`, `ai_agents`, `ai_agent_versions`, and `ai_tool_executions` (total database tables: 37).
  - Built typed Pydantic schemas (`backend/app/llm/schemas.py`) for unified LLM interactions: `ChatMessage`, `MessageRole`, `ToolCall`, `ToolDefinition`, `LLMOptions`, `LLMUsage`, `LLMResponse`, `LLMStreamChunk`, and `ProviderCapabilities`.
  - Implemented typed exception hierarchy (`backend/app/llm/errors.py`) with retryable error classification (`LLMError`, `LLMAuthenticationError`, `LLMRateLimitError`, `LLMTimeoutError`, `LLMServiceUnavailableError`, `LLMConfigurationError`, `LLMUnsupportedCapabilityError`).
  - Created provider-agnostic base adapter contract `BaseLLMProvider` (`backend/app/llm/base.py`) standardizing `generate()`, `stream()`, `validate_connection()`, `mask_api_key()`, and `normalize_error()`.
  - Implemented `MuseProvider` (`backend/app/llm/providers/muse.py`) as the primary gateway integration with Bearer authentication, configurable base URL, and strict capability reporting (`supports_tools=False`, `supports_streaming=False` with diagnostic feedback identifying unverified proprietary schemas per verified documentation).
  - Implemented `OpenAIProvider` (`backend/app/llm/providers/openai.py`) with tool-calling schema translation, structured JSON output, streaming, and error normalization.
  - Implemented `AnthropicProvider` (`backend/app/llm/providers/anthropic.py`) with Anthropic Messages API format, top-level system prompt isolation, and `tool_use` / `tool_result` translation.
  - Implemented `GenericOpenAIProvider` (`backend/app/llm/providers/generic_openai.py`) for local and self-hosted models (Ollama, vLLM, LocalAI).
  - Built unified `LLMGateway` (`backend/app/llm/gateway.py`) resolving provider adapters, decrypting stored credentials via Fernet, managing resilient fallback chains (disabled by default, retryable errors only, forbidden on mutating tool steps), and recording token and cost accounting in `llm_usage_logs`.
  - Built extensible tool-calling infrastructure: `BaseTool` (`backend/app/tools/base.py`), `ToolRegistry` (`backend/app/tools/registry.py`), and `ToolDispatcher` (`backend/app/tools/dispatcher.py`) enforcing agent whitelist, timeout safeguards, and execution auditing in `ai_tool_executions`.
  - Implemented clinical tools: `CheckAvailabilityTool` (`backend/app/tools/clinical/availability.py`) querying `AppointmentService.get_daily_availability` (strictly enforcing Sunday closure, operating hours, and active slot conflicts) and `FindPatientTool` (`backend/app/tools/clinical/patient.py`) with PHI phone masking.
  - Implemented `AgentRuntime` (`backend/app/agents/runtime.py`) featuring deterministic context assembly (preserving system instructions and user message while truncating historical turns to context token budget), multi-step tool execution loop with max-step and timeout guards, and session state transitions (`pending`, `running`, `completed`, `failed`).
  - Implemented `AgentService` (`backend/app/services/agent_service.py`) with startup initialization of default AI entities (seeding `muse`, `openai`, `anthropic`, `generic_openai`, models, tools, and the draft **Deepti** receptionist agent v1), provider configuration management, agent CRUD with immutable version snapshots, and isolated test console execution.
  - Built REST API routers mounted in `backend/app/main.py`:
    - `/api/v1/llm`: Provider management, diagnostic connection test, active model listing with pricing.
    - `/api/v1/agents`: Agent CRUD, immutable version history snapshots, execution session logs, and isolated test execution.
    - `/api/v1/tools`: Registered tool schema catalog.
  - Built frontend typed API client methods in `frontend/src/lib/api-client.ts`.
  - Built complete interactive AI Agent management dashboard (`frontend/src/app/(dashboard)/agents/page.tsx`) with agent cards, Deepti badge, create/edit modals, system prompt editor, version history modal, execution sessions log, and isolated test console with metrics and tool inspector.
  - Enhanced settings dashboard (`frontend/src/app/(dashboard)/settings/page.tsx`) with tabbed switcher between WhatsApp Integrations and LLM Gateway Providers (viewing provider health, masked keys, models, connection test diagnostics, and configure modal) while preserving 100% of existing WhatsApp UI and tests.
  - Added comprehensive backend test suites: `backend/tests/test_llm_gateway.py` (9 tests), `backend/tests/test_agent_runtime.py` (8 tests), `backend/tests/test_ai_api.py` (4 tests) — total backend suite: 68/68 passing (100%).
  - Added frontend test suite `frontend/src/app/(dashboard)/agents/agents.test.tsx` (3 tests) — total frontend suite: 25/25 passing across 8 suites (100%).
  - Clean TypeScript check with zero errors (`tsc --noEmit`).

- **Task 6: Clinical Appointments Engine & Availability Rules**:
  - Implemented `AppointmentHistory` SQLAlchemy model (`backend/app/models/patient.py`) for comprehensive chronological tracking of appointment lifecycle events (`created`, `rescheduled`, `cancelled`, `completed`, `no_show`, `updated`).
  - Extended `Appointment` model with `duration_minutes` (default 45), `created_by_id`, and `updated_by_id` audit foreign keys.
  - Authored Alembic migration `002_appointment_history_and_rules.py` with SQL CHECK constraint `chk_appointment_no_sunday` and PostgreSQL `btree_gist` range exclusion constraint `uq_no_overlapping_active_appointments` preventing concurrent/overlapping active bookings.
  - Implemented Pydantic v2 schemas (`backend/app/schemas/appointment.py`) including `TimeSlot`, `AvailabilityResponse`, `AppointmentCreate`, `AppointmentUpdate`, `AppointmentRescheduleRequest`, `AppointmentCancelRequest`, `AppointmentActionRequest`, and `AppointmentResponse`.
  - Built dedicated `AppointmentService` (`backend/app/services/appointment_service.py`) with:
    - Authoritative Sunday closure enforcement in clinic business timezone (`Asia/Kolkata` / UTC+05:30 with Windows compatibility fallback).
    - Operating hours validation (09:00 - 20:00 IST) and 30-minute slot generation excluding past slots and active booking conflicts.
    - Double-booking prevention via in-process async locks, PostgreSQL transactional advisory locks, and DB range exclusion constraints.
    - Complete lifecycle operations (`create_appointment`, `reschedule_appointment`, `cancel_appointment`, `complete_appointment`, `mark_no_show`, `update_appointment`, `get_appointment`, `list_appointments`).
    - Automatic patient record lookup/creation by contact phone number.
    - Synchronized dual audit logging to `audit_logs` and `appointment_history`.
  - Built REST API routes under `/api/v1/appointments` with structured business error mapping (`SUNDAY_RESTRICTION`, `OPERATING_HOURS_VIOLATION`, `PAST_APPOINTMENT`, `APPOINTMENT_CONFLICT`, `INVALID_STATUS_TRANSITION`) and least-privilege RBAC permission gates (`appointments:read`, `appointments:create`, `appointments:update`, `appointments:cancel`, `appointments:complete`, `appointments:no_show`).
  - Added frontend typed client methods and interfaces in `frontend/src/lib/api-client.ts`.
  - Built complete interactive appointment management dashboard (`frontend/src/app/(dashboard)/appointments/page.tsx`) with date filtering, status filtering, search, Sunday restriction banner, slot-picker booking dialog, reschedule modal, cancellation reason modal, completion & no-show actions, full audit timeline modal, and Viewer read-only restrictions.
  - Created automated backend test suite (`backend/tests/test_appointments.py`) with 14 async scenarios covering availability, Sunday restrictions, overlap prevention, rescheduling, cancellation, completion, no-show, concurrency (`asyncio.gather`), CSRF validation, and RBAC permissions (47/47 backend tests passing).
  - Created frontend test suite (`frontend/src/app/(dashboard)/appointments/appointments.test.tsx`) with Jest (22/22 frontend tests passing across 7 suites).

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
