# STAGING DEPLOYMENT APPROVAL & OPERATIONAL SPECIFICATION

**Project:** Physio One WhatsApp AI Platform (Single Organization Edition)  
**Target Environment:** Google Cloud Platform (GCP) — Isolated Staging  
**Document Purpose:** Complete specification of all cloud resources, secrets, IAM roles, deployment steps, and rollback mechanisms for explicit operator authorization.

> [!IMPORTANT]  
> **MANDATORY STOP CONDITION:** Do NOT execute any of the provisioning commands in this document without explicit written operator approval. Zero cloud resources have been created. Zero live messages will be sent.

---

## 1. GCP Project ID & Organization

- **Project ID:** `[OPERATOR TO SUPPLY]` (e.g. `physio-one-staging-2026`)
- **Organization:** Physio One Clinic
- **Billing Account:** Operator to link prior to running Terraform.
- **Budget Notification:** Mandatory billing alert set at **USD 35.00** ceiling (soft alert at USD 15.00).

---

## 2. Target Region & Availability

- **Proposed Region:** `asia-south1` (Mumbai, India)  
  *Rationale:* Meets Indian healthcare data sovereignty requirements, minimizes latency for clinic staff and patients in India (< 50ms), supports all required GCP services (Cloud Run v2, Cloud SQL PG16, Cloud Tasks, Cloud Scheduler, Secret Manager).
- **Zonal Availability:** `asia-south1-a` (single-zone staging tier to minimize cost).

---

## 3. Reviewable List of Resources to Create

The complete infrastructure is declared in `infra/staging/main.tf`:

| Resource Type | Resource Identifier | Purpose & Specifications |
|---|---|---|
| **Google Project Services (APIs)** | `apis` (8 APIs) | `run.googleapis.com`, `sqladmin.googleapis.com`, `cloudtasks.googleapis.com`, `cloudscheduler.googleapis.com`, `secretmanager.googleapis.com`, `artifactregistry.googleapis.com`, `monitoring.googleapis.com`, `logging.googleapis.com`. |
| **Artifact Registry** | `physio-staging` | Docker repository in `asia-south1` for `api` and `frontend` images. |
| **Service Accounts** | `physio-staging-api` | Runtime identity for Cloud Run API service and Cloud Run migration job. |
| **Service Accounts** | `physio-staging-worker` | Identity for Cloud Scheduler and Cloud Tasks OIDC token generation. |
| **IAM Member** | `api_sql` | `roles/cloudsql.client` granted to `physio-staging-api`. |
| **IAM Member** | `api_tasks` | `roles/cloudtasks.enqueuer` granted to `physio-staging-api`. |
| **IAM Member** | `worker_run` | `roles/run.invoker` granted to `physio-staging-worker`. |
| **IAM Member** | `api_read` | `roles/secretmanager.secretAccessor` granted to `physio-staging-api` for all 7 secrets. |
| **Secret Manager Secrets** | `physio-staging-*` (7 secrets) | `db-password`, `app-secret`, `jwt-secret`, `worker-token`, `whatsapp-token`, `whatsapp-app-secret`, `llm-key`. Values populated out-of-band. |
| **Cloud SQL Instance** | `physio-staging-pg` | PostgreSQL 16, tier `db-f1-micro`, 10 GB SSD, Zonal, automated daily backups, `ipv4_enabled = true` with zero authorized networks (zero direct public internet access). |
| **Cloud SQL Database** | `physio_one_staging` | Application database with pgvector extension enabled. |
| **Cloud SQL User** | `physio_admin` | Database user authenticated via `physio-staging-db-password`. |
| **Cloud Tasks Queues** | `physio-staging-*` (3 queues) | `inbound`, `automation`, `campaigns`. Rate limits: 5 dispatches/sec, max 10 concurrent. Max 5 retry attempts. |
| **Cloud Run v2 Service** | `physio-staging-api` | Port 8000, 1 vCPU, 1 GiB RAM, min 0 / max 3 instances. Cloud SQL socket mount at `/cloudsql`. Secret Manager env wiring. `custom_audiences = ["https://physio-staging-api"]`. |
| **Cloud Run v2 Service** | `physio-staging-web` | Port 3000, 1 vCPU, 512 MiB RAM, min 0 / max 2 instances. Next.js rewrite server-side proxy to API service. |
| **Cloud Run v2 IAM** | `api_public` & `frontend_public` | `roles/run.invoker` to `allUsers` for public webhook receipt and browser UI. |
| **Cloud Run v2 Job** | `physio-staging-worker-once` | Bounded execution (`python -m app.workers.runner --once`), 1 vCPU, 1 GiB RAM. Mounts Cloud SQL socket volume for migrations and queue draining. |
| **Cloud Scheduler Jobs** | `physio-staging-*` (4 jobs) | `process-due` (*/5), `scan-inactivity` (*/15), `campaigns` (*/30 9-20), `inbound` (*/2). Asia/Kolkata timezone, OIDC Bearer tokens. |

