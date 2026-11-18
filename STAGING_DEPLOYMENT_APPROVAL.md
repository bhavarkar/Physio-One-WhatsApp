# STAGING DEPLOYMENT APPROVAL & OPERATIONAL SPECIFICATION

**Project:** Physio One WhatsApp AI Platform (Single Organization Edition)  
**Target Environment:** Google Cloud Platform (GCP) — Isolated Staging  
**Document Purpose:** Complete specification of all cloud resources, secrets bootstrap, IAM roles, deployment sequences, connection budgets, and rollback mechanisms for explicit operator authorization.

> [!IMPORTANT]  
> **MANDATORY STOP CONDITION:** Do NOT execute any of the provisioning commands in this document without explicit written operator approval. Zero cloud resources have been created. Zero live messages will be sent.

---

## 1. GCP Project ID & Organization

- **Project ID:** `[OPERATOR TO SUPPLY]` (e.g. `physio-one-staging-2026`)
- **Organization:** Physio One Clinic
- **Billing Account:** Operator to link prior to running Terraform.
- **Budget Notification:** Mandatory billing alert set at **USD 35.00** ceiling (soft alert at USD 15.00). Note: GCP billing alerts notify administrators via email/PubSub; they do not automatically shut down resources. Hard ceilings require container scaling limits (`max_instance_count = 3`).

---

## 2. Target Region & Availability

- **Proposed Region:** `asia-south1` (Mumbai, India)  
  *Rationale:* Meets Indian healthcare data sovereignty requirements, minimizes latency for clinic staff and patients in India (< 50ms), supports all required GCP services (Cloud Run v2, Cloud SQL PG16, Cloud Tasks, Cloud Scheduler, Secret Manager, Artifact Registry).
- **Zonal Availability:** `asia-south1-a` (single-zone staging tier to minimize cost).

---

## 3. Reviewable List of Resources to Create

The complete infrastructure is declared in `infra/staging/main.tf` (17 top-level resource blocks expanding via `for_each` to **43 discrete Google Cloud resource instances**):

| Resource Type | Resource Identifier | Purpose & Specifications |
|---|---|---|
| **Google Project Services (APIs)** | `apis` (8 APIs) | `run.googleapis.com`, `sqladmin.googleapis.com`, `cloudtasks.googleapis.com`, `cloudscheduler.googleapis.com`, `secretmanager.googleapis.com`, `artifactregistry.googleapis.com`, `monitoring.googleapis.com`, `logging.googleapis.com`. |
| **Artifact Registry** | `physio-staging` | Docker repository in `asia-south1` for `api` and `frontend` images. |
| **Service Accounts** | `physio-staging-api` | Runtime identity for Cloud Run API service and Cloud Run migration job. |
| **Service Accounts** | `physio-staging-worker` | Identity for Cloud Scheduler and Cloud Tasks OIDC token generation. |
| **IAM Member** | `api_sql` | `roles/cloudsql.client` granted to `physio-staging-api`. |
| **IAM Member** | `api_tasks` | `roles/cloudtasks.enqueuer` granted to `physio-staging-api`. |
| **IAM Member** | `worker_run` | `roles/run.invoker` granted to `physio-staging-worker`. |
| **IAM Member** | `api_read` (7 bindings) | `roles/secretmanager.secretAccessor` granted to `physio-staging-api` for all 7 secrets. |
| **Secret Manager Secrets** | `physio-staging-*` (7 secrets) | `db-password`, `app-secret`, `jwt-secret`, `worker-token`, `whatsapp-token`, `whatsapp-app-secret`, `llm-key`. Containers created by Terraform; versions added out-of-band. |
| **Cloud SQL Instance** | `physio-staging-pg` | PostgreSQL 16, tier `db-custom-1-3840` (or `db-f1-micro`), 10 GB SSD, Zonal, automated daily backups, `ipv4_enabled = true` with zero authorized networks (zero direct public internet access). |
| **Cloud SQL Database** | `physio_one_staging` | Application database with pgvector extension enabled. |
| **Cloud SQL User** | `physio_admin` | Database user created out-of-band via `gcloud sql users create` directly using Secret Manager password to ensure zero secret storage in `terraform.tfstate`. |
| **Cloud Tasks Queues** | `physio-staging-*` (3 queues) | `inbound`, `automation`, `campaigns`. Rate limits: 5 dispatches/sec, max 10 concurrent. Max 5 retry attempts. |
| **Cloud Run v2 Service** | `physio-staging-api` | Port 8000, 1 vCPU, 1 GiB RAM, min 0 / max 3 instances. Cloud SQL socket mount at `/cloudsql`. Secret Manager env wiring. `custom_audiences = ["https://physio-staging-api"]`. Mock outbound & safety switches injected. |
| **Cloud Run v2 Service** | `physio-staging-web` | Port 3000, 1 vCPU, 512 MiB RAM, min 0 / max 2 instances. Next.js rewrite server-side proxy to API service. |
| **Cloud Run v2 IAM** | `api_public` & `frontend_public` | `roles/run.invoker` to `allUsers` for public webhook receipt and browser UI. |
| **Cloud Run v2 Job (Migration)** | `physio-staging-db-migrate` | Dedicated migration runner (`alembic upgrade head`), 1 vCPU, 1 GiB RAM. Mounts Cloud SQL socket volume. Executed before API serves traffic. |
| **Cloud Run v2 Job (Worker)** | `physio-staging-worker-once` | Bounded execution (`python -m app.workers.runner --once`), 1 vCPU, 1 GiB RAM. Mounts Cloud SQL socket volume. |
| **Cloud Scheduler Jobs** | `physio-staging-*` (4 jobs) | `process-due` (*/5), `scan-inactivity` (*/15), `campaigns` (*/30 9-20), `inbound` (*/2). Asia/Kolkata timezone, OIDC Bearer tokens. |

