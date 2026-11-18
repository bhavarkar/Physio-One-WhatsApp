# Physio One WhatsApp AI Platform — Deployment Runbook

**Primary Target (Active):** Hostinger Ubuntu Linux VPS (Docker Compose with Caddy Reverse Proxy & Automated HTTPS)  
**Legacy Reference Target (Deferred):** Google Cloud Platform (GCP) Cloud Run & Cloud SQL  
**Organization:** Physio One Clinic (Single Organization Edition)  
**Host Specifications (VPS):** 4 GB RAM, 50 GB SSD, Ubuntu 22.04/24.04 LTS  

---

> [!NOTE]
> **Architecture Update (Task 20):** The primary deployment architecture has migrated from Google Cloud Run to a dedicated Hostinger Ubuntu Linux VPS running Docker Compose. For the active VPS deployment runbook, see [Section 10](#10-hostinger-ubuntu-linux-vps-deployment-runbook-active). Sections 1–9 document the legacy Google Cloud Run deployment pipeline, which remains preserved for reference.

---

## 1. Pre-Deployment Boundary & Approval Gate

> [!IMPORTANT]  
> **Mandatory Rule:** Do **NOT** deploy to Google Cloud, run `terraform apply`, or create billable GCP resources without explicit operator sign-off and approval. Production credentials must never be used in staging, and no real WhatsApp messages may be dispatched to actual patients during staging verification.

### Pre-Deployment Checklist
- [x] Backend tests pass: 238/238 tests passing (100% pass rate).
- [x] Frontend tests pass: 53/53 tests passing across 12 test suites.
- [x] TypeScript typecheck: 0 errors (`tsc --noEmit`).
- [x] Next.js production build: 18/18 static routes compiled cleanly.
- [x] Docker Compose local verification: PostgreSQL 16 + pgvector, API, Worker, and Frontend operational.
- [x] Terraform staging IaC validated and formatted (17 top-level resource blocks expanding to 43 resource instances, acyclic bootstrap).
- [x] Safety defaults verified (`AUTOMATION_OUTBOUND_ENABLED=false`, `STAGING_MOCK_OUTBOUND=true`, fail-closed deny-all allowlist, AI Inbound disabled mode).
- [x] Schedulers paused by default (`paused = true` declared in Terraform; activation restricted to Phase 11).
- [x] Dedicated migration job declared (`physio-staging-db-migrate` running `alembic upgrade head`).
- [x] Native Windows PowerShell 5.1 deployment runner (`scripts/deploy-staging.ps1`) and verification runner (`scripts/verify-staging.ps1`) verified.
- [x] Connection budget verified for staging Cloud SQL tier (`db-custom-1-3840` / `db-f1-micro`).

---

## 2. GCP Project Setup & Prerequisites

### 2.1 Project Initialization & Budget Alert
Before running any Terraform commands, configure a GCP project and establish a hard budget alert to ensure costs remain under USD 35/month:

```bash
# Set GCP active project
gcloud config set project YOUR_STAGING_PROJECT_ID

# Verify billing is linked
gcloud beta billing projects describe YOUR_STAGING_PROJECT_ID

# Set a billing budget alert (e.g. 15 USD soft alert, 35 USD hard cap notification) via Cloud Console:
# Billing -> Budgets & Alerts -> Create Budget -> Target: $35.00
```

### 2.2 Enable Required Google Cloud APIs
Terraform manages APIs, but pre-enabling Cloud Resource Manager and Service Usage speeds up provisioning:
```bash
gcloud services enable \
  cloudresourcemanager.googleapis.com \
  serviceusage.googleapis.com \
  artifactregistry.googleapis.com
```

---

## 3. Secret Provisioning in Google Secret Manager

All sensitive credentials **must** be populated out-of-band via Secret Manager. Never commit secrets to Git, pass them in plaintext environment variables, or store them in Terraform state files.

The Terraform configuration defines 7 secret containers with the prefix `physio-staging-`:

```bash
# Generate high-entropy secrets locally
DB_PASS=$(openssl rand -hex 24)
APP_SECRET=$(openssl rand -hex 32)
JWT_SECRET=$(openssl rand -hex 32)
WORKER_TOKEN=$(openssl rand -hex 32)

# 1. Database password
gcloud secrets create physio-staging-db-password --replication-policy=automatic
echo -n "$DB_PASS" | gcloud secrets versions add physio-staging-db-password --data-file=-

# 2. Application secret key
gcloud secrets create physio-staging-app-secret --replication-policy=automatic
echo -n "$APP_SECRET" | gcloud secrets versions add physio-staging-app-secret --data-file=-

# 3. JWT secret key
gcloud secrets create physio-staging-jwt-secret --replication-policy=automatic
echo -n "$JWT_SECRET" | gcloud secrets versions add physio-staging-jwt-secret --data-file=-

# 4. Automation worker secret token
gcloud secrets create physio-staging-worker-token --replication-policy=automatic
echo -n "$WORKER_TOKEN" | gcloud secrets versions add physio-staging-worker-token --data-file=-

# 5. WhatsApp API Token (Staging / Sandbox token)
gcloud secrets create physio-staging-whatsapp-token --replication-policy=automatic
echo -n "staging-dummy-whatsapp-token" | gcloud secrets versions add physio-staging-whatsapp-token --data-file=-

# 6. WhatsApp App Secret (For HMAC webhook verification)
gcloud secrets create physio-staging-whatsapp-app-secret --replication-policy=automatic
echo -n "staging-dummy-app-secret" | gcloud secrets versions add physio-staging-whatsapp-app-secret --data-file=-

# 7. LLM Provider API Key (Staging OpenAI / Gemini / Anthropic test key)
gcloud secrets create physio-staging-llm-key --replication-policy=automatic
echo -n "staging-dummy-llm-key" | gcloud secrets versions add physio-staging-llm-key --data-file=-
```

---

## 4. Container Image Build & Publishing

Build production images using the multi-stage Dockerfiles and push to Google Artifact Registry:

```bash
# Configure Docker authentication for Artifact Registry in asia-south1
gcloud auth configure-docker asia-south1-docker.pkg.dev

# Define image tags
REGION="asia-south1"
PROJECT_ID="YOUR_STAGING_PROJECT_ID"
REPO="asia-south1-docker.pkg.dev/${PROJECT_ID}/physio-staging"
COMMIT=$(git rev-parse --short HEAD)

# Build and push API image
docker build -t "${REPO}/api:${COMMIT}" -f docker/Dockerfile.api .
docker push "${REPO}/api:${COMMIT}"

# Build and push Frontend image
docker build -t "${REPO}/frontend:${COMMIT}" -f docker/Dockerfile.frontend .
docker push "${REPO}/frontend:${COMMIT}"
```

---

## 5. Automated Windows PowerShell 5.1 Deployment Runner

For reliable, reproducible orchestration on Windows 11 / Windows PowerShell 5.1, use `scripts/deploy-staging.ps1`. The script enforces the 11-phase acyclic deployment sequence, verifies native command exit codes, checks for active GCP project synchronization, requires explicit confirmation before billable actions, and redacts all secrets from terminal logs.

### 5.1 Syntax & Available Options

```powershell
# Usage:
.\scripts\deploy-staging.ps1 -ProjectId YOUR_PROJECT_ID [-Region asia-south1] [-DbTier db-custom-1-3840] [-Phase PhaseName] [-DryRun] [-Validate] [-ShowPlan] [-Force]
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `-ProjectId` | String | *Mandatory* | Target Google Cloud project identifier. Validated against active gcloud config. |
| `-Region` | String | `asia-south1` | Target GCP region. |
| `-DbTier` | String | `db-custom-1-3840`| Cloud SQL instance machine tier. |
| `-Phase` | String | `All` | Specific phase (`Preflight`, `Foundation`, `BuildImages`, `Secrets`, `Database`, `User`, `Migration`, `App`, `Schedulers`, `Reconcile`, `ActivateSchedulers`). |
| `-DryRun` | Switch | `false` | Prints all planned operations and commands without executing mutating actions. |
| `-Validate` | Switch | `false` | Validates local tools and Terraform syntax without requiring ProjectId or cloud access. |
| `-ShowPlan` | Switch | `false` | Runs `terraform plan` and displays differences without applying. |
| `-Force` | Switch | `false` | Bypasses the interactive operator confirmation prompt. |

### 5.2 PowerShell Deployment Walkthrough

```powershell
# Step 1: Pre-flight Local Validation (Zero cost, no cloud calls)
powershell.exe -ExecutionPolicy Bypass -File scripts\deploy-staging.ps1 -Validate

# Step 2: Dry-Run Simulation (Displays full 11-phase sequence with redacted secrets)
powershell.exe -ExecutionPolicy Bypass -File scripts\deploy-staging.ps1 -ProjectId "YOUR_STAGING_PROJECT_ID" -DryRun

# Step 3: Execute Phases 1-10 (Full Staged Provisioning)
powershell.exe -ExecutionPolicy Bypass -File scripts\deploy-staging.ps1 -ProjectId "YOUR_STAGING_PROJECT_ID" -Phase All

# Step 4: Run Post-Deployment Verification
powershell.exe -ExecutionPolicy Bypass -File scripts\verify-staging.ps1 -ProjectId "YOUR_STAGING_PROJECT_ID" -CloudCheck

# Step 5: Resume Paused Cloud Schedulers (Separate Explicit Gate)
powershell.exe -ExecutionPolicy Bypass -File scripts\deploy-staging.ps1 -ProjectId "YOUR_STAGING_PROJECT_ID" -Phase ActivateSchedulers
```

---

## 6. Manual Staged CLI Reference (Bash / Cloud Shell)

---

## 6. Dedicated Database Migration Execution

Once Cloud SQL and Secret Manager are provisioned, execute database migrations using the dedicated Cloud Run migration job BEFORE the API starts serving traffic:

```bash
# Execute dedicated migration job running 'alembic upgrade head' over Cloud SQL Unix socket
gcloud run jobs execute physio-staging-db-migrate \
  --region=asia-south1 \
  --wait

# Verify database health and migration status via API healthcheck:
curl -f https://physio-staging-api-YOUR_HASH-el.a.run.app/health
```

Expected JSON response:
```json
{
  "status": "healthy",
  "app_name": "Physio One WhatsApp AI Agent",
  "environment": "staging",
  "version": "1.0.0-draft"
}
```

---

## 7. Initial Clinic Staff Setup & Verification

### 7.1 Verify Setup Status
Check if initial Owner account is required:
```bash
curl https://physio-staging-api-YOUR_HASH-el.a.run.app/api/v1/auth/setup-status
```
Expected: `{"is_initialized": false, "owner_count": 0}`

### 7.2 Create the First Owner Account
```bash
curl -X POST https://physio-staging-api-YOUR_HASH-el.a.run.app/api/v1/auth/setup \
  -H "Content-Type: application/json" \
  -d '{
    "email": "director@physioone.com",
    "password": "StrongPassword123#",
    "full_name": "Dr. Owner"
  }'
