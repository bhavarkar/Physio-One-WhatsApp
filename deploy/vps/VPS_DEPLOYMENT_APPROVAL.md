# Hostinger VPS Deployment Approval Gate & Operator Action Plan

**Platform:** Physio One WhatsApp AI Platform (Single Organization Edition)  
**Host Target:** Hostinger KVM 1 Ubuntu 24.04.5 LTS VPS  
**Domain Target:** `physio.dataagent.in`  
**Coexisting Service:** `n8n.dataagent.in` (100% Preserved)  
**Status:** STOPPED AT OPERATOR APPROVAL GATE  

---

## 1. Approval Gate Protocol

> [!IMPORTANT]
> **Strict Safety Gate:** In accordance with deployment safety invariants, **no mutating actions have been performed on the VPS.** The platform codebase, Docker Compose configuration (`compose.hostinger.yaml`), host PostgreSQL scripts, and Nginx virtual host files have been prepared and validated locally.
>
> **The operator must explicitly approve each phase below before execution.**

---

## 2. Operator Execution Sequence (Step-by-Step)

### Phase A: DNS Setup (Operator Registrar / Cloudflare)
1. Add an **A record**:
   - Host: `physio`
   - Target: `YOUR_HOSTINGER_VPS_IP`
   - TTL: 300s (5 minutes)
2. Verify propagation:
   ```bash
   dig +short physio.dataagent.in
   ```

---

### Phase B: Host PostgreSQL 16 Database Initialization
1. Log in to the VPS via SSH as your non-root user (`physioadmin`).
2. Run the database provisioning script:
   ```bash
   # From the repository root on the VPS:
   cd /opt/physio/app/deploy/vps
   sudo -u postgres psql -f database/init_host_postgres.sql
   ```
   *(Creates database `physio_db`, role `physio_user`, and installs extensions `vector 0.6.0` and `btree_gist`).*
3. Verify pgvector functionality and HNSW indexing:
   ```bash
   sudo -u postgres psql -d physio_db -f database/verify_host_postgres.sql
   ```

---

### Phase C: Environment Secrets Configuration
1. Create and lock down the environment file:
   ```bash
   cd /opt/physio/app/deploy/vps
   cp .env.example .env
   chmod 600 .env
   ```
2. Populate the `.env` file with generated credentials:
   - `POSTGRES_PASSWORD`: Password configured in `init_host_postgres.sql`
   - `DATABASE_URL`: `postgresql+asyncpg://physio_user:YOUR_PASSWORD@host.docker.internal:5432/physio_db`
   - `APP_SECRET`: Generated 32-character hex key
   - `JWT_SECRET_KEY`: Generated 32-character hex key
   - `AUTOMATION_WORKER_SECRET_TOKEN`: Generated 24-character hex key
   - `CORS_ORIGINS`: `https://physio.dataagent.in`
   - `AUTOMATION_OUTBOUND_ENABLED`: `false` (Keeps outbound disabled until operator authorizes)
   - `STAGING_MOCK_OUTBOUND`: `true`

---

### Phase D: Multi-Container Deployment Execution
1. Run the deployment orchestrator in dry-run mode:
   ```bash
   chmod +x scripts/*.sh
   ./scripts/deploy_hostinger.sh --dry-run
   ```
2. If dry-run passes, execute the deployment:
   ```bash
   ./scripts/deploy_hostinger.sh
   ```
   *(Builds images, executes Alembic migrations to head, and starts `api`, `worker`, and `frontend` bound to `127.0.0.1`).*

3. Verify local container health:
   ```bash
   curl -s http://127.0.0.1:8000/health
   # Expected: {"status":"healthy","app_name":"Physio One WhatsApp AI Agent",...}
   ```

---

### Phase E: Host Nginx Virtual Host & TLS Issuance
1. Install the Nginx virtual host configuration:
   ```bash
   sudo cp deploy/vps/nginx/physio.conf /etc/nginx/sites-available/physio.conf
   ```
2. Obtain SSL certificate via Certbot:
   ```bash
   sudo certbot --nginx -d physio.dataagent.in
   ```
3. Enable the site:
   ```bash
   sudo ln -sf /etc/nginx/sites-available/physio.conf /etc/nginx/sites-enabled/
   ```
4. Verify configuration syntax:
   ```bash
   sudo nginx -t
   ```
5. Reload Nginx:
   ```bash
   sudo systemctl reload nginx
   ```
   *(Zero downtime. Does NOT impact `n8n.dataagent.in`).*

---

### Phase F: Initial Clinic Owner Setup
1. Navigate to `https://physio.dataagent.in/setup` in your browser.
2. Initialize the primary Owner credentials.
3. Verify that setup immediately locks out subsequent attempts with HTTP 403 Forbidden.

---

## 3. Emergency Rollback Playbook

If an issue arises after deployment:

### Application Container Rollback
```bash
cd /opt/physio/app/deploy/vps
./scripts/rollback_hostinger.sh --confirm
```

### Nginx Routing Rollback (Immediate n8n-only state)
```bash
sudo rm -f /etc/nginx/sites-enabled/physio.conf
sudo nginx -t
sudo systemctl reload nginx
```

---

## 4. Final Operator Authorization Request

To proceed with deployment on the Hostinger VPS, please approve the actions listed in **Phases A through E**.
