#!/usr/bin/env bash
# ==============================================================================
# Physio One WhatsApp AI Platform — Host PostgreSQL Restore Runner
# Target: Host PostgreSQL 16 on Hostinger VPS
# Usage: ./scripts/restore_host_db.sh <backup.sql.gz> [--confirm-restore] [--dry-run]
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

if [[ -f .env ]]; then
    source .env
fi

TARGET_DB="${POSTGRES_DB:-physio_db}"

echo "=================================================================="
echo " PHYSIO ONE — HOST DATABASE RESTORE RUNNER"
echo " Backup File:   ${BACKUP_FILE}"
echo " Target DB:     ${TARGET_DB}"
echo " Dry-Run Mode:  ${DRY_RUN}"
echo "=================================================================="

info()  { echo -e "\033[0;34m[INFO]\033[0m  $*"; }
pass()  { echo -e "\033[0;32m[PASS]\033[0m  $*"; }
warn()  { echo -e "\033[0;33m[WARN]\033[0m  $*"; }
fail()  { echo -e "\033[0;31m[FAIL]\033[0m  $*" >&2; exit 1; }

# 1. Validate File
if [[ ! -f "${BACKUP_FILE}" ]]; then
    fail "Backup file '${BACKUP_FILE}' does not exist!"
fi

info "Testing gzip integrity..."
if ! gzip -t "${BACKUP_FILE}"; then
    fail "Gzip integrity check failed for '${BACKUP_FILE}'."
fi
pass "Archive integrity verified."

# 2. Confirmation Check
if [[ "${DRY_RUN}" != "true" && "${CONFIRM}" != "true" ]]; then
    warn "=================================================================="
    warn " CRITICAL WARNING: DATABASE RESTORE OVERWRITE"
    warn " This will overwrite existing data in '${TARGET_DB}'!"
    warn " Pass '--confirm-restore' to authorize restoration."
    warn "=================================================================="
    exit 1
fi

if [[ "${DRY_RUN}" == "true" ]]; then
    info "[DRY-RUN] Would stream zcat ${BACKUP_FILE} | psql -d ${TARGET_DB}"
    pass "[DRY-RUN] Restore simulation completed."
    exit 0
fi

# 3. Execute Restore
info "Restoring database from compressed archive..."
if command -v PGPASSWORD >/dev/null 2>&1 || [[ -n "${POSTGRES_PASSWORD:-}" ]]; then
    export PGPASSWORD="${POSTGRES_PASSWORD:-}"
    zcat "${BACKUP_FILE}" | psql -h 127.0.0.1 -p 5432 -U "${POSTGRES_USER:-physio_user}" -d "${TARGET_DB}" --quiet -v ON_ERROR_STOP=1
    unset PGPASSWORD
else
    zcat "${BACKUP_FILE}" | sudo -u postgres psql -d "${TARGET_DB}" --quiet -v ON_ERROR_STOP=1
fi

pass "Database restored successfully."

# 4. Verify Table Count Post-Restore
info "Verifying restored schema table count..."
TABLE_COUNT=$(sudo -u postgres psql -d "${TARGET_DB}" -t -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';" | tr -d '[:space:]')
info "Verified restored public tables count: ${TABLE_COUNT}"

if (( TABLE_COUNT >= 63 )); then
    pass "Table count check passed (${TABLE_COUNT} tables present)."
else
    warn "Restored table count is ${TABLE_COUNT} (expected >= 63). Check migration status."
fi