---

## 4. Expected Monthly Cost Assessment

Itemized cost projection in Google Cloud region `asia-south1`:

| GCP Component | Resource Tier | Monthly Free Tier Allowance | Estimated Staging Cost |
|---|---|---|---|
| **Cloud SQL** | `db-f1-micro` + 10 GB SSD storage | N/A | ~$10.50 / month |
| **Cloud Run (API & Worker)** | Max 3 instances, scaled to 0 | First 2M requests, 180k vCPU-s, 360k GiB-s free | ~$0.50 – $2.00 / month |
| **Cloud Run (Web Frontend)** | Max 2 instances, scaled to 0 | Covered under monthly free tier allowance | ~$0.00 – $1.00 / month |
| **Cloud Tasks** | 3 queues | First 1M operations/month free ($0.40/M after) | ~$0.00 / month |
| **Cloud Scheduler** | 4 jobs | 3 free jobs per billing account ($0.10/job after) | ~$0.10 / month |
| **Secret Manager** | 7 secrets | 6 secret versions and 10k API operations free | ~$0.10 / month |
| **Artifact Registry** | 1 repository | First 0.5 GB free (~1 GB total storage) | ~$0.10 / month |
| **Cloud Logging** | Standard system logs | First 50 GB log ingestion per month free | ~$0.00 / month |
| **Egress Bandwidth** | Low-volume webhooks & UI | Standard GCP egress allowance | ~$0.20 – $1.00 / month |
| **Total Projected Monthly Cost** | | | **USD 11.40 – 14.80 / month** |

> [!NOTE]  
> Budget alerts notify administrators when thresholds are exceeded; they do not automatically shut down resources. Setting maximum container instance counts (API max 3, Frontend max 2) guarantees a hard cost ceiling.

---

## 5. Maximum Instance Counts & Quota Checks

- **Cloud Run API:** Max instances = **3** (Prevents connection pool exhaustion on `db-f1-micro`).
- **Cloud Run Frontend:** Max instances = **2**.
- **Database Connection Sizing:**  
  `pool_size = 5`, `max_overflow = 5` per container. Max 3 containers * 10 connections = 30 max connections, safely within `db-f1-micro` limit (50 connections).
- **Cloud Run Concurrency:** 80 requests/instance.
- **Request Timeout:** 300 seconds.

---

## 6. Required Secrets Specification

All 7 secrets must be created via Google Secret Manager. Values must be high-entropy and generated out-of-band:

| Secret Name | Purpose | Recommended Length | Generation Command |
|---|---|---|---|
| `physio-staging-db-password` | Cloud SQL PostgreSQL password for `physio_admin` | 32 hex chars | `openssl rand -hex 16` |
| `physio-staging-app-secret` | Application cryptographic master secret | 64 hex chars | `openssl rand -hex 32` |
| `physio-staging-jwt-secret` | JWT signing secret for staff sessions | 64 hex chars | `openssl rand -hex 32` |
| `physio-staging-worker-token` | Internal fallback worker token (`X-Worker-Token`) | 32 hex chars | `openssl rand -hex 16` |
| `physio-staging-whatsapp-token` | Staging WhatsApp API Bearer token | Staging token | Dummy or test token |
| `physio-staging-whatsapp-app-secret` | WhatsApp App Secret for HMAC webhook verification | Meta App Secret | Staging Meta App Secret |
| `physio-staging-llm-key` | LLM Gateway API key (OpenAI / Anthropic / Gemini) | Provider key | Staging API test key |

---

## 7. Required IAM Permissions for Deploying Operator

