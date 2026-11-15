# Production Deployment Guide: Physio One WhatsApp AI Platform

**Target Architecture:** Google Cloud Platform (Cloud Run, Cloud Tasks, Cloud Scheduler, Cloud SQL for PostgreSQL with pgvector, Secret Manager).  
**Edition:** Single Organization Edition (Physio One Clinic).  
**Audience:** Platform Engineers, Site Reliability Engineers, and Clinic Technical Administrators.

---

## 1. Architectural Overview

```
                                  [Meta / YCloud Webhooks]
                                             │
                                             ▼
                                  ┌───────────────────────┐
                                  │   Cloud Run (API)     │
                                  │  FastAPI Backend      │
                                  └──────────┬────────────┘
                                             │
                       ┌─────────────────────┴─────────────────────┐
                       ▼                                           ▼
            ┌───────────────────────┐                   ┌─────────────────────┐
            │      Cloud Tasks      │                   │   Cloud Scheduler   │
            │   (Inbound Debounce   │                   │ (15m Automation &   │
            │  & Outbound Delivery) │                   │  30m Campaign Scan) │
            └──────────┬────────────┘                   └──────────┬──────────┘
                       │                                           │
                       │ Authenticated via Google OIDC Token       │ Authenticated via Google OIDC Token
                       │ (Service Account: physio-one-worker)      │ (Service Account: physio-one-worker)
                       ▼                                           ▼
            ┌─────────────────────────────────────────────────────────────────┐
            │            Cloud Run (Worker Endpoints / Daemon)               │
            │   POST /api/v1/automations/process-due                          │
            │   POST /api/v1/automations/scan-inactivity                      │
            │   POST /api/v1/campaigns/worker/run                             │
            │   POST /api/v1/ai-inbound/process-due                           │
            └────────────────────────────────┬────────────────────────────────┘
                                             │
                     ┌───────────────────────┴───────────────────────┐
                     ▼                                               ▼
          ┌─────────────────────┐                         ┌─────────────────────┐
          │      Cloud SQL      │                         │    Cloud Storage    │
          │  PostgreSQL 16 +    │                         │  Encrypted Media &  │
          │  pgvector (HNSW)    │                         │  Document Assets    │
          └─────────────────────┘                         └─────────────────────┘
```

---

## 2. Service Accounts & IAM Roles

The deployment enforces the principle of least privilege using dedicated Google Cloud service accounts.

### 2.1 Service Account: `physio-one-api@<PROJECT_ID>.iam.gserviceaccount.com`
- **Role:** `roles/cloudsql.client` (Connect to Cloud SQL instance via Cloud SQL Auth Proxy).
- **Role:** `roles/secretmanager.secretAccessor` (Read encrypted API tokens, DB credentials, APP_SECRET).
- **Role:** `roles/cloudtasks.enqueuer` (Enqueue debounced and delayed worker tasks).
- **Role:** `roles/storage.objectAdmin` (Read/write clinical media and knowledge base chunks to GCS bucket).

### 2.2 Service Account: `physio-one-worker@<PROJECT_ID>.iam.gserviceaccount.com`
- **Role:** `roles/run.invoker` (Invoke authenticated worker routes on Cloud Run).
- **Role:** `roles/cloudtasks.taskDeleter` (Manage retries and dead-letter tasks).

---

## 3. Secret Manager Configuration

All sensitive credentials must be stored in Google Cloud Secret Manager and mounted as environment variables:

| Secret Name | Description | Cloud Run Env Var |
|---|---|---|
| `physio-db-password` | PostgreSQL database user password | `POSTGRES_PASSWORD` |
| `physio-app-secret` | 64-char cryptographic encryption master key | `APP_SECRET` |
| `physio-jwt-secret` | HMAC key for dashboard sessions | `JWT_SECRET_KEY` |
| `physio-worker-secret-token` | Internal fallback worker secret token | `AUTOMATION_WORKER_SECRET_TOKEN` |
| `physio-whatsapp-access-token` | Meta Cloud API permanent system user token | `WHATSAPP_ACCESS_TOKEN` |
| `physio-whatsapp-app-secret` | Meta App Secret for webhook HMAC-SHA256 validation | `WHATSAPP_APP_SECRET` |
| `physio-llm-api-key` | API Key for primary LLM provider (Muse / OpenAI) | `MUSE_API_KEY` |

---

## 4. Cloud Run Services Deployment

### 4.1 Backend API Service (`physio-one-api`)

Deploy the FastAPI container image to Cloud Run with automatic scaling:

```bash
gcloud run deploy physio-one-api \
    --image gcr.io/${PROJECT_ID}/physio-one-api:${GIT_SHA} \
    --region asia-south1 \
    --platform managed \
    --memory 1Gi \
    --cpu 1 \
    --min-instances 1 \
    --max-instances 10 \
    --service-account physio-one-api@${PROJECT_ID}.iam.gserviceaccount.com \
    --add-cloudsql-instances ${PROJECT_ID}:asia-south1:physio-postgres \
    --set-env-vars ENVIRONMENT=staging,PORT=8000,CLOUD_RUN_SERVICE_URL=https://api.staging.physioone.in,OIDC_AUDIENCE=https://api.staging.physioone.in,WORKER_SERVICE_ACCOUNT_EMAIL=physio-one-worker@${PROJECT_ID}.iam.gserviceaccount.com,REQUIRE_OIDC_IN_PRODUCTION=true \
    --set-secrets POSTGRES_PASSWORD=physio-db-password:latest,APP_SECRET=physio-app-secret:latest,JWT_SECRET_KEY=physio-jwt-secret:latest,AUTOMATION_WORKER_SECRET_TOKEN=physio-worker-secret-token:latest,WHATSAPP_ACCESS_TOKEN=physio-whatsapp-access-token:latest,WHATSAPP_APP_SECRET=physio-whatsapp-app-secret:latest,MUSE_API_KEY=physio-llm-api-key:latest \
    --no-allow-unauthenticated
```

*Note: For public webhook endpoints (`/api/v1/webhook/whatsapp`), configure a Google Cloud Load Balancer with Cloud Armor WAF or allow unauthenticated traffic while relying on Meta signature validation.*

### 4.2 Frontend Next.js Service (`physio-one-dashboard`)

Deploy the production-built Next.js application:

```bash
gcloud run deploy physio-one-dashboard \
    --image gcr.io/${PROJECT_ID}/physio-one-frontend:${GIT_SHA} \
    --region asia-south1 \
    --platform managed \
    --memory 512Mi \
    --cpu 1 \
    --min-instances 1 \
    --max-instances 5 \
    --set-env-vars NODE_ENV=production,INTERNAL_API_URL=https://api.staging.physioone.in,NEXT_PUBLIC_API_URL=https://api.staging.physioone.in \
    --allow-unauthenticated
```

---

## 5. Cloud Tasks Queue Configuration

Cloud Tasks provides durable queueing and rate-limiting for WhatsApp dispatches:

```bash
# 1. Inbound debouncing queue
gcloud tasks queues create physio-inbound-queue \
    --location asia-south1 \
    --max-concurrent-dispatches 10 \
    --max-dispatches-per-second 5 \
    --max-attempts 5

# 2. Outbound WhatsApp delivery queue (enforces Meta rate limits)
gcloud tasks queues create physio-outbound-queue \
    --location asia-south1 \
    --max-concurrent-dispatches 5 \
    --max-dispatches-per-second 2 \
    --max-attempts 3
```

---

## 6. Cloud Scheduler Jobs

Cloud Scheduler triggers periodic queue scans and worker cycles with verified OIDC service account authentication:

### 6.1 Scheduled Automation Worker (Every 1 Minute)
```bash
gcloud scheduler jobs create http physio-process-due-jobs \
    --location asia-south1 \
    --schedule "* * * * *" \
    --time-zone "Asia/Kolkata" \
    --uri "https://api.staging.physioone.in/api/v1/automations/process-due?limit=25" \
    --http-method POST \
    --oidc-service-account-email physio-one-worker@${PROJECT_ID}.iam.gserviceaccount.com \
    --oidc-token-audience "https://api.staging.physioone.in"
```

### 6.2 Inactivity Check-in Scanner (Every 15 Minutes)
```bash
gcloud scheduler jobs create http physio-scan-inactivity \
    --location asia-south1 \
    --schedule "*/15 * * * *" \
    --time-zone "Asia/Kolkata" \
    --uri "https://api.staging.physioone.in/api/v1/automations/scan-inactivity" \
    --http-method POST \
    --oidc-service-account-email physio-one-worker@${PROJECT_ID}.iam.gserviceaccount.com \
    --oidc-token-audience "https://api.staging.physioone.in"
```

### 6.3 Instagram Re-engagement Dispatch (Every 30 Minutes during 09:00 - 21:00 IST)
```bash
gcloud scheduler jobs create http physio-campaign-reengagement \
    --location asia-south1 \
    --schedule "*/30 9-20 * * *" \
    --time-zone "Asia/Kolkata" \
    --uri "https://api.staging.physioone.in/api/v1/campaigns/worker/run?limit=25" \
    --http-method POST \
    --oidc-service-account-email physio-one-worker@${PROJECT_ID}.iam.gserviceaccount.com \
    --oidc-token-audience "https://api.staging.physioone.in"
```

---

## 7. PostgreSQL Database Migration Pipeline

Migrations MUST be applied automatically during release deployment before routing traffic:

```bash
# Execute Cloud Build migration job
gcloud builds submit \
    --config=docker/cloudbuild-migration.yaml \
    --substitutions=_DATABASE_URL="postgresql+psycopg2://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${CLOUDSQL_IP}:5432/${POSTGRES_DB}"
```

**Verification step:**
```sql
SELECT version_num FROM alembic_version;
-- Expected head: 008_campaigns_instagram_reengagement
```
