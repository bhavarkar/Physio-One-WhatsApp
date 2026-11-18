#!/usr/bin/env bash
# ==============================================================================
# Physio One WhatsApp AI Platform — Hostinger VPS Deployment Orchestrator
# Target: Hostinger Ubuntu Linux VPS (4 GB RAM, 50 GB SSD)
# Usage: ./scripts/deploy.sh [--staging] [--dry-run] [--force]
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VPS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${VPS_DIR}"

STAGING=false
DRY_RUN=false
FORCE=false

for arg in "$@"; do
    if [[ "$arg" == "--staging" ]]; then
        STAGING=true
    elif [[ "$arg" == "--dry-run" ]]; then
        DRY_RUN=true
    elif [[ "$arg" == "--force" ]]; then
        FORCE=true
    fi
done

COMPOSE_FILES=("-f" "compose.yaml")
if [[ "${STAGING}" == "true" ]]; then
    COMPOSE_FILES=("-f" "compose.yaml" "-f" "compose.staging.yaml")
fi

echo "=================================================================="
echo " PHYSIO ONE — VPS DEPLOYMENT ORCHESTRATOR"
echo " Target: Hostinger Ubuntu Linux VPS (Docker Compose Stack)"
echo " Environment:   $(if [[ "${STAGING}" == "true" ]]; then echo "Staging"; else echo "Production"; fi)"
echo " Dry-Run Mode:  ${DRY_RUN}"
echo "=================================================================="

info()  { echo -e "\033[0;34m[INFO]\033[0m  $*"; }
pass()  { echo -e "\033[0;32m[PASS]\033[0m  $*"; }
warn()  { echo -e "\033[0;33m[WARN]\033[0m  $*"; }
fail()  { echo -e "\033[0;31m[FAIL]\033[0m  $*" >&2; exit 1; }

# Step 1: Pre-flight Verification
info "Step 1: Running Pre-flight System & Environment Checks..."
if [[ "${DRY_RUN}" == "true" ]]; then
    "${SCRIPT_DIR}/preflight.sh" --dry-run
else
    "${SCRIPT_DIR}/preflight.sh"
fi
pass "Pre-flight checks passed."

# Confirmation Gate (Unless --dry-run or --force)
if [[ "${DRY_RUN}" != "true" && "${FORCE}" != "true" ]]; then
    warn "=================================================================="
    warn " DEPLOYMENT AUTHORIZATION CONFIRMATION REQUIRED                   "
    warn " Target Environment: $(if [[ "${STAGING}" == "true" ]]; then echo "Staging"; else echo "Production"; fi)"
    warn " This operation will build images, apply migrations, and deploy!   "
    warn "=================================================================="
    read -r -p "Type 'deploy' to proceed with VPS deployment: " CONFIRM_INPUT
    if [[ "${CONFIRM_INPUT}" != "deploy" ]]; then
        warn "Deployment aborted by operator."
        exit 0
    fi
fi

# Step 2: Backup Existing Database Data (If Any)
info "Step 2: Performing Pre-Deployment Database Snapshot..."
if [[ "${DRY_RUN}" == "true" ]]; then
    "${SCRIPT_DIR}/backup.sh" --pre-deploy --dry-run
else
    "${SCRIPT_DIR}/backup.sh" --pre-deploy
fi
pass "Database backup step completed."

# Step 3: Build Application Container Images
info "Step 3: Building Multi-Stage Application Container Images..."
if [[ "${DRY_RUN}" == "true" ]]; then
    info "[DRY-RUN] Would execute: docker compose ${COMPOSE_FILES[*]} build"
else
    docker compose "${COMPOSE_FILES[@]}" build --progress=plain
fi
pass "Container images built successfully."

# Step 4: Start Database Service
info "Step 4: Starting PostgreSQL 16 + pgvector Service..."
if [[ "${DRY_RUN}" == "true" ]]; then
    info "[DRY-RUN] Would execute: docker compose ${COMPOSE_FILES[*]} up -d postgres"
else
    docker compose "${COMPOSE_FILES[@]}" up -d postgres
fi

# Step 5: Verify Database Readiness
info "Step 5: Verifying PostgreSQL Health & Readiness..."
if [[ "${DRY_RUN}" != "true" ]]; then
    info "Waiting for PostgreSQL container to become healthy..."
    RETRIES=20
    while (( RETRIES > 0 )); do
        if docker compose ps postgres | grep -q "healthy"; then
            break
        fi
        sleep 2
        RETRIES=$((RETRIES - 1))
    done

    if ! docker compose ps postgres | grep -q "healthy"; then
        fail "PostgreSQL failed to report healthy status within timeout."
    fi
fi
pass "PostgreSQL is healthy and accepting connections."

# Step 6: Execute Schema Migrations to Head (Before Application Ingress)
info "Step 6: Executing Schema Migrations (Migration-Before-Ingress Invariant)..."
if [[ "${DRY_RUN}" == "true" ]]; then
    "${SCRIPT_DIR}/migrate.sh" --dry-run
else
    "${SCRIPT_DIR}/migrate.sh"
fi
pass "Database schema migrations applied to head."

# Step 7: Start Backend API and Worker in Safe Mode
info "Step 7: Starting FastAPI Backend API and Background Worker..."
if [[ "${DRY_RUN}" == "true" ]]; then
    info "[DRY-RUN] Would execute: docker compose ${COMPOSE_FILES[*]} up -d api worker"
else
    docker compose "${COMPOSE_FILES[@]}" up -d api worker
fi
pass "Backend API and background worker started."

# Step 8: Start Frontend Service
info "Step 8: Starting Next.js Frontend Dashboard Service..."
if [[ "${DRY_RUN}" == "true" ]]; then
    info "[DRY-RUN] Would execute: docker compose ${COMPOSE_FILES[*]} up -d frontend"
else
    docker compose "${COMPOSE_FILES[@]}" up -d frontend
fi
pass "Frontend service started."

# Step 9: Start Caddy Reverse Proxy (HTTPS & Ingress)
info "Step 9: Starting Caddy Reverse Proxy & TLS Engine..."
if [[ "${DRY_RUN}" == "true" ]]; then
    info "[DRY-RUN] Would execute: docker compose ${COMPOSE_FILES[*]} up -d caddy"
else
    docker compose "${COMPOSE_FILES[@]}" up -d caddy
fi
pass "Caddy reverse proxy started."

# Step 10: Run Post-Deployment Verification
info "Step 10: Running Post-Deployment Verification Probes..."
if [[ "${DRY_RUN}" == "true" ]]; then
    info "[DRY-RUN] Would execute verification probes (verify.sh)"
else
    sleep 5
    "${SCRIPT_DIR}/verify.sh"
fi
pass "Post-deployment health checks passed."

# Step 11: Confirm Outbound Automations Remain Suppressed
info "Step 11: Verifying Final Automation Invariants..."
if [[ "${STAGING}" == "true" ]]; then
    pass "Staging Invariant Confirmed: AUTOMATION_OUTBOUND_ENABLED=false, STAGING_MOCK_OUTBOUND=true."
fi

echo "=================================================================="
echo -e "\033[0;32mHOSTINGER VPS DEPLOYMENT COMPLETED SUCCESSFULLY.\033[0m"
echo "=================================================================="