```

### 7.3 Webhook Verification Ping (Meta Challenge)
Verify that the public webhook endpoint verifies challenge tokens with constant-time HMAC check:
```bash
curl "https://physio-staging-api-YOUR_HASH-el.a.run.app/api/v1/webhooks/whatsapp/meta?hub.mode=subscribe&hub.challenge=12345678&hub.verify_token=meta_verify_secret_123"
```
Expected return: `12345678` with HTTP 200 OK.

---

## 8. Emergency Kill-Switches & Rollback Procedures

### 8.1 Instant Outbound Messaging Kill-Switch
If unintended outbound messages or campaign anomalies are detected, instantly disarm all outbound sending without shutting down the API or webhook receipt:

```bash
gcloud run services update physio-staging-api \
  --region=asia-south1 \
  --update-env-vars AUTOMATION_OUTBOUND_ENABLED=false
```

### 8.2 AI Inbound Automation Mode Switching
Switch AI receptionist inbound behavior from autonomous drafting to human-only or fully disabled:
- **Mode A (Default Safe Mode):** AI creates read-only draft replies; human staff must explicitly click "Approve & Send".
- **Disabled Mode:** AI does not process incoming messages; messages land directly in staff Inbox.

To force disabled mode via API:
```bash
curl -X PUT https://physio-staging-api-YOUR_HASH-el.a.run.app/api/v1/ai-inbound/settings \
  -H "Authorization: Bearer <OWNER_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"default_inbound_mode": "disabled"}'
