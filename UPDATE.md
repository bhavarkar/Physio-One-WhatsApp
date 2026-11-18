# UPDATE & LIFECYCLE MANAGEMENT: Single Organization Edition

## 1. Centralized Version Management & SemVer Strategy
The WhatsApp AI Agent platform strictly adheres to **Semantic Versioning (SemVer 2.0.0)**:
- **MAJOR (`X.0.0`)**: Breaking database changes, fundamental architectural shifts, or major framework upgrades.
- **MINOR (`1.X.0`)**: Backwards-compatible new features, new agent tools, or new UI dashboards.
- **PATCH (`1.0.X`)**: Backwards-compatible bug fixes, security patches, or LLM prompt refinements.

### Centralized Version Manifest (`version.json`)
Located at the root of the project:
```json
{
  "version": "1.0.0",
  "build_date": "2026-11-13",
  "min_compatible_db_version": "1.0.0",
  "release_notes_url": "https://github.com/organization/physio-one-agent/releases/tag/v1.0.0",
  "schema_version": 1
}
```

---

## 2. Inviolable Data Protection Rules

During any software update, upgrade, or rollback:
1. **NEVER DELETE CONVERSATIONS**: Existing WhatsApp conversations and messages must remain intact.
2. **NEVER DELETE PATIENT RECORDS**: Patient profiles, contact mappings, and consent flags are permanent clinical assets.
3. **NEVER DELETE CAMPAIGN HISTORY**: Historical campaign broadcasts and conversion metrics must persist.
4. **NEVER RESET USER ACCOUNTS**: Staff passwords and roles must survive migrations unchanged.
5. **NEVER OVERWRITE CONFIGURATION**: Production `.env` files and clinic settings must never be replaced by defaults.
6. **NEVER RESET POSTGRES VOLUMES**: Docker persistent volumes (`postgres_data`) must never be purged.
7. **NEVER DROP USER DATA COLUMNS**: Do not perform destructive SQL `DROP COLUMN` on columns with active user data.

---

## 3. Database Migration Strategy: Expand-and-Contract

To guarantee zero downtime and safe rollbacks, all Alembic database migrations must use the **Expand-and-Contract** methodology:

```
Phase 1 (Current): Version 1.0.0 uses column `old_col`.
Phase 2 (Expand):  Version 1.1.0 adds `new_col` nullable. Both written.
Phase 3 (Migrate): Backfill script copies data from `old_col` to `new_col`.
Phase 4 (Contract): Next major release removes `old_col` only after verification.
```

- **Forward-Compatible Schema**: Every migration must be forward-compatible with the immediately preceding application version.
- **No Automatic Downgrades**: Database down-migrations are disabled automatically in production to prevent accidental loss of freshly written data.

---

## 4. Automated 10-Step Update Pipeline

When an update is initiated from the UI or via `scripts/update.sh`:

```mermaid
flowchart TD
    S1[1. Check for New Release Tag] --> S2[2. Display Diff & Release Notes]
    S2 --> S3[3. Create Pre-Update DB Backup via pg_dump]
    S3 --> S4{4. Verify Backup Integrity}
    S4 -->|Backup Valid| S5[5. Pull Target Docker Images]
    S4 -->|Backup Failed| ABORT[ABORT UPDATE & Alert Admin]
    S5 --> S6[6. Apply Alembic Migrations]
    S6 --> S7[7. Restart API & Worker Services]
    S7 --> S8[8. Execute Container Health Checks]
    S8 -->|Healthy| S9[9. Record Successful Update in DB]
    S8 -->|Failed| S10[10. Initiate Automatic Rollback Protocol]
```

### Detailed Pipeline Steps:
1. **Probe Remote Release**: Queries the version endpoint/registry for newer tags.
2. **Display Changelog**: Displays release notes and any operator intervention requirements.
3. **Automated Database Snapshot**: Runs `scripts/backup.sh` generating an encrypted timestamped dump in `/backups/pre-upgrade-vX.Y.Z-<timestamp>.sql.gz`.
4. **Backup Verification**: Verifies the backup archive size (> 0 bytes) and gzip integrity before proceeding.
5. **Image Pulling**: Pulls version-tagged Docker images (e.g. `physio-one-api:v1.1.0`).
6. **Execute Migrations**: Runs `alembic upgrade head` inside the API container.
7. **Service Rolling Restart**: Restarts `worker`, `scheduler`, and `api` sequentially.
8. **Automated Health Checks**: Pings `/api/v1/health` and verifies Celery worker responsiveness.
9. **Log Success**: Updates `system_settings` with new version string and timestamp.
10. **Automated Rollback (On Failure)**: If health checks fail within 120 seconds, the update runner automatically:
    - Stops the new containers.
    - Reverts the Docker tag to the previous version.
    - Restarts the previous stable containers.
    - Preserves the database and alerts the Super Admin.

---

## 5. Upgrade & Disaster Recovery Scripts

