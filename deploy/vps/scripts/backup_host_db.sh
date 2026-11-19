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
PRE_DEPLOY=false

for arg in "$@"; do
    if [[ "$arg" == "--pre-deploy" ]]; then
        PREFIX="pre_deploy_host_backup"
        PRE_DEPLOY=true
    elif [[ "$arg" == "--dry-run" ]]; then
        DRY_RUN=true
    fi
done

TARGET_DB="${POSTGRES_DB:-physio_db}"

echo "=================================================================="
echo " PHYSIO ONE — HOST POSTGRESQL BACKUP RUNNER"
echo " Target DB:       ${TARGET_DB}"
echo " Backup Dir:      ${BACKUP_DIR}"
echo " Retention Days:  ${BACKUP_RETENTION_DAYS}"
echo " Dry-Run Mode:    ${DRY_RUN}"
echo "=================================================================="

info()  { echo -e "\033[0;34m[INFO]\033[0m  $*"; }
pass()  { echo -e "\033[0;32m[PASS]\033[0m  $*"; }
warn()  { echo -e "\033[0;33m[WARN]\033[0m  $*"; }
fail()  { echo -e "\033[0;31m[FAIL]\033[0m  $*" >&2; exit 1; }

# 1. Directory and Permissions Check
if [[ "${DRY_RUN}" == "true" ]]; then
    info "[DRY-RUN] Would create backup directory: ${BACKUP_DIR} (chmod 700)"
else
    mkdir -p "${BACKUP_DIR}"
    chmod 700 "${BACKUP_DIR}"
fi

BACKUP_FILE="${BACKUP_DIR}/${PREFIX}_${TIMESTAMP}.sql.gz"

# 2. Check Host PostgreSQL Readiness & Target DB Existence
if [[ "${DRY_RUN}" == "true" ]]; then
    info "[DRY-RUN] Would check PostgreSQL connectivity via Unix socket or localhost"
    info "[DRY-RUN] Would execute pg_dump on ${TARGET_DB} | gzip -9 > ${BACKUP_FILE}"
    pass "[DRY-RUN] Backup simulation completed."
    exit 0
fi

info "Checking if PostgreSQL 16 is responding on host..."
SOCKET_PATH="/var/run/postgresql/.s.PGSQL.5432"
PG_READY=false

if [[ -S "${SOCKET_PATH}" ]] && pg_isready -h /var/run/postgresql -p 5432 >/dev/null 2>&1; then
    PG_READY=true
    PG_HOST_ARG="-h /var/run/postgresql"
elif pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
    PG_READY=true
    PG_HOST_ARG="-h 127.0.0.1"
elif sudo -u postgres pg_isready >/dev/null 2>&1; then
    PG_READY=true
    PG_HOST_ARG=""
fi

if [[ "${PG_READY}" != "true" ]]; then
    fail "PostgreSQL 16 is not accepting connections via Unix socket or TCP."
fi
pass "Host PostgreSQL is responsive."

# Check if target database exists
DB_EXISTS=false
if sudo -u postgres psql -t -A -c "SELECT 1 FROM pg_database WHERE datname='${TARGET_DB}'" 2>/dev/null | grep -q "1"; then
    DB_EXISTS=true
fi

if [[ "${DB_EXISTS}" != "true" ]]; then
    if [[ "${PRE_DEPLOY}" == "true" ]]; then
        info "Database '${TARGET_DB}' does not exist yet (clean initialization). Skipping pre-deploy backup."
        exit 0
    else
        fail "Database '${TARGET_DB}' does not exist. Cannot execute backup."
    fi
fi

# 3. Stream Compressed pg_dump
info "Streaming compressed PostgreSQL dump to: ${BACKUP_FILE}..."
if command -v PGPASSWORD >/dev/null 2>&1 && [[ -n "${POSTGRES_PASSWORD:-}" ]]; then
    export PGPASSWORD="${POSTGRES_PASSWORD}"
    pg_dump ${PG_HOST_ARG} -p 5432 -U "${POSTGRES_USER:-physio_user}" -d "${TARGET_DB}" \
        --clean --if-exists --no-owner --no-privileges \
        | gzip -9 > "${BACKUP_FILE}"
    unset PGPASSWORD
else
    # Fallback to sudo -u postgres peer dump if password not set in environment
    sudo -u postgres pg_dump -d "${TARGET_DB}" \
        --clean --if-exists --no-owner --no-privileges \
        | gzip -9 > "${BACKUP_FILE}"
fi

# 4. Verify Archive Integrity
if ! gzip -t "${BACKUP_FILE}"; then
    rm -f "${BACKUP_FILE}"
    fail "Backup verification failed! The created archive is corrupt."
fi

chmod 600 "${BACKUP_FILE}"
FILE_SIZE=$(du -h "${BACKUP_FILE}" | awk '{print $1}')
SHA256_HASH=$(sha256sum "${BACKUP_FILE}" | awk '{print $1}')

pass "Backup completed and integrity verified!"
info "File:     ${BACKUP_FILE}"
info "Size:     ${FILE_SIZE}"
info "SHA256:   ${SHA256_HASH}"

# 5. Enforce Retention
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