---

## 4. Expected Monthly Cost Assessment

Itemized cost projection in Google Cloud region `asia-south1`:

| GCP Component | Resource Tier | Monthly Free Tier Allowance | Low Usage | Expected Staging | High Usage |
|---|---|---|---|---|---|
| **Cloud SQL (Custom Tier)** | `db-custom-1-3840` (1 vCPU, 3.75GB) + 10GB SSD | None | $25.00 | $27.50 | $30.00 |
| **Cloud SQL (Micro Tier Option)** | `db-f1-micro` + 10GB SSD | None | $9.50 | $10.50 | $12.00 |
| **Cloud Run (API & Worker)** | Max 3 instances, scaled to 0 | 2M req, 180k vCPU-s, 360k GiB-s | $0.00 | $1.00 | $3.50 |
| **Cloud Run (Web Frontend)** | Max 2 instances, scaled to 0 | Covered under monthly free tier | $0.00 | $0.50 | $1.50 |
| **Cloud Tasks** | 3 queues, <10k operations | 1M operations/month free | $0.00 | $0.00 | $0.20 |
| **Cloud Scheduler** | 4 jobs | 3 free jobs per billing account | $0.10 | $0.10 | $0.10 |
| **Secret Manager** | 7 active secrets, <1k ops | 6 active versions free | $0.20 | $0.40 | $0.80 |
| **Artifact Registry** | 1 repository, ~2-4 GB images | 0.5 GB free | $0.20 | $0.40 | $0.80 |
| **Cloud Logging / Monitoring** | System & container logs | 50 GB ingestion free | $0.00 | $0.00 | $1.00 |
| **Network Egress** | Low-volume webhooks & UI | 5 GB free egress | $0.20 | $0.50 | $1.50 |
| **Total Estimated Cost (db-custom-1-3840)** | | | **$25.70 / mo** | **$30.40 / mo** | **$39.40 / mo** |
| **Total Estimated Cost (db-f1-micro)** | | | **$10.20 / mo** | **$13.40 / mo** | **$21.40 / mo** |

### Scale-Down & Cost Reduction Instructions
- **Off-hours database shutdown:** To eliminate Cloud SQL compute costs when staging is idle over weekends or nights:
  ```bash
  gcloud sql instances patch physio-staging-pg --activation-policy=NEVER
  ```
  While stopped, only 10 GB SSD storage is billed (~$1.70/month). To resume:
  ```bash
  gcloud sql instances patch physio-staging-pg --activation-policy=ALWAYS
  ```
- **Scale-to-zero containers:** Both Cloud Run services are configured with `min_instance_count = 0`, ensuring zero container CPU/RAM charges when idle.

---

## 5. Connection Budget & Concurrency Calculations

| Component | Default Pool Size | Max Overflow | Max Instances / Processes | Max Conns per Component |
|---|---|---|---|---|
| **Cloud Run API** | 5 | 5 | 3 | $3 \times (5 + 5) = 30$ |
| **Worker Once / Job** | 2 | 1 | 1 | $1 \times (2 + 1) = 3$ |
| **Migration Job** | 1 (NullPool) | 0 | 1 | 1 |
| **Admin / Cloud SQL Internal** | N/A | N/A | N/A | 5 |
| **Total System Peak** | | | | **39 Connections** |

- **Tier Comparison:**
  - `db-custom-1-3840`: `max_connections = 100`. Total peak = 39. Headroom = 61 connections (61% buffer). **Recommended.**
  - `db-f1-micro`: `max_connections = 25`. Default 39 connections exceeds tier limit. If `db-f1-micro` is chosen for cost savings, set container env vars `POSTGRES_POOL_SIZE=2` and `POSTGRES_MAX_OVERFLOW=2` ($3 \times 4 + 1 + 1 + 5 = 19 \le 25$).

