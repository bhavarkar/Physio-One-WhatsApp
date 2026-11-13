# DOCKER: Container Architecture & Deployment Guide (Single Organization Edition)

## 1. Container Topology
The platform runs as a coordinated suite of 6 isolated Docker containers managed via Docker Compose:

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

## 2. Service Specifications

| Container Name | Service Role | Base Image | Ports | Health Check Command |
| :--- | :--- | :--- | :--- | :--- |
| `frontend` | Dashboard UI (Next.js) | `node:20-alpine` | `3000:3000` | `wget --spider http://localhost:3000/api/health \|\| exit 1` |
| `api` | Inbound Ingress & REST API | `python:3.11-slim` | `8000:8000` | `curl -f http://localhost:8000/api/v1/health \|\| exit 1` |
| `worker` | Celery Background Worker | `python:3.11-slim` | None | `celery -A app.workers.celery inspect ping` |
| `scheduler` | Celery Beat Periodic Runner| `python:3.11-slim` | None | Process alive / PID check |
| `postgres` | Database with pgvector | `pgvector/pgvector:pg16` | `5432:5432` | `pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB` |
| `redis` | Broker, Debounce & Cache | `redis:7-alpine` | `6379:6379` | `redis-cli ping` |

---

## 3. Persistent Volumes
To guarantee data protection during container updates and system reboots:
1. `postgres_data`: Mounted to `/var/lib/postgresql/data` (relational records, vectors).
2. `redis_data`: Mounted to `/data` (Redis AOF persistence).
3. `media_storage`: Mounted to `/app/storage` (local media cache, voice note audio files).
4. `backups`: Mounted to `/backups` (automated pre-upgrade database snapshots).

> **CRITICAL RULE**: Persistent volume definitions must **never** be deleted or pruned during software updates.

---

## 4. Docker Compose Configurations

### A. Development (`docker-compose.yml`)
- Source code directories mounted as live volumes for hot-reloading (`./backend:/app`, `./frontend:/app`).
- Debug logging enabled.
- Default credentials pre-configured for local testing.

### B. Production (`docker-compose.prod.yml`)
- Multi-stage optimized Docker builds with non-root user execution (`USER appuser`).
- Resource limits configured (`cpus`, `memory`).
- Restart policies set to `always`.
- SSL/TLS terminated via reverse proxy (Caddy / Nginx / Cloudflare).

---

## 5. Multi-Platform Deployment Blueprints

### Blueprint A: Single Dedicated VPS (Recommended Baseline)
- Standard Ubuntu 22.04 / 24.04 LTS VPS (4 vCPUs, 8GB RAM, 50GB NVMe SSD).
- Docker Engine + Docker Compose Plugin installed.
- One-command startup:
  ```bash
  docker compose -f docker-compose.prod.yml up -d
  ```

### Blueprint B: Google Cloud Run Deployment
- `frontend` container deployed to Cloud Run (Serverless Next.js).
- `api` container deployed to Cloud Run (FastAPI).
- Managed Cloud SQL for PostgreSQL 16 (with `pgvector` flag enabled).
- Managed Memorystore for Redis.
- Background worker and beat scheduler deployed on Cloud Run Jobs or a persistent Google Compute Engine micro-instance.

### Blueprint C: Hybrid Cloud (Vercel / Netlify + Cloud Run)
- Frontend deployed to Vercel or Netlify.
- Backend API and Celery workers hosted on Cloud Run / VPS.
- Cross-Origin Resource Sharing (CORS) restricted strictly to the verified frontend domain.
