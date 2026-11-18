#!/usr/bin/env bash
# ==============================================================================
# Physio One WhatsApp AI Platform — Database Restore Runner
# Target: PostgreSQL 16 + pgvector on Hostinger VPS
# Usage: ./scripts/restore.sh <path-to-backup.sql.gz> [--confirm-restore] [--dry-run]
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VPS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${VPS_DIR}"

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <path-to-backup.sql.gz> [--confirm-restore] [--dry-run]"
    exit 1
fi

BACKUP_FILE="$1"
CONFIRM=false
DRY_RUN=false

for arg in "$@"; do
    if [[ "$arg" == "--confirm-restore" ]]; then
        CONFIRM=true
    elif [[ "$arg" == "--dry-run" ]]; then
        DRY_RUN=true
    fi
done

source .env

echo "=================================================================="
echo " PHYSIO ONE — DATABASE RESTORE RUNNER"
echo " Backup File: ${BACKUP_FILE}"
echo " Target DB:   ${POSTGRES_DB:-physio_one_db}"
echo " Dry-Run Mode: ${DRY_RUN}"
echo "=================================================================="

info()  { echo -e "\033[0;34m[INFO]\033[0m  $*"; }
pass()  { echo -e "\033[0;32m[PASS]\033[0m  $*"; }
warn()  { echo -e "\033[0;33m[WARN]\033[0m  $*"; }
fail()  { echo -e "\033[0;31m[FAIL]\033[0m  $*" >&2; exit 1; }

# 1. Validate Backup File
info "Validating backup file existence..."
if [[ ! -f "${BACKUP_FILE}" ]]; then
    fail "Backup file '${BACKUP_FILE}' does not exist!"
fi

info "Testing gzip archive integrity..."
if ! gzip -t "${BACKUP_FILE}"; then
    fail "Gzip integrity test failed for '${BACKUP_FILE}'! Archive may be corrupt."
fi
pass "Backup archive integrity verified."

# 2. Check Confirmation Gate
if [[ "${DRY_RUN}" != "true" && "${CONFIRM}" != "true" ]]; then
    warn "=================================================================="
    warn " CRITICAL WARNING: DATABASE RESTORE OPERATION                      "
    warn " This will overwrite existing data in '${POSTGRES_DB}'!           "
    warn " Pass '--confirm-restore' flag to authorize restoration.          "
    warn "=================================================================="
    exit 1
fi

# 3. Check PostgreSQL Container
info "Checking if PostgreSQL container is running and healthy..."
if ! docker compose ps postgres | grep -q "healthy"; then
    fail "PostgreSQL container is not healthy. Start database before restoring."
fi
pass "PostgreSQL container is ready."

# 4. Execute Restore
if [[ "${DRY_RUN}" == "true" ]]; then
    info "[DRY-RUN] Would stream zcat ${BACKUP_FILE} | docker compose exec -T postgres psql -U ${POSTGRES_USER} -d ${POSTGRES_DB}"
    pass "[DRY-RUN] Restore simulation completed successfully."
    exit 0
fi

info "Restoring database from compressed archive..."
zcat "${BACKUP_FILE}" | docker compose exec -T postgres psql \
    -U "${POSTGRES_USER:-physio_admin}" \
    -d "${POSTGRES_DB:-physio_one_db}" \
    --quiet -v ON_ERROR_STOP=1

pass "Database restored successfully from '${BACKUP_FILE}'."

# 5. Verify Table Count Post-Restore
info "Verifying restored schema table count..."
TABLE_COUNT=$(docker compose exec -T postgres psql -U "${POSTGRES_USER:-physio_admin}" -d "${POSTGRES_DB:-physio_one_db}" -t -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';" | tr -d '[:space:]')
info "Verified restored public tables count: ${TABLE_COUNT}"

if (( TABLE_COUNT >= 63 )); then
    pass "Table count check passed (${TABLE_COUNT} tables present)."
else
    warn "Restored table count is ${TABLE_COUNT} (expected >= 63). Check migration status."
fi
