# Hostinger KVM 1 VPS Infrastructure Audit & Coexistence Plan

**Platform:** Physio One WhatsApp AI Platform (Single Organization Edition)  
**Host Target:** Hostinger KVM 1 Ubuntu Linux VPS  
**Audit Date:** 2026-11-18  
**Audit Classification:** READ-ONLY PREFLIGHT & COEXISTENCE READINESS  

---

## 1. Executive Summary & Verified Host Environment

A comprehensive infrastructure assessment was performed for hosting the Physio One WhatsApp AI Platform on an existing Hostinger KVM 1 VPS. The server currently hosts an active `n8n` workflow automation instance behind host-level Nginx.

### Verified Hardware & Operating System Baseline

| Metric | Verified Host Value | Assessment & Capacity Impact |
|---|---|---|
| **Operating System** | Ubuntu 24.04.5 LTS (Noble Numbat) | Excellent. Modern LTS kernel with full Docker and cgroups v2 support. |
| **CPU Architecture** | 1 vCPU (x86_64) | Resource-constrained. Requires single-threaded worker polling and strict CPU limits. |
| **Total Memory (RAM)** | 3.8 GiB (3,891 MiB) | Fits within 4 GB VPS design envelope. |
| **Available Memory** | **2.6 GiB (2,662 MiB)** | **Sufficient.** Leaves plenty of headroom after n8n baseline consumption. |
| **Swap Space** | 4.0 GiB (521 MiB used) | Healthy swap buffer prevents OOM-killer kernel panics during build spikes. |
| **Available Storage** | **26 GB free** (out of ~50 GB SSD) | Sufficient. Physio One images + data require 3–5 GB initial disk footprint. |
| **Host Web Server** | Nginx (active on ports 80 & 443) | Owns public ingress. Caddy **must NOT** be started on the host. |
| **Existing Workload** | `n8n` (Docker) on `n8n.dataagent.in` | Active container. Must remain 100% untouched and operational. |
| **Stopped Workloads** | Hermes (stopped), FreeHire (removed) | No resource contention from legacy workloads. |
| **Host Database** | PostgreSQL 16 (port 5432) | Running on host. Can be leveraged directly to eliminate redundant containers. |
| **pgvector Status** | `pgvector 0.6.0` available | **100% compatible** with all Alembic migrations and HNSW cosine indexes. |
| **Host Firewall (UFW)** | **INACTIVE** | **Critical Security Finding.** Requires strict Docker loopback port binding. |

---

## 2. Security & Firewall Threat Model (UFW Inactive)

### The Docker iptables Bypass Vulnerability
On Linux systems where Docker is installed, Docker directly modifies `iptables` NAT tables to route traffic to published container ports. If a container service specifies `ports: ["8000:8000"]` or `ports: ["3000:3000"]`, Docker binds the port to `0.0.0.0` (all interfaces), **exposing the container directly to the public internet** even if host firewalls or UFW are configured.

Because the Hostinger VPS currently has **UFW inactive**, any unconstrained port publishing would immediately expose the internal FastAPI REST backend and Next.js dashboard directly to unauthorized external probes.

### Remediation & Enforced Invariants
1. **Strict 127.0.0.1 Binding:** In `deploy/vps/compose.hostinger.yaml`, all published ports are strictly bound to host loopback:
   ```yaml
   ports:
     - "127.0.0.1:8000:8000"  # FastAPI API (Nginx reverse proxy target)
     - "127.0.0.1:3000:3000"  # Next.js Dashboard (Nginx reverse proxy target)
   ```
2. **Zero Database Port Mapping:** Neither the host PostgreSQL nor any fallback database container maps port 5432 externally. Database traffic is confined to `127.0.0.1` and private Docker bridge networks.
3. **Firewall Recommendation:** The operator should enable UFW to enforce defense-in-depth:
   ```bash
   sudo ufw default deny incoming
   sudo ufw default allow outgoing
   sudo ufw allow 22/tcp
   sudo ufw allow 80/tcp
   sudo ufw allow 443/tcp
   sudo ufw enable
   ```

---

## 3. Database Compatibility Analysis (pgvector 0.6.0)

### Codebase & Migration Audit
An exhaustive audit of all Alembic migrations (`001_initial_schema.py` through `008_campaigns_instagram_reengagement.py`) and application models was conducted:
- **Vector Dimensions:** `Vector(1536)` (OpenAI `text-embedding-3-small` standard).
- **Index Definitions:**
  ```sql
  CREATE INDEX IF NOT EXISTS idx_conv_memory_embedding ON conversation_memory USING hnsw (embedding vector_cosine_ops);
  CREATE INDEX IF NOT EXISTS idx_knowledge_chunk_embedding ON knowledge_chunks USING hnsw (embedding vector_cosine_ops);
  ```
