#!/usr/bin/env bash
# ==============================================================================
# Physio One WhatsApp AI Platform — Host PostgreSQL Backup Runner
# Target: Host PostgreSQL 16 on Hostinger VPS
# Usage: ./scripts/backup_host_db.sh [--pre-deploy] [--dry-run]
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VPS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${VPS_DIR}"

if [[ -f .env ]]; then
    source .env
fi

BACKUP_DIR="${BACKUP_DIR:-/opt/physio/backups}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
PREFIX="physio_host_backup"
DRY_RUN=false

for arg in "$@"; do
    if [[ "$arg" == "--pre-deploy" ]]; then
        PREFIX="pre_deploy_host_backup"
    elif [[ "$arg" == "--dry-run" ]]; then
        DRY_RUN=true
    fi
done

echo "=================================================================="
echo " PHYSIO ONE — HOST POSTGRESQL BACKUP RUNNER"
echo " Target DB:       ${POSTGRES_DB:-physio_db}"
echo " Backup Dir:      ${BACKUP_DIR}"
echo " Retention Days:  ${BACKUP_RETENTION_DAYS}"
echo " Dry-Run Mode:    ${DRY_RUN}"
echo "=================================================================="

info()  { echo -e "\033[0;34m[INFO]\033[0m  $*"; }
pass()  { echo -e "\033[0;32m[PASS]\033[0m  $*"; }
fail()  { echo -e "\033[0;31m[FAIL]\033[0m  $*" >&2; exit 1; }

# 1. Directory and Permissions Check
if [[ "${DRY_RUN}" == "true" ]]; then
    info "[DRY-RUN] Would create backup directory: ${BACKUP_DIR} (chmod 700)"
else
    mkdir -p "${BACKUP_DIR}"
    chmod 700 "${BACKUP_DIR}"
fi

BACKUP_FILE="${BACKUP_DIR}/${PREFIX}_${TIMESTAMP}.sql.gz"

# 2. Check Host PostgreSQL Readiness
if [[ "${DRY_RUN}" == "true" ]]; then
    info "[DRY-RUN] Would check pg_isready on host port 5432"
    info "[DRY-RUN] Would execute pg_dump on ${POSTGRES_DB:-physio_db} | gzip -9 > ${BACKUP_FILE}"
    pass "[DRY-RUN] Backup simulation completed."
    exit 0
fi

info "Checking if PostgreSQL 16 is responding on host..."
if ! pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1 && ! sudo -u postgres pg_isready >/dev/null 2>&1; then
    fail "PostgreSQL is not accepting connections on host port 5432."
fi
pass "Host PostgreSQL is responsive."

# 3. Stream Compressed pg_dump
info "Streaming compressed PostgreSQL dump to: ${BACKUP_FILE}..."
if command -v PGPASSWORD >/dev/null 2>&1 || [[ -n "${POSTGRES_PASSWORD:-}" ]]; then
    export PGPASSWORD="${POSTGRES_PASSWORD:-}"
    pg_dump -h 127.0.0.1 -p 5432 -U "${POSTGRES_USER:-physio_user}" -d "${POSTGRES_DB:-physio_db}" \
        --clean --if-exists --no-owner --no-privileges \
        | gzip -9 > "${BACKUP_FILE}"
    unset PGPASSWORD
else
    # Fallback to sudo -u postgres if running locally as operator
    sudo -u postgres pg_dump -d "${POSTGRES_DB:-physio_db}" \
        --clean --if-exists --no-owner --no-privileges \
        | gzip -9 > "${BACKUP_FILE}"
fi

chmod 600 "${BACKUP_FILE}"
FILE_SIZE=$(du -h "${BACKUP_FILE}" | awk '{print $1}')
SHA256_HASH=$(sha256sum "${BACKUP_FILE}" | awk '{print $1}')

pass "Backup completed successfully!"
info "File:     ${BACKUP_FILE}"
info "Size:     ${FILE_SIZE}"
info "SHA256:   ${SHA256_HASH}"

# 4. Enforce Retention
info "Enforcing retention policy (${BACKUP_RETENTION_DAYS} days)..."
DELETED_COUNT=0
while IFS= read -r OLD_FILE; do
    if [[ -n "${OLD_FILE}" ]]; then
        rm -f "${OLD_FILE}"
        info "Removed expired backup: ${OLD_FILE}"
        DELETED_COUNT=$((DELETED_COUNT + 1))
    fi
done < <(find "${BACKUP_DIR}" -name "${PREFIX}_*.sql.gz" -type f -mtime +"${BACKUP_RETENTION_DAYS}" 2>/dev/null || true)

pass "Retention policy enforced. Removed ${DELETED_COUNT} expired backups."
