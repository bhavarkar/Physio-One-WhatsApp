# DOCKER: Container Architecture & Deployment Guide (Single Organization Edition)

## 1. Container Topology
The platform runs as a coordinated suite of isolated Docker containers managed via Docker Compose:

```
[ Internet ]
      │
      ▼
┌──────────────┐     ┌──────────────┐
│  frontend    │     │  backend-api │
│ (Next.js 14) │◄───►│  (FastAPI)   │
│  Port 3000   │     │  Port 8000   │
└──────────────┘     └──────┬───────┘
                            │
               ┌────────────┼────────────┐
               │            │            │
               ▼            ▼            ▼
        ┌─────────────┐ ┌──────────┐ ┌───────────┐
        │   celery-   │ │ celery-  │ │ postgres- │
        │   worker    │ │   beat   │ │  pgvector │
        └──────┬──────┘ └────┬─────┘ └─────┬─────┘
               │             │             │
               └──────┬──────┘             │
                      ▼                    │
               ┌─────────────┐             │
               │   redis-7   │◄────────────┘
               └─────────────┘
```

---

## 2. Implemented Docker Compose Configuration (`docker-compose.yml`)

| Container Name | Service Role | Image / Dockerfile | Ports | Health Check Command |
| :--- | :--- | :--- | :--- | :--- |
| `postgres` | Database with pgvector | `pgvector/pgvector:pg16` | `5432:5432` | `pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB` |
| `redis` | Broker, Debounce & Cache | `redis:7-alpine` | `6379:6379` | `redis-cli ping` |
| `migration` | One-shot Alembic runner | `docker/Dockerfile.api` | None | Service completes successfully (`alembic upgrade head`) |
| `api` | Inbound Ingress & REST API | `docker/Dockerfile.api` | `8000:8000` | Process / health check |
| `worker` | Background Automation & Campaign Daemon | `docker/Dockerfile.api` | None | Continuous cycle via `python -m app.workers.runner` |
| `frontend` | Next.js 14 Web Console | `docker/Dockerfile.frontend` | `3000:3000` | HTTP GET `/api/v1/auth/setup-status` proxy check |

---

## 3. Persistent Volumes
To guarantee data protection during container updates and system reboots:
1. `postgres_data`: Mounted to `/var/lib/postgresql/data` (relational records, vectors).
2. `redis_data`: Mounted to `/data` (Redis AOF persistence).
3. `media_storage`: Mounted to `/app/storage` (local media cache, voice note audio files).

> **CRITICAL RULE**: Persistent volume definitions must **never** be deleted or pruned during software updates.

---

## 4. Local Startup & Migration Instructions

```bash
# 1. Start database and cache services
docker compose up -d postgres redis

# 2. Run database migrations explicitly via container
docker compose run --rm migration

# 3. Start full application stack
docker compose up -d
```

---

## 5. Task 14 Verification Notes (2026-11-15)

- **Redis removed**: audit found zero application references to Redis/Celery (only unused config constants). Compose no longer provisions Redis; durable jobs are PostgreSQL-backed. Do not re-add without code that uses it.
- **Worker**: local Compose runs the polling daemon (acceptable locally). Cloud Run must use Scheduler/Tasks -> worker HTTP endpoints or the Cloud Run Job `python -m app.workers.runner --once`. Never deploy the polling loop as a Cloud Run service.
- **Images**: API honours `$PORT` (Cloud Run), runs non-root; frontend uses `npm ci` with the committed lockfile.
- **Verification status**: Docker daemon execution was not confirmed in this session (see PRODUCTION_READINESS.md scorecard); rerun: `docker compose config && docker compose build && docker compose up -d && docker compose ps`, then `python scripts/verify_postgres.py` against a disposable `*_verify` database.
