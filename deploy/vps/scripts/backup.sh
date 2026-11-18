#!/usr/bin/env bash
# ==============================================================================
# Physio One WhatsApp AI Platform — Database Backup Runner
# Target: PostgreSQL 16 + pgvector on Hostinger VPS
# Usage: ./scripts/backup.sh [--pre-deploy] [--dry-run]
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VPS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${VPS_DIR}"

source .env

BACKUP_DIR="${BACKUP_DIR:-/opt/physio/backups}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
PREFIX="physio_backup"

if [[ "${1:-}" == "--pre-deploy" || "${2:-}" == "--pre-deploy" ]]; then
    PREFIX="pre_deploy_backup"
fi

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" || "${2:-}" == "--dry-run" ]]; then
    DRY_RUN=true
fi

echo "=================================================================="
echo " PHYSIO ONE — DATABASE BACKUP RUNNER"
echo " Target DB: ${POSTGRES_DB:-physio_one_db} on Container postgres"
echo " Backup Directory: ${BACKUP_DIR}"
echo " Retention: ${BACKUP_RETENTION_DAYS} days"
echo " Dry-Run Mode: ${DRY_RUN}"
echo "=================================================================="

info()  { echo -e "\033[0;34m[INFO]\033[0m  $*"; }
pass()  { echo -e "\033[0;32m[PASS]\033[0m  $*"; }
fail()  { echo -e "\033[0;31m[FAIL]\033[0m  $*" >&2; exit 1; }

# 1. Ensure Backup Directory Exists with Restricted Permissions
if [[ "${DRY_RUN}" == "true" ]]; then
    info "[DRY-RUN] Would create backup directory: ${BACKUP_DIR} with permissions 700"
else
    mkdir -p "${BACKUP_DIR}"
    chmod 700 "${BACKUP_DIR}"
fi

BACKUP_FILE="${BACKUP_DIR}/${PREFIX}_${TIMESTAMP}.sql.gz"

# 2. Check if PostgreSQL container is running
info "Checking if PostgreSQL container is running..."
if ! docker compose ps postgres | grep -q "Up\|healthy"; then
    info "PostgreSQL container is not running. Checking if backup is required..."
    if [[ "${PREFIX}" == "pre_deploy_backup" ]]; then
        info "No active database container found for pre-deploy backup. Skipping initial backup."
        exit 0
    else
        fail "PostgreSQL container is stopped. Cannot execute backup."
    fi
fi

# 3. Execute pg_dump and Gzip
if [[ "${DRY_RUN}" == "true" ]]; then
    info "[DRY-RUN] Would execute pg_dump on postgres container to ${BACKUP_FILE}"
    pass "[DRY-RUN] Backup simulation completed."
    exit 0
fi

info "Streaming compressed PostgreSQL dump to: ${BACKUP_FILE}..."
docker compose exec -T postgres pg_dump \
    -U "${POSTGRES_USER:-physio_admin}" \
    -d "${POSTGRES_DB:-physio_one_db}" \
    --clean --if-exists --no-owner --no-privileges \
    | gzip -9 > "${BACKUP_FILE}"

chmod 600 "${BACKUP_FILE}"
FILE_SIZE=$(du -h "${BACKUP_FILE}" | awk '{print $1}')
SHA256_HASH=$(sha256sum "${BACKUP_FILE}" | awk '{print $1}')

pass "Backup completed successfully!"
info "File:     ${BACKUP_FILE}"
info "Size:     ${FILE_SIZE}"
info "SHA256:   ${SHA256_HASH}"

# 4. Apply Local Retention Policy
info "Applying backup retention policy (${BACKUP_RETENTION_DAYS} days)..."
DELETED_COUNT=0
while IFS= read -r OLD_FILE; do
    if [[ -n "${OLD_FILE}" ]]; then
        rm -f "${OLD_FILE}"
        info "Removed expired backup: ${OLD_FILE}"
        DELETED_COUNT=$((DELETED_COUNT + 1))
    fi
done < <(find "${BACKUP_DIR}" -name "physio_backup_*.sql.gz" -type f -mtime +"${BACKUP_RETENTION_DAYS}" 2>/dev/null || true)

pass "Retention policy applied. Removed ${DELETED_COUNT} expired backups."
info "Recommendation: Replicate ${BACKUP_FILE} off-server via rsync/sftp to secure cold storage."