The human operator running the deployment script must possess the following roles on the target GCP project:
- `roles/owner` **OR** the following least-privilege combination:
  - `roles/resourcemanager.projectIamAdmin` (Grant IAM roles to service accounts)
  - `roles/serviceusage.serviceUsageAdmin` (Enable required Google APIs)
  - `roles/run.admin` (Deploy Cloud Run services and jobs)
  - `roles/cloudsql.admin` (Provision Cloud SQL instances and users)
  - `roles/cloudtasks.admin` (Create Cloud Tasks queues)
  - `roles/cloudscheduler.admin` (Create Cloud Scheduler jobs)
  - `roles/secretmanager.admin` (Create Secret Manager containers)
  - `roles/artifactregistry.admin` (Create Docker repositories and push images)

---

## 8. Deployment Sequence (Step-by-Step)

```bash
# ------------------------------------------------------------------------------
# STEP 1: Operator Environment Setup
# ------------------------------------------------------------------------------
export PROJECT_ID="YOUR_STAGING_PROJECT_ID"
export REGION="asia-south1"
gcloud config set project "$PROJECT_ID"

# ------------------------------------------------------------------------------
# STEP 2: Secret Manager Out-of-Band Population
# ------------------------------------------------------------------------------
# 1. db-password
DB_PASS=$(openssl rand -hex 16)
gcloud secrets create physio-staging-db-password --replication-policy=automatic
echo -n "$DB_PASS" | gcloud secrets versions add physio-staging-db-password --data-file=-

# 2. app-secret
echo -n "$(openssl rand -hex 32)" | gcloud secrets create physio-staging-app-secret --replication-policy=automatic --data-file=-

# 3. jwt-secret
echo -n "$(openssl rand -hex 32)" | gcloud secrets create physio-staging-jwt-secret --replication-policy=automatic --data-file=-

# 4. worker-token
echo -n "$(openssl rand -hex 16)" | gcloud secrets create physio-staging-worker-token --replication-policy=automatic --data-file=-

# 5. whatsapp-token
echo -n "staging-test-token" | gcloud secrets create physio-staging-whatsapp-token --replication-policy=automatic --data-file=-

# 6. whatsapp-app-secret
echo -n "staging-test-app-secret" | gcloud secrets create physio-staging-whatsapp-app-secret --replication-policy=automatic --data-file=-

# 7. llm-key
echo -n "staging-test-llm-key" | gcloud secrets create physio-staging-llm-key --replication-policy=automatic --data-file=-

# ------------------------------------------------------------------------------
# STEP 3: Container Image Build and Push
# ------------------------------------------------------------------------------
gcloud auth configure-docker "${REGION}-docker.pkg.dev"
REPO="${REGION}-docker.pkg.dev/${PROJECT_ID}/physio-staging"
COMMIT=$(git rev-parse --short HEAD)

docker build -t "${REPO}/api:${COMMIT}" -f docker/Dockerfile.api .
docker push "${REPO}/api:${COMMIT}"

docker build -t "${REPO}/frontend:${COMMIT}" -f docker/Dockerfile.frontend .
docker push "${REPO}/frontend:${COMMIT}"

# ------------------------------------------------------------------------------
# STEP 4: Terraform Infrastructure Provisioning
# ------------------------------------------------------------------------------
cd infra/staging
terraform init
terraform plan \
  -var="project_id=${PROJECT_ID}" \
  -var="region=${REGION}" \
  -var="env=staging" \
  -var="api_image=${REPO}/api:${COMMIT}" \
  -var="frontend_image=${REPO}/frontend:${COMMIT}" \
  -out=staging.tfplan

# Review plan output -> Apply
terraform apply staging.tfplan

# Set Cloud SQL user password matching Secret Manager
gcloud sql users set-password physio_admin \
  --instance="physio-staging-pg" \
  --password="$DB_PASS"

# ------------------------------------------------------------------------------
# STEP 5: Database Migration Execution
# ------------------------------------------------------------------------------
# Execute one-shot migration job
gcloud run jobs execute physio-staging-worker-once \
  --region="${REGION}" \
  --wait
```

---

## 9. Staging Verification Steps

Once deployed, verify platform health via the following smoke test sequence:

```bash
API_URL=$(gcloud run services describe physio-staging-api --region=asia-south1 --format="value(status.url)")
WEB_URL=$(gcloud run services describe physio-staging-web --region=asia-south1 --format="value(status.url)")

# 1. API Health Check
curl -f "${API_URL}/health"
# Expected response: {"status":"healthy","app_name":"Physio One WhatsApp AI Agent","environment":"staging","version":"1.0.0-draft"}

# 2. Check Owner Setup Status
curl -f "${API_URL}/api/v1/auth/setup-status"
# Expected response: {"is_initialized":false,"owner_count":0}

# 3. Initialize First Owner Account
curl -X POST "${API_URL}/api/v1/auth/setup" \
  -H "Content-Type: application/json" \
  -d '{"email":"owner@physioone.com","password":"StagingPassword2026#","full_name":"Clinic Owner"}'
# Expected response: HTTP 201 Created with User object and Set-Cookie session headers

# 4. Verify Second Setup Attempt is Blocked
curl -X POST "${API_URL}/api/v1/auth/setup" \
  -H "Content-Type: application/json" \
  -d '{"email":"hacker@test.com","password":"StagingPassword2026#","full_name":"Attacker"}'
# Expected response: HTTP 403 Forbidden ("System is already initialized with an active Owner.")

# 5. Verify Meta Webhook Challenge Handshake
curl "${API_URL}/api/v1/webhooks/whatsapp/meta?hub.mode=subscribe&hub.challenge=778899&hub.verify_token=staging-test-token"

# 6. Verify Outbound Messaging Kill-Switch is Active
# Confirm AUTOMATION_OUTBOUND_ENABLED is false in Cloud Run environment:
gcloud run services describe physio-staging-api --region=asia-south1 --format="yaml(spec.template.spec.containers[0].env)"
```

---

## 10. Emergency Rollback Procedures & Kill-Switches

### 10.1 Instant Outbound Messaging Shutdown
If any anomalous message dispatch is observed, immediately execute:
```bash
gcloud run services update physio-staging-api \
  --region=asia-south1 \
  --update-env-vars AUTOMATION_OUTBOUND_ENABLED=false
```

### 10.2 Fast Cloud Run Revision Rollback
To instantly divert 100% of user traffic back to the prior stable revision:
```bash
PREV_REV=$(gcloud run revisions list --service=physio-staging-api --region=asia-south1 --format="value(name)" --limit=2 | sed -n '2p')
gcloud run services update-traffic physio-staging-api \
  --region=asia-south1 \
  --to-revisions="${PREV_REV}=100"
```

### 10.3 Complete Staging De-provisioning
To destroy all cloud staging resources and eliminate all ongoing costs:
```bash
cd infra/staging
terraform destroy \
  -var="project_id=${PROJECT_ID}" \
  -var="region=${REGION}" \
  -var="env=staging" \
  -var="api_image=${REPO}/api:${COMMIT}" \
  -var="frontend_image=${REPO}/frontend:${COMMIT}"
```

---

## 11. Database Backup & Disaster Recovery Strategy

1. **Automated Daily Backups:** Cloud SQL `backup_configuration.enabled = true` takes automated daily backups retained according to Google standard backup retention.
2. **On-Demand Snapshot Pre-Migration:**
   Before running any future migration:
   ```bash
   gcloud sql backups create --instance=physio-staging-pg --description="pre-migration-snapshot"
   ```
3. **Point-in-Time Recovery (PITR):** Supported within the backup retention window.

---

## 12. Operator Sign-Off & Approval Checklist

Before proceeding with Task 17 or any real cloud deployment, the operator must complete and sign this checklist:

- [ ] GCP Project ID supplied and confirmed: `____________________________`
- [ ] Billing linked and budget alert set at USD 35.00 ceiling.
- [ ] Operator verified that no real patient WhatsApp numbers or production credentials will be used in staging.
- [ ] Outbound messaging kill-switch verified (`AUTOMATION_OUTBOUND_ENABLED=false`).
- [ ] AI Receptionist mode verified in Mode A / Disabled mode.
- [ ] Staging cost estimate (USD 11.40–14.80/month) reviewed and approved.
- [ ] Cloud SQL connection security (socket volume + IAM) reviewed and approved.
- [ ] Formal authorization granted to execute Terraform plan & apply.

**Operator Signature:** `___________________________`  
**Date:** `____-____-2026`