---

## 6. Authentication Architecture Separation

| Workflow | Trigger Source | Destination | Auth Mechanism | Credentials / Token Format |
|---|---|---|---|---|
| **Event-driven Tasks** | Cloud Tasks | Cloud Run API HTTP (`/api/v1/automations/process-due`) | OIDC Token | Google-signed ID token (`service_account_email = worker_sa.email`, `audience = "https://physio-staging-api"`). Signature validated against Google public certs. |
| **Periodic Orchestration** | Cloud Scheduler | Cloud Run API HTTP (`/api/v1/automations/process-due`, etc.) | OIDC Token | Google-signed ID token minted by Cloud Scheduler. Audience verified in `require_worker_auth`. |
| **Batch / Maintenance** | Manual / CLI | Cloud Run Job `physio-staging-worker-once` | OAuth 2.0 Token | Google Cloud Run Jobs REST API (`:run`) requires OAuth 2.0 access token with scope `cloud-platform` and IAM role `roles/run.invoker` or `roles/run.developer`. |
| **Database Migration** | Pre-flight Bootstrap | Cloud Run Job `physio-staging-db-migrate` | Direct Job Execution | Runs `alembic upgrade head` over Cloud SQL Unix socket volume. |

---

## 7. Staged Bootstrap Sequence (Resolves Dependency Cycles)

To avoid circular dependencies between Secret containers, Secret versions, Docker images, and Cloud Run services:

```bash
# ------------------------------------------------------------------------------
# PHASE 1: Operator Authentication & Project Selection
# ------------------------------------------------------------------------------
export PROJECT_ID="YOUR_STAGING_PROJECT_ID"
export REGION="asia-south1"
export COMMIT=$(git rev-parse --short HEAD)
export REPO="${REGION}-docker.pkg.dev/${PROJECT_ID}/physio-staging"

gcloud auth login
gcloud auth application-default login
gcloud config set project "$PROJECT_ID"

# ------------------------------------------------------------------------------
# PHASE 2: Provision Foundation Infrastructure (APIs, Registry, IAM, Secret Containers)
# ------------------------------------------------------------------------------
cd infra/staging
terraform init
terraform apply \
  -target=google_project_service.apis \
  -target=google_artifact_registry_repository.repo \
  -target=google_service_account.api \
  -target=google_service_account.worker \
  -target=google_secret_manager_secret.s \
  -target=google_secret_manager_secret_iam_member.api_read \
  -var="project_id=${PROJECT_ID}" \
  -var="region=${REGION}" \
  -var="api_image=${REPO}/api:${COMMIT}" \
  -var="frontend_image=${REPO}/frontend:${COMMIT}"

# ------------------------------------------------------------------------------
# PHASE 3: Build & Push Container Images to Artifact Registry
# ------------------------------------------------------------------------------
cd ../..
gcloud auth configure-docker "${REGION}-docker.pkg.dev"

docker build -t "${REPO}/api:${COMMIT}" -f docker/Dockerfile.api .
docker push "${REPO}/api:${COMMIT}"

docker build -t "${REPO}/frontend:${COMMIT}" -f docker/Dockerfile.frontend .
docker push "${REPO}/frontend:${COMMIT}"

# ------------------------------------------------------------------------------
# PHASE 4: Populate Secret Versions Out-of-Band (Never in Terraform state)
# ------------------------------------------------------------------------------
DB_PASS=$(openssl rand -hex 16)
echo -n "$DB_PASS" | gcloud secrets versions add physio-staging-db-password --data-file=-
echo -n "$(openssl rand -hex 32)" | gcloud secrets versions add physio-staging-app-secret --data-file=-
echo -n "$(openssl rand -hex 32)" | gcloud secrets versions add physio-staging-jwt-secret --data-file=-
echo -n "$(openssl rand -hex 16)" | gcloud secrets versions add physio-staging-worker-token --data-file=-
echo -n "staging-test-token" | gcloud secrets versions add physio-staging-whatsapp-token --data-file=-
echo -n "staging-test-app-secret" | gcloud secrets versions add physio-staging-whatsapp-app-secret --data-file=-
echo -n "staging-test-llm-key" | gcloud secrets versions add physio-staging-llm-key --data-file=-

# ------------------------------------------------------------------------------
# PHASE 5: Provision Core Cloud SQL, Jobs, Cloud Run Services & Schedulers
# ------------------------------------------------------------------------------
cd infra/staging
terraform plan \
  -var="project_id=${PROJECT_ID}" \
  -var="region=${REGION}" \
  -var="db_tier=db-custom-1-3840" \
  -var="api_image=${REPO}/api:${COMMIT}" \
  -var="frontend_image=${REPO}/frontend:${COMMIT}" \
  -out=staging.tfplan

terraform apply staging.tfplan

# Create Cloud SQL database user directly using Secret Manager password (zero credentials in tfstate)
gcloud sql users create physio_admin \
  --instance="physio-staging-pg" \
  --password="$DB_PASS"

# ------------------------------------------------------------------------------
# PHASE 6: Execute Dedicated Migration Job Before Traffic Ingress
# ------------------------------------------------------------------------------
gcloud run jobs execute physio-staging-db-migrate \
  --region="${REGION}" \
  --wait
```

