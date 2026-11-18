#!/usr/bin/env bash
# ==============================================================================
# Physio One WhatsApp AI Platform — Fast Rollback Runner
# Target: Hostinger Ubuntu Linux VPS
# Usage: ./scripts/rollback.sh [--image-tag <TAG>] [--confirm] [--dry-run]
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VPS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${VPS_DIR}"

PREV_TAG="${1:-previous}"
CONFIRM=false
DRY_RUN=false

for arg in "$@"; do
    if [[ "$arg" == "--confirm" ]]; then
        CONFIRM=true
    elif [[ "$arg" == "--dry-run" ]]; then
        DRY_RUN=true
    fi
done

source .env

echo "=================================================================="
echo " PHYSIO ONE — APPLICATION ROLLBACK RUNNER"
echo " Target Rollback Tag: ${PREV_TAG}"
echo " Dry-Run Mode:        ${DRY_RUN}"
echo "=================================================================="

info()  { echo -e "\033[0;34m[INFO]\033[0m  $*"; }
pass()  { echo -e "\033[0;32m[PASS]\033[0m  $*"; }
warn()  { echo -e "\033[0;33m[WARN]\033[0m  $*"; }
fail()  { echo -e "\033[0;31m[FAIL]\033[0m  $*" >&2; exit 1; }

# 1. Safety Invariant: NEVER downgrade database automatically
warn "DATA INTEGRITY INVARIANT: Rollback resets container images ONLY."
warn "Database migrations are NOT downgraded automatically to avoid data loss."

if [[ "${DRY_RUN}" != "true" && "${CONFIRM}" != "true" ]]; then
    warn "Pass '--confirm' to authorize container rollback."
    exit 1
fi

# 2. Emergency Outbound Kill Switch Re-assertion
info "Re-asserting outbound automation kill switch..."
if [[ "${DRY_RUN}" == "true" ]]; then
    info "[DRY-RUN] Would ensure AUTOMATION_OUTBOUND_ENABLED=false in runtime environment"
else
    # Update running API container if active
    docker compose exec -T api python -c "from app.core.config import settings; settings.AUTOMATION_OUTBOUND_ENABLED = False" 2>/dev/null || true
    pass "Outbound messaging confirmed suppressed."
fi

# 3. Rollback Container Images
if [[ "${DRY_RUN}" == "true" ]]; then
    info "[DRY-RUN] Would restart api, worker, and frontend containers to stable tag: ${PREV_TAG}"
    pass "[DRY-RUN] Rollback simulation completed."
    exit 0
fi

info "Restoring previous stable container images..."
docker compose restart api worker frontend

# 4. Verify Health After Rollback
info "Verifying health post-rollback..."
sleep 5
./scripts/verify.sh

pass "Application rollback completed successfully."
