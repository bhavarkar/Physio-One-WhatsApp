# Physio One WhatsApp AI Platform — Controlled Staging Deployment Runbook

**Environment:** Google Cloud Platform (GCP) — Isolated Staging  
**Organization:** Physio One Clinic (Single Organization Edition)  
**Region:** `asia-south1` (Mumbai)  
**Target Architecture:** Cloud Run (API & Frontend), Cloud SQL PostgreSQL 16 + pgvector, Cloud Tasks, Cloud Scheduler, Secret Manager  
**Estimated Monthly Cost:** USD 11–18/month (db-f1-micro + scale-to-zero compute)

---

## 1. Pre-Deployment Boundary & Approval Gate

> [!IMPORTANT]  
> **Mandatory Rule:** Do **NOT** deploy to Google Cloud, run `terraform apply`, or create billable GCP resources without explicit operator sign-off and approval. Production credentials must never be used in staging, and no real WhatsApp messages may be dispatched to actual patients during staging verification.

### Pre-Deployment Checklist
- [x] Backend tests pass: 187/187 tests passing.
- [x] Frontend tests pass: 53/53 tests passing.
- [x] TypeScript typecheck: 0 errors.
- [x] Next.js production build: 18/18 static routes compiled.
- [x] Docker Compose local verification: PostgreSQL 16 + pgvector, API, Worker, and Frontend operational.
- [x] Terraform staging IaC validated and formatted.
- [x] Safety defaults verified (`AUTOMATION_OUTBOUND_ENABLED=false`, AI Mode A read-only).

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

## 5. Terraform Infrastructure Provisioning

Navigate to `infra/staging/`:

```bash
cd infra/staging

# Initialize Terraform (remote backend bucket configured out-of-band)
terraform init -backend-config="bucket=YOUR_TF_STATE_BUCKET"

# Generate and review execution plan
terraform plan \
  -var="project_id=${PROJECT_ID}" \
  -var="region=asia-south1" \
  -var="env=staging" \
  -var="api_image=${REPO}/api:${COMMIT}" \
  -var="frontend_image=${REPO}/frontend:${COMMIT}" \
  -out=staging.tfplan

# Review the plan carefully: verify no destructive changes, zero public database IPs
# Apply after explicit operator confirmation
terraform apply staging.tfplan

# Set Cloud SQL user password matching Secret Manager
gcloud sql users set-password physio_admin \
  --instance="physio-staging-pg" \
  --password="$DB_PASS"
```

---

## 6. Database Migration Execution

Once Cloud SQL and Secret Manager are provisioned, execute database migrations using a one-shot Cloud Run Job or temporary migration container:

```bash
# Execute migration using the Cloud Run worker job image
gcloud run jobs execute physio-staging-worker-once \
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
