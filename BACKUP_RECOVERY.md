# Backup, Disaster Recovery & Data Retention Policy

**Organization:** Physio One Clinic  
**Edition:** Single Organization Edition  
**Compliance Standards:** HIPAA / Digital Personal Data Protection (DPDP) Act compliance for clinical records.

---

## 1. PostgreSQL Database Backup Architecture

Physio One uses Google Cloud SQL for PostgreSQL 16 with high availability and automated continuous archiving.

### 1.1 Automated Backups & Retention
- **Daily Automated Backups:** Configured at 03:00 IST (outside clinic hours).
- **Point-in-Time Recovery (PITR):** Write-Ahead Logs (WAL) retained for **7 days**. Allows restoring the database to any exact second within the last 7 days.
- **Backup Retention Window:** 30 daily snapshots retained before archival to Coldline GCS storage.
- **Location:** Redundant regional storage in `asia-south1` (Mumbai) with multi-region backup replication.

### 1.2 Point-in-Time Recovery (PITR) Execution Procedure

To recover the database to a specific timestamp before an operational error or corruption:

```bash
# 1. Identify target recovery timestamp (UTC or IST)
RECOVERY_TIME="2026-11-15T02:00:00Z"

# 2. Clone the Cloud SQL instance to a new instance at target timestamp
gcloud sql instances clone physio-postgres physio-postgres-restored \
    --point-in-time "${RECOVERY_TIME}" \
    --project ${PROJECT_ID}

# 3. Verify data integrity on the restored instance
gcloud sql connect physio-postgres-restored --user=physio_admin
```

```sql
-- Verify table counts and latest records
SELECT COUNT(*) FROM appointments;
SELECT COUNT(*) FROM patients;
SELECT MAX(created_at) FROM whatsapp_messages;
```

```bash
# 4. Point Cloud Run API service to the restored instance via Secret Manager
gcloud secrets versions add physio-db-host --data-file=<(echo -n "physio-postgres-restored")
```

---

## 2. pgvector Re-indexing & Knowledge Base Recovery

If vector indexes become corrupted or document embeddings need recreation:

```sql
-- 1. Re-build HNSW vector cosine index
REINDEX INDEX idx_kb_chunks_embedding;

-- 2. Verify vector index health
SELECT schemaname, tablename, indexname, idx_scan 
FROM pg_stat_user_indexes 
WHERE indexname = 'idx_kb_chunks_embedding';
```

If document chunks need complete re-embedding:
```bash
# Run deterministic re-indexing script
python -m app.services.knowledge_service --reindex-all
```

---

## 3. Media Storage & Clinical Assets Replication

- **Clinical Media & Instagram Reels:** Stored in Cloud Storage (`gs://physio-one-media-storage`).
- **Object Versioning:** Enabled with 30-day noncurrent version retention to protect against accidental deletions.
- **Replication:** Dual-region storage (`asia1` - Mumbai and Delhi) for 99.999999999% (11 9's) durability.

---

## 4. Disaster Recovery (DR) Drill Runbook

An annual disaster recovery simulation must be performed:

1. **Pre-drill Notification:** Technical team notifies clinic operations that a drill is taking place in an isolated staging project.
2. **Synthetic Data Injection:** 1,000 synthetic patient records, 5,000 conversations, and 500 appointments are seeded.
3. **Simulated Outage:** Target database instance is terminated.
4. **Restoration:** Cloud SQL PITR clone is triggered and verified.
5. **RTO / RPO Targets:**
   - **RTO (Recovery Time Objective):** < 45 minutes to restore full clinic operations.
   - **RPO (Recovery Point Objective):** < 5 minutes of data loss (governed by Cloud SQL WAL streaming).
