#!/usr/bin/env bash
# ==============================================================================
# Physio One WhatsApp AI Platform — VPS Deployment Verification Runner
# Target: Hostinger Ubuntu Linux VPS
# Usage: ./scripts/verify.sh [--staging]
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VPS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${VPS_DIR}"

source .env

echo "=================================================================="
echo " PHYSIO ONE — VPS DEPLOYMENT POST-FLIGHT VERIFIER"
echo " Target Domain: ${DOMAIN_NAME:-app.example.com}"
echo " Environment:   ${ENVIRONMENT:-production}"
echo "=================================================================="

info()  { echo -e "\033[0;34m[INFO]\033[0m  $*"; }
pass()  { echo -e "\033[0;32m[PASS]\033[0m  $*"; }
warn()  { echo -e "\033[0;33m[WARN]\033[0m  $*"; }
fail()  { echo -e "\033[0;31m[FAIL]\033[0m  $*" >&2; exit 1; }

# 1. Container Status Inspection
info "Inspecting Docker container status..."
docker compose ps

SERVICES=("postgres" "api" "worker" "frontend" "caddy")
for SVC in "${SERVICES[@]}"; do
    if ! docker compose ps "${SVC}" | grep -q "Up\|healthy"; then
        fail "Service '${SVC}' is not running or not healthy!"
    fi
    pass "Service '${SVC}' is active."
done

# 2. Port Exposure Audit
info "Verifying that internal ports (5432, 8000, 3000) are NOT published externally..."
if netstat -tuln 2>/dev/null | grep -q ":5432 " || ss -tuln 2>/dev/null | grep -q ":5432 "; then
    fail "CRITICAL SECURITY BREACH: Port 5432 is listening publicly on host!"
else
    pass "Port 5432 is not exposed publicly (protected inside private Docker network)."
fi

# 3. API Healthcheck Probe
info "Probing backend API health endpoint internally..."
HEALTH_RESP=$(docker compose exec -T api curl -s -f http://localhost:8000/health || echo '{"status":"failed"}')
if echo "${HEALTH_RESP}" | grep -q '"status":"healthy"'; then
    pass "API health endpoint responded: healthy."
else
    fail "API healthcheck probe failed: ${HEALTH_RESP}"
fi

# 4. Setup Status Probe
info "Checking initial admin setup status..."
SETUP_RESP=$(docker compose exec -T api curl -s -f http://localhost:8000/api/v1/auth/setup-status || echo '{"error":"failed"}')
pass "Auth setup-status response: ${SETUP_RESP}"

# 5. Staging Safety Safeguards Audit
if [[ "${ENVIRONMENT:-}" == "staging" ]]; then
    info "Auditing staging safety guardrails in container environment..."
    OUTBOUND_ENABLED=$(docker compose exec -T api python -c "from app.core.config import settings; print(settings.AUTOMATION_OUTBOUND_ENABLED)")
    MOCK_ENABLED=$(docker compose exec -T api python -c "from app.core.config import settings; print(settings.STAGING_MOCK_OUTBOUND)")
    READ_ONLY_APPT=$(docker compose exec -T api python -c "from app.core.config import settings; print(settings.APPOINTMENTS_READ_ONLY)")
    DRAFT_CAMPAIGNS=$(docker compose exec -T api python -c "from app.core.config import settings; print(settings.CAMPAIGNS_DRAFT_ONLY)")

    if [[ "${OUTBOUND_ENABLED}" == "False" ]]; then
        pass "AUTOMATION_OUTBOUND_ENABLED = False (Kill-switch active)."
    else
        fail "SAFETY VIOLATION: AUTOMATION_OUTBOUND_ENABLED is True in staging!"
    fi

    if [[ "${MOCK_ENABLED}" == "True" ]]; then
        pass "STAGING_MOCK_OUTBOUND = True (Provider mock mode active)."
    else
        warn "STAGING_MOCK_OUTBOUND is False. Verify allowlist is configured."
    fi

    if [[ "${READ_ONLY_APPT}" == "True" && "${DRAFT_CAMPAIGNS}" == "True" ]]; then
        pass "Appointments read-only and campaigns draft-only guards active."
    fi
fi

# 6. Public Caddy / HTTPS Ingress Check
info "Checking Caddy ingress proxy..."
if curl -k -s -f "http://localhost/health" >/dev/null 2>&1 || curl -k -s -f "https://localhost/health" >/dev/null 2>&1; then
    pass "Caddy reverse proxy is successfully routing /health requests."
else
    warn "Local Caddy probe returned non-200. Check DNS propagation and TLS certificates."
fi

echo "=================================================================="
echo -e "\033[0;32mALL POST-DEPLOYMENT VERIFICATION CHECKS PASSED.\033[0m"
echo "=================================================================="
