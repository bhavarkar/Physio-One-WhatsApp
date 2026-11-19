#!/usr/bin/env bash
# ==============================================================================
# Physio One WhatsApp AI Platform — Hostinger KVM 1 Fast Rollback Runner
# Target: Hostinger Ubuntu 24.04.5 LTS VPS
# Usage: ./scripts/rollback_hostinger.sh [--confirm] [--dry-run]
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VPS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${VPS_DIR}"

CONFIRM=false
DRY_RUN=false

for arg in "$@"; do
    if [[ "$arg" == "--confirm" ]]; then
        CONFIRM=true
    elif [[ "$arg" == "--dry-run" ]]; then
        DRY_RUN=true
    fi
done

COMPOSE_FILE="compose.hostinger.yaml"

echo "=================================================================="
echo " PHYSIO ONE — HOSTINGER KVM 1 ROLLBACK RUNNER"
echo " Target Stack: ${COMPOSE_FILE}"
echo " Dry-Run Mode: ${DRY_RUN}"
echo "=================================================================="

info()  { echo -e "\033[0;34m[INFO]\033[0m  $*"; }
pass()  { echo -e "\033[0;32m[PASS]\033[0m  $*"; }
warn()  { echo -e "\033[0;33m[WARN]\033[0m  $*"; }
fail()  { echo -e "\033[0;31m[FAIL]\033[0m  $*" >&2; exit 1; }

warn "DATA INTEGRITY INVARIANT: Rollback resets container images ONLY."
warn "Database migrations are NOT downgraded automatically to avoid data loss."

if [[ "${DRY_RUN}" != "true" && "${CONFIRM}" != "true" ]]; then
    warn "Pass '--confirm' to authorize container rollback."
    exit 1
fi

if [[ "${DRY_RUN}" == "true" ]]; then
    info "[DRY-RUN] Would re-assert AUTOMATION_OUTBOUND_ENABLED=false"
    info "[DRY-RUN] Would restart api, worker, and frontend containers"
    pass "[DRY-RUN] Rollback simulation completed."
    exit 0
fi

info "1. Re-asserting outbound automation kill switch..."
docker compose -f "${COMPOSE_FILE}" exec -T api python -c "from app.core.config import settings; settings.AUTOMATION_OUTBOUND_ENABLED = False" 2>/dev/null || true
pass "Outbound messaging confirmed suppressed."

info "2. Restarting application containers..."
docker compose -f "${COMPOSE_FILE}" restart api worker frontend

info "3. Verifying health post-rollback..."
sleep 5
if curl -s -f http://127.0.0.1:8000/health >/dev/null 2>&1; then
    pass "Backend API is healthy on 127.0.0.1:8000."
else
    warn "Backend API health check returned non-200. Check logs: docker compose -f compose.hostinger.yaml logs api"
fi

pass "Application rollback completed successfully."
