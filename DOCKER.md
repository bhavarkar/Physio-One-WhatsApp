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
- **Verification status**: Verified and operational.

---

## 6. Task 15 — Docker Security Hardening & Execution Status (2026-11-17)

- **PostgreSQL Localhost Binding**:
  - `docker-compose.yml` updated from `"${POSTGRES_PORT:-5432}:5432"` to `"127.0.0.1:${POSTGRES_PORT:-5432}:5432"`.
  - Prevents exposing the database port on public or local network interfaces (`0.0.0.0`).
- **Non-Root Execution**:
  - `Dockerfile.api`: runs as `USER appuser`.
  - `Dockerfile.frontend`: runs as `USER nextjs`.
- **Live Stack Status**:
  - 4 services active and healthy: `physio_postgres` (pgvector:pg16), `physio_api`, `physio_worker`, `physio_frontend`.
  - One-shot `physio_migration` verified with exit code 0.

---

## 7. Task 20 — Hostinger VPS Standalone Docker Compose Stack (`deploy/vps/compose.yaml`)

- Multi-container topology for greenfield VPS deployments: `caddy`, `api`, `worker`, `frontend`, `postgres`, `migration`.
- PostgreSQL port 5432 has zero host port mappings.
- Total container memory limits capped at 2.4 GB out of 4.0 GB host RAM.

---

## 8. Task 23 — Hostinger KVM 1 Coexistence Stack (`deploy/vps/compose.hostinger.yaml`)

- Engineered for VPS environments with pre-existing host Nginx and host PostgreSQL 16 (e.g. running alongside `n8n.dataagent.in`).
- **No Caddy Container**: Ingress handled by host Nginx.
- **Strict Loopback Bindings**:
  - API: `127.0.0.1:8000:8000`
  - Frontend: `127.0.0.1:3000:3000`
  - Prevents Docker from manipulating iptables and exposing ports on `0.0.0.0`.
- **Host Gateway Networking**:
  - Uses `extra_hosts: ["host.docker.internal:host-gateway"]` to connect directly to host PostgreSQL 16 at `host.docker.internal:5432`.
- **Resource Constraints (1 vCPU, 4 GB RAM)**:
  - API: 400 MB limit, 0.50 CPU limit.
  - Worker: 350 MB limit, 0.30 CPU limit.
  - Frontend: 350 MB limit, 0.40 CPU limit.
  - Total container limits: 1,100 MB (~1.1 GB).
- **Optional Containerized DB Profile**: Includes `postgres` service with profile `container-db` as a zero-host-port container fallback.

