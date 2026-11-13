# CHANGELOG: WhatsApp AI Agent (Single Organization Edition)

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0-draft] - 2026-11-13

### Added
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