- `scripts/backup.sh`: Standalone script for one-command PostgreSQL and media backups.
- `scripts/restore.sh`: Interactive or headless point-in-time database restore script.
- `scripts/update.sh`: Host-level automated update orchestrator.
- `scripts/healthcheck.sh`: Comprehensive sanity check of all 6 containers, database connectivity, and Redis latency.

---

## 6. Cloud Run Revision Strategy for Staging & Production
In Google Cloud Run environments:
- Service deployments create immutable, versioned Revisions (e.g. `physio-staging-api-00002-abc`).
- Zero-downtime rolling traffic shift: traffic shifts to the new revision only after container startup probes (`/health`) pass.
- Instant rollback: traffic can be routed back to the prior stable revision in under 5 seconds via `gcloud run services update-traffic --to-revisions=PREV_REV=100`.
- Dedicated Database Migration Job (`physio-staging-db-migrate`): Runs `alembic upgrade head` as an isolated one-shot job over the Cloud SQL Unix socket before traffic shifts to the new revision, guaranteeing zero-downtime schema evolution.
- Bounded workers execute via Cloud Run Jobs (`physio-staging-worker-once`) without running persistent idle containers.
- Out-of-Band Cloud SQL Credential Lifecycle: Database user `physio_admin` is managed out-of-band via Secret Manager and `gcloud sql users create` (or `set-password`). Passwords are never serialized into `terraform.tfstate`. Password rotations are executed by adding a new secret version to `physio-staging-db-password`, running `gcloud sql users set-password`, and restarting Cloud Run revisions.
- Windows PowerShell 5.1 Deployment Lifecycle: Staging releases and updates are orchestrated via `scripts/deploy-staging.ps1`. The runner enforces an 11-phase acyclic sequence, validates prerequisites, runs dedicated migrations before promoting traffic, leaves background schedulers dormant until explicit Phase 11 activation, and provides non-destructive `-DryRun` simulation. Automated health and readiness checks are verified via `scripts/verify-staging.ps1`.

---

## 7. Hostinger Ubuntu Linux VPS Lifecycle Management & Updates (Active)

For the active Hostinger Ubuntu Linux VPS Docker Compose target:
- **Application Updates via `deploy/vps/scripts/deploy.sh`**:
  - Updates follow a strict 8-stage sequence:
    1. Preflight sanity check (`deploy/vps/scripts/preflight.sh`).
    2. Automated pre-update database snapshot (`deploy/vps/scripts/backup.sh`) with gzip integrity and SHA256 verification.
    3. Docker image build / pull (`docker compose build`).
    4. Database container startup and health check wait (`docker compose up -d postgres`).
    5. Database schema migration runner (`deploy/vps/scripts/migrate.sh` running `docker compose run --rm migration alembic upgrade head`).
    6. Application and background worker startup (`docker compose up -d api worker`).
    7. Next.js frontend startup (`docker compose up -d frontend`).
    8. Caddy reverse proxy reload (`docker compose up -d caddy`).
- **Data Protection Invariant (Zero Down-Migrations)**:
  - If a deployment or update fails post-migration health checks, `deploy/vps/scripts/rollback.sh` reverts the container images to previous tags and enforces the emergency outbound kill switch.
  - The database schema is **never automatically downgraded** to prevent irreversible loss of newly committed data.
  - Full point-in-time database restoration is performed manually by the operator using `deploy/vps/scripts/restore.sh` with the explicit `--confirm-restore` safety gate.
- **Automated Backup Rotation**:
  - `deploy/vps/scripts/backup.sh` streams compressed dumps to `/opt/physio/backups/physio_backup_<timestamp>.sql.gz`.
  - Automatically purges backups older than 7 days, maintaining disk headroom on the 50 GB SSD.

---

## 8. Task 21 Rehearsal Verification & Safety Findings (2026-11-18)

- **Disposable Stack Integration Rehearsal**:
  - Successfully verified end-to-end upgrade simulation on a disposable stack without affecting active development or staging volumes.
  - Confirmed that Alembic migrations run cleanly to head (revisions 001–008 generating 64 public tables), Caddy reliably proxies unified port 80/443 ingress, and container restarts preserve database volume contents.
- **Queue Concurrency & Race Condition Elimination**:
  - Hardened database queue transactions in `automation_worker.py`, `inbound_queue.py`, and `campaign_service.py` with `.with_for_update(skip_locked=True)`.
  - Proved atomic locking under concurrent worker polling across 7 integration test scenarios (`test_vps_queue_concurrency_and_reliability.py`).
- **Disaster Recovery Integrity Test**:
  - Streamed `pg_dump` with gzip compression and verified archive integrity with `gzip -t`.
  - Restored backup into a clean test database and confirmed that 64 tables and pgvector extension (0.8.7) were fully recovered.
- **Resource Budget Ground Truth**:
  - Measured live idle container consumption: Total **323 MiB** across 5 containers, leaving ~1.6 GB headroom for OS and system buffers on a 4 GB Hostinger VPS.
- **Hostinger Preflight Checklist**:
  - Authored `deploy/vps/HOSTINGER_PREFLIGHT_CHECKLIST.md` specifying read-only preflight commands for Task 22 server inspection.