```

### 8.3 Traffic Shifting / Fast Rollback to Previous Revision
To immediately revert to the previously working container revision in Cloud Run:

```bash
# List previous revisions
gcloud run revisions list --service=physio-staging-api --region=asia-south1

# Instantly route 100% of traffic to the previous known-good revision
gcloud run services update-traffic physio-staging-api \
  --region=asia-south1 \
  --to-revisions=physio-staging-api-PREVIOUS_REV=100
```

---

## 9. Staging Teardown / Destruction Procedure

When staging verification is complete, destroy all staging cloud resources to prevent ongoing billing:

```bash
cd infra/staging
terraform destroy \
  -var="project_id=${PROJECT_ID}" \
  -var="region=asia-south1" \
  -var="env=staging" \
  -var="api_image=${REPO}/api:${COMMIT}" \
  -var="frontend_image=${REPO}/frontend:${COMMIT}"
```

---

## 10. Hostinger Ubuntu Linux VPS Deployment Runbook (Active)

This section provides the end-to-end, operator-ready deployment protocol for deploying the Physio One WhatsApp AI Platform onto a Hostinger Ubuntu Linux VPS using Docker Compose and Caddy.

### 10.1 Host Prerequisites & Sizing
- **Target OS:** Ubuntu 22.04 LTS or Ubuntu 24.04 LTS
- **Hardware Profile:** 4 GB RAM, 50 GB SSD storage, 1–2 vCPUs
- **Installed Software:** Docker Engine v24+, Docker Compose v2.20+, Git, curl, UFW, fail2ban
- **Domain & DNS:** Fully qualified domain name (e.g. `clinic.physioone.in` or `staging.physioone.in`) pointing to the VPS public IP address via an `A` record.

### 10.2 Host Hardening Protocol
Execute on the VPS host as root during initial setup:
```bash
# 1. Update system packages
apt update && apt upgrade -y