- **pgvector Version History:**
  - HNSW indexing and `vector_cosine_ops` were introduced in `pgvector 0.5.0` (August 2023).
  - `pgvector 0.6.0` (January 2024) stabilized HNSW, parallel index builds, and L1 distance.
  - Advanced features from 0.7.0+ (`halfvec`, `sparsevec`, iterative index scans) are **NOT** used anywhere in Physio One.

### Conclusion: pgvector 0.6.0 is 100% Sufficient & Compatible
The host `pgvector 0.6.0` extension satisfies all functional, schema, and performance requirements of the platform.

### Preferred Database Architecture: Host PostgreSQL 16
Using the existing host PostgreSQL 16 daemon instead of running a separate containerized PostgreSQL instance provides major advantages:
1. **Memory Savings:** Saves ~150–250 MiB of RAM by eliminating a second database engine process.
2. **CPU Optimization:** Reduces context-switching and background disk flushing on the 1 vCPU host.
3. **Operational Simplicity:** Database backups and maintenance integrate with standard host tools.

*Note: A containerized PostgreSQL fallback profile (`--profile container-db`) is also provided in `compose.hostinger.yaml` should the operator prefer complete container isolation.*

---

## 4. Resource Allocation & Sizing Plan (1 vCPU, 4 GB RAM)

### Memory Budget Decomposition

```text
Hostinger KVM 1 Physical RAM: 3.8 GiB (3,891 MiB)
========================================================================================
[ Existing Baseline Workloads ]
  - Ubuntu OS, kernel, systemd, sshd, journald:     ~400 MiB
  - Existing n8n Docker container:                  ~280 MiB
  - Host PostgreSQL 16 (shared):                    ~180 MiB
  - Host Nginx reverse proxy:                        ~30 MiB
  Subtotal Existing Baseline:                       ~890 MiB (approx 23% of total RAM)

[ Physio One Container Stack (Hard Limits) ]
  - FastAPI REST Backend (physio_hostinger_api):     400 MiB limit (typically  ~90 MiB idle)
  - Background Worker (physio_hostinger_worker):     350 MiB limit (typically  ~95 MiB idle)
  - Next.js Dashboard (physio_hostinger_frontend):   350 MiB limit (typically  ~60 MiB idle)
  Subtotal Physio One Allocation:                 1,100 MiB (1.1 GiB limit / ~245 MiB idle)

[ Unallocated Free Headroom ]
  - Remaining Available Host Memory:              ~1,900 MiB (1.9 GiB / ~49% of total RAM)
========================================================================================
```

### CPU & Concurrency Optimization
- **Single Background Worker:** Background runner daemon executes single-threaded polling sweeps every 15 seconds (`WORKER_POLL_INTERVAL_SECONDS=15`).
- **Connection Pools:** PostgreSQL connection pool capped at `POSTGRES_POOL_SIZE=3` with `POSTGRES_MAX_OVERFLOW=5` for API, and `pool_size=2` / `max_overflow=3` for worker (total $\le 13$ connections).
- **Log Management:** Every container is capped using the `json-file` driver (`max-size: "10m"`, `max-file: "3"`), guaranteeing total container logs never exceed 90 MB.

---

## 5. Nginx Integration & Non-Interference Guarantee

Host Nginx will route external HTTPS traffic by hostname:

```text
                          Internet (Ports 80 & 443)
                                     |
                         +-----------------------+
                         |   Host Nginx Engine   |
                         +-----------+-----------+
                                     |
               +---------------------+---------------------+
               |                                           |
    Host: n8n.dataagent.in                     Host: physio.dataagent.in
               |                                           |
   [Existing n8n Container]                    +-----------+-----------+
   (100% Untouched / Active)                   |                       |
                                         /api/*, /health               /
                                               |                       |
                                       http://127.0.0.1:8000   http://127.0.0.1:3000
                                       (FastAPI Backend)       (Next.js Frontend)
```

### Safety & Rollback Verification
- Placed in an isolated configuration file: `/etc/nginx/sites-available/physio.conf`.
- Enabled via symlink: `/etc/nginx/sites-enabled/physio.conf`.
- **Zero edits** to existing n8n configuration.
- Configuration testing: `sudo nginx -t` must pass before reloading.
- Zero-downtime reload: `sudo systemctl reload nginx`.
- Instant rollback: `sudo rm /etc/nginx/sites-enabled/physio.conf && sudo nginx -t && sudo systemctl reload nginx`.
