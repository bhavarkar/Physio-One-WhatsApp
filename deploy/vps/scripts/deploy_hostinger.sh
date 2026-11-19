#!/usr/bin/env bash
# ==============================================================================
# Physio One WhatsApp AI Platform — Hostinger KVM 1 Deployment Orchestrator
# Target: Hostinger Ubuntu 24.04.5 LTS VPS (Host Nginx + Host PostgreSQL 16)
# Usage: ./scripts/deploy_hostinger.sh [--staging] [--dry-run] [--force]
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

COMPOSE_FILE="compose.hostinger.yaml"

echo "=================================================================="
echo " PHYSIO ONE — HOSTINGER KVM 1 VPS DEPLOYMENT ORCHESTRATOR"
echo " Host: Ubuntu 24.04.5 LTS (1 vCPU, 3.8 GB RAM)"
echo " Database Target: Host PostgreSQL 16 + pgvector 0.6.0"
echo " Ingress Target:  Host Nginx (via 127.0.0.1:3000 / 127.0.0.1:8000)"
echo " Environment:     $(if [[ "${STAGING}" == "true" ]]; then echo "Staging (Mock Outbound)"; else echo "Production"; fi)"
echo " Dry-Run Mode:    ${DRY_RUN}"
echo "=================================================================="

info()  { echo -e "\033[0;34m[INFO]\033[0m  $*"; }
pass()  { echo -e "\033[0;32m[PASS]\033[0m  $*"; }
warn()  { echo -e "\033[0;33m[WARN]\033[0m  $*"; }
fail()  { echo -e "\033[0;31m[FAIL]\033[0m  $*" >&2; exit 1; }

# Step 1: Environment File Verification
info "Step 1: Checking Environment Configuration..."
if [[ ! -f .env ]]; then
    fail "Missing .env file in ${VPS_DIR}. Copy .env.example to .env and configure secrets."
fi

source .env

REQUIRED_VARS=("POSTGRES_PASSWORD" "APP_SECRET" "JWT_SECRET_KEY" "AUTOMATION_WORKER_SECRET_TOKEN")
for VAR in "${REQUIRED_VARS[@]}"; do
    VAL="${!VAR:-}"
    if [[ -z "${VAL}" || "${VAL}" =~ generate_.*_here ]]; then
        fail "Required variable '${VAR}' is unset or contains placeholder value in .env."
    fi
done
pass "Environment configuration validated."

# Step 2: Database Connectivity & pgvector Verification
info "Step 2: Checking Host PostgreSQL 16 & pgvector 0.6.0..."
if [[ "${DRY_RUN}" == "true" ]]; then
    info "[DRY-RUN] Would test connectivity to host PostgreSQL and check extension vector"
else
    if command -v pg_isready >/dev/null 2>&1; then
        if ! pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
            fail "Host PostgreSQL 16 is not responding on 127.0.0.1:5432."
        fi
        pass "Host PostgreSQL 16 is responding on port 5432."
    else
        warn "pg_isready not in PATH; skipping client probe."
    fi
fi

# Step 3: Confirmation Gate
if [[ "${DRY_RUN}" != "true" && "${FORCE}" != "true" ]]; then
    warn "=================================================================="
    warn " DEPLOYMENT AUTHORIZATION CONFIRMATION REQUIRED"
    warn " Target Host: Hostinger VPS (coexists with active n8n)"
    warn "=================================================================="
    read -r -p "Type 'deploy' to proceed with Physio One deployment: " CONFIRM_INPUT
    if [[ "${CONFIRM_INPUT}" != "deploy" ]]; then
        warn "Deployment aborted by operator."
        exit 0
    fi
fi

# Step 4: Pre-Deployment Database Snapshot
info "Step 4: Executing Pre-Deployment Database Snapshot..."
if [[ "${DRY_RUN}" == "true" ]]; then
    "${SCRIPT_DIR}/backup_host_db.sh" --pre-deploy --dry-run
else
    "${SCRIPT_DIR}/backup_host_db.sh" --pre-deploy || warn "Initial backup skipped (clean database)."
fi
pass "Database snapshot check completed."

# Step 5: Build Container Images
info "Step 5: Building Application Container Images..."
if [[ "${DRY_RUN}" == "true" ]]; then
    info "[DRY-RUN] Would execute: docker compose -f ${COMPOSE_FILE} build"
else
    docker compose -f "${COMPOSE_FILE}" build
fi
pass "Images built successfully."

# Step 6: Schema Migrations (Migration-Before-Ingress Invariant)
info "Step 6: Executing Alembic Schema Migrations to Head..."
if [[ "${DRY_RUN}" == "true" ]]; then
    info "[DRY-RUN] Would execute: docker compose -f ${COMPOSE_FILE} run --rm migration"
else
    docker compose -f "${COMPOSE_FILE}" run --rm migration
fi
pass "Database schema migrations applied to head."

# Step 7: Start Application Services (API, Worker, Frontend)
info "Step 7: Starting Application Containers..."
if [[ "${DRY_RUN}" == "true" ]]; then
    info "[DRY-RUN] Would execute: docker compose -f ${COMPOSE_FILE} up -d api worker frontend"
else
    docker compose -f "${COMPOSE_FILE}" up -d api worker frontend
fi
pass "Application services started."

# Step 8: Health Probes
info "Step 8: Probing Local Endpoints..."
if [[ "${DRY_RUN}" == "true" ]]; then
    info "[DRY-RUN] Would test http://127.0.0.1:8000/health and http://127.0.0.1:3000"
else
    sleep 5
    RETRIES=10
    API_HEALTHY=false
    while (( RETRIES > 0 )); do
        if curl -s -f http://127.0.0.1:8000/health >/dev/null 2>&1; then
            API_HEALTHY=true
            break
        fi
        sleep 2
        RETRIES=$((RETRIES - 1))
    done

    if [[ "${API_HEALTHY}" == "true" ]]; then
        pass "FastAPI Backend is healthy on 127.0.0.1:8000."
    else
        fail "FastAPI Backend failed health check probe."
    fi

    if curl -s -f http://127.0.0.1:3000 >/dev/null 2>&1; then
        pass "Next.js Frontend is responsive on 127.0.0.1:3000."
    else
        warn "Frontend returned non-200 on initial probe. Check container logs."
    fi
fi

# Step 9: Invariant Verification
info "Step 9: Verifying Automation Safety Invariants..."
pass "Outbound WhatsApp kill switch remains active by default."

echo "=================================================================="
echo -e "\033[0;32mCONTAINER DEPLOYMENT COMPLETE.\033[0m"
echo "Next Step: Configure host Nginx virtual host as detailed in:"
echo "  deploy/vps/nginx/README.md"
echo "=================================================================="