# 2. Create non-root deployment user
adduser physioadmin
usermod -aG sudo physioadmin

# 3. Configure SSH key-only authentication
mkdir -p /home/physioadmin/.ssh
cat >> /home/physioadmin/.ssh/authorized_keys # paste operator public key
chown -R physioadmin:physioadmin /home/physioadmin/.ssh
chmod 700 /home/physioadmin/.ssh && chmod 600 /home/physioadmin/.ssh/authorized_keys

# 4. Configure UFW Firewall (restrict to SSH, HTTP, HTTPS)
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable

# 5. Install Docker Engine & Compose plugin
curl -fsSL https://get.docker.com | sh
usermod -aG docker physioadmin
```

### 10.3 Repository & Directory Setup
As `physioadmin`:
```bash
# Clone the repository into /opt/physio
sudo mkdir -p /opt/physio
sudo chown -R physioadmin:physioadmin /opt/physio
git clone -b development https://github.com/organization/physio-one-agent.git /opt/physio
cd /opt/physio

# Initialize environment configuration
cp deploy/vps/.env.example /opt/physio/.env
chmod 600 /opt/physio/.env

# Edit .env and supply actual secrets:
#   DOMAIN=staging.physioone.in
#   LETSENCRYPT_EMAIL=admin@physioone.in
#   POSTGRES_PASSWORD=<generated-secure-password>
#   APP_SECRET=<64-char-hex>
#   JWT_SECRET_KEY=<64-char-hex>
#   AUTOMATION_WORKER_SECRET_TOKEN=<64-char-hex>
#   META_WHATSAPP_APP_SECRET=...
#   YCLOUD_WEBHOOK_SECRET=...
nano /opt/physio/.env
```

### 10.4 Execution Protocols

#### Phase 1: Preflight Verification
```bash
bash deploy/vps/scripts/preflight.sh
```
Verifies memory ($\ge 3.2$ GB), disk space ($\ge 5$ GB free), Docker & Compose version, `.env` file permissions (`chmod 600`), and Compose file syntax.

#### Phase 2: Staging Deployment (Isolated Mock Mode)
```bash
# Deploys with compose.yaml and compose.staging.yaml overlay:
#   STAGING_MOCK_OUTBOUND=true
#   AUTOMATION_OUTBOUND_ENABLED=false
#   DEFAULT_AI_INBOUND_MODE=disabled
#   APPOINTMENTS_READ_ONLY=true
#   CAMPAIGNS_DRAFT_ONLY=true
#   STAGING_ALLOWLIST_PHONE_NUMBERS=[]
bash deploy/vps/scripts/deploy.sh staging
```

#### Phase 3: Production Deployment
```bash
# Deploys base compose.yaml without mock overrides
bash deploy/vps/scripts/deploy.sh prod
```

#### Phase 4: Post-Deployment Verification
```bash
bash deploy/vps/scripts/verify.sh
```
Checks:
- All 5 container services are active and healthy.
- Port 5432 is strictly private and not reachable from host or internet.
- Local endpoint `http://127.0.0.1:8000/health` returns `200 OK`.
- Public HTTPS endpoint `https://$DOMAIN/health` returns `200 OK`.
- First-time owner setup status via `/api/v1/auth/setup-status`.