---

## 8. Staging Isolation & Outbound Safeguards

1. **Global Kill Switch:** `AUTOMATION_OUTBOUND_ENABLED=false` is enforced as the default Cloud Run environment variable.
2. **Provider Mock Mode by Default:** `STAGING_MOCK_OUTBOUND=true` is enabled by default in staging. All outbound messages generate synthetic receipts with `mock_staging_*` IDs without contacting Meta or YCloud external APIs.
3. **Fail-Closed Allowlist:** If mock mode is ever toggled off (`STAGING_MOCK_OUTBOUND=false`), `STAGING_ALLOWLIST_PHONE_NUMBERS` enforces a strict deny-all default. If the allowlist is empty `[]` or unconfigured, 100% of outbound messages are immediately rejected.
4. **Appointments Read-Only Mode:** `APPOINTMENTS_READ_ONLY=true` blocks any booking or cancellation mutations in staging.
5. **Campaigns Draft-Only Mode:** `CAMPAIGNS_DRAFT_ONLY=true` prevents campaigns from being scheduled or dispatched.
6. **No Production Credential Fallback:** Fail-closed design ensures missing credentials result in clean errors rather than silent production failover.

---

## 9. Staging Verification Smoke Tests

```bash
API_URL=$(gcloud run services describe physio-staging-api --region=asia-south1 --format="value(status.url)")
WEB_URL=$(gcloud run services describe physio-staging-web --region=asia-south1 --format="value(status.url)")

# 1. Health Probe
curl -f "${API_URL}/health"

# 2. Setup Status Check
curl -f "${API_URL}/api/v1/auth/setup-status"

# 3. Initialize Staging Admin
curl -X POST "${API_URL}/api/v1/auth/setup" \
  -H "Content-Type: application/json" \
  -d '{"email":"owner@physioone.com","password":"StagingPassword2026#","full_name":"Clinic Owner"}'

# 4. Confirm Second Setup Is Blocked
curl -X POST "${API_URL}/api/v1/auth/setup" \
  -H "Content-Type: application/json" \
  -d '{"email":"hacker@test.com","password":"StagingPassword2026#","full_name":"Attacker"}'
# Must return HTTP 403 Forbidden
```

---

## 10. Emergency Rollback Procedures

### 10.1 Instant Outbound Messaging Shutdown
```bash
gcloud run services update physio-staging-api \
  --region=asia-south1 \
  --update-env-vars AUTOMATION_OUTBOUND_ENABLED=false
```

### 10.2 Fast Revision Rollback
```bash
PREV_REV=$(gcloud run revisions list --service=physio-staging-api --region=asia-south1 --format="value(name)" --limit=2 | sed -n '2p')
gcloud run services update-traffic physio-staging-api \
  --region=asia-south1 \
  --to-revisions="${PREV_REV}=100"
```

### 10.3 Complete Staging Infrastructure Teardown
```bash
cd infra/staging
terraform destroy \
  -var="project_id=${PROJECT_ID}" \
  -var="region=${REGION}" \
  -var="api_image=${REPO}/api:${COMMIT}" \
  -var="frontend_image=${REPO}/frontend:${COMMIT}"
```

---

## 11. Operator Deployment Approval Checklist

Before proceeding with any live cloud deployment, the operator must complete and sign this checklist:

- [ ] **GCP Project ID:** `________________________________________`
- [ ] **Target GCP Region:** `asia-south1` (or specify: `________________`)
- [ ] **Billing Authorization:** Confirmed active billing account linked.
- [ ] **Monthly Budget Cap:** $35.00 ceiling acknowledged.
- [ ] **Database Tier Selection:** `[ ] db-custom-1-3840 (Recommended)` / `[ ] db-f1-micro (Low-cost)`
- [ ] **Secret Provisioning:** Confirmed Secret Manager out-of-band generation sequence (no credentials in Git or tfstate).
- [ ] **External API Access:** `[ ] Mock Mode Only` / `[ ] Meta Test Sandbox Allowed` (No real patient numbers).
- [ ] **Outbound Kill Switch:** Confirmed `AUTOMATION_OUTBOUND_ENABLED=false` default.
- [ ] **Formal Approval:** Authorization granted to execute Terraform staged bootstrap.

**Operator Name:** `___________________________________`  
**Operator Signature:** `________________________________`  
**Approval Date:** `____________________________________`