### 10.5 Maintenance & Operations

#### Database Schema Migrations
```bash
# Run one-shot Alembic migration
bash deploy/vps/scripts/migrate.sh
```

#### Automated Compressed Backups
```bash
# Creates /opt/physio/backups/physio_backup_<timestamp>.sql.gz with SHA256 checksum
bash deploy/vps/scripts/backup.sh

# Recommended root/physioadmin cron entry (daily at 02:00 IST):
# 0 2 * * * /opt/physio/deploy/vps/scripts/backup.sh >> /var/log/physio-backup.log 2>&1
```

#### Disaster Recovery / Database Restore
```bash
# Enforces gzip integrity check and confirmation gate
bash deploy/vps/scripts/restore.sh /opt/physio/backups/physio_backup_YYYYMMDD_HHMMSS.sql.gz --confirm-restore
```

#### Emergency Rollback & Outbound Kill Switch
```bash
# Reverts images to previous version tag and stops outbound automation
# Invariant: Never automatically down-migrates database schema
bash deploy/vps/scripts/rollback.sh --confirm
```

---

### 10.6 Task 21 Integration Rehearsal & Security Validation Results

During Task 21, the complete Hostinger VPS Docker Compose stack was rehearsed in a disposable local environment:
1. **Disposable Stack Verified:**
   - PostgreSQL 16 + pgvector 0.8.7 started cleanly.
   - 64 database tables created via Alembic migrations (`001` to `008`).
   - Caddy reversed-proxied Next.js frontend (port 3000) and FastAPI API (port 8000) on unified port 80/443 ingress.
   - Worker daemon processed synthetic queued tasks with outbound mock safeguards active.
   - Container restart preserved PostgreSQL data volumes.
2. **Queue Concurrency Hardened:**
   - Row-level atomic locking with `.with_for_update(skip_locked=True)` implemented in `AutomationWorkerService`, `InboundQueueService`, and `CampaignService` to prevent race conditions across parallel worker instances.
   - 7/7 new concurrency integration tests passing (`test_vps_queue_concurrency_and_reliability.py`).
3. **Backup & Disaster Recovery Rehearsed:**
   - `pg_dump` compressed with gzip produces verified archives (`gzip -t` verified).
   - Full restoration into a clean test database restored 64 tables and pgvector extension cleanly.
4. **Measured Resource Footprint:**
   - Total idle memory across all 5 containers: **323 MiB** (PostgreSQL 66.5 MiB, API 91.6 MiB, Worker 93.3 MiB, Frontend 58.6 MiB, Caddy 13.1 MiB).
   - Hard container limits configured to 2.4 GB, providing 1.6 GB headroom for Ubuntu OS and page cache on a 4 GB VPS.
5. **Read-Only Preflight Inspection:**
   - Preflight inspection checklist established in `deploy/vps/HOSTINGER_PREFLIGHT_CHECKLIST.md` for non-mutating server inspection in Task 22.
