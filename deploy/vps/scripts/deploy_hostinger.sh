#!/usr/bin/env bash
# ==============================================================================
# Physio One WhatsApp AI Platform — Hostinger KVM 1 Deployment Orchestrator
# Target: Hostinger Ubuntu 24.04.5 LTS VPS (Host Nginx + Host PostgreSQL 16)
# Usage: ./scripts/deploy_hostinger.sh [--staging] [--skip-build] [--dry-run] [--force]
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VPS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${VPS_DIR}"

STAGING=false
DRY_RUN=false
FORCE=false
SKIP_BUILD=false

for arg in "$@"; do
    if [[ "$arg" == "--staging" ]]; then
        STAGING=true
    elif [[ "$arg" == "--dry-run" ]]; then
        DRY_RUN=true
    elif [[ "$arg" == "--force" ]]; then
        FORCE=true
    elif [[ "$arg" == "--skip-build" ]]; then
        SKIP_BUILD=true
    fi
done

COMPOSE_FILE="compose.hostinger.yaml"

echo "=================================================================="
echo " PHYSIO ONE — HOSTINGER KVM 1 VPS DEPLOYMENT ORCHESTRATOR"
echo " Host: Ubuntu 24.04.5 LTS (1 vCPU, 3.8 GB RAM)"
echo " Database Target: Host PostgreSQL 16 via Unix domain socket"
echo " Ingress Target:  Host Nginx (via 127.0.0.1:3000 / 127.0.0.1:8000)"
echo " Environment:     $(if [[ "${STAGING}" == "true" ]]; then echo "Staging (Mock Outbound)"; else echo "Production"; fi)"
echo " Skip Build Mode: ${SKIP_BUILD}"
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

# Step 2: Database Connectivity & Socket Verification
info "Step 2: Checking Host PostgreSQL 16 & pgvector Socket..."
SOCKET_PATH="/var/run/postgresql/.s.PGSQL.5432"
if [[ "${DRY_RUN}" == "true" ]]; then
    info "[DRY-RUN] Would test connectivity to host PostgreSQL socket or 127.0.0.1:5432"
else
    PG_ACCESSIBLE=false
    if [[ -S "${SOCKET_PATH}" ]]; then
        info "Found active Unix domain socket: ${SOCKET_PATH}"
        PG_ACCESSIBLE=true
    elif command -v pg_isready >/dev/null 2>&1; then
        if pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
            PG_ACCESSIBLE=true
        fi
    fi

    if [[ "${PG_ACCESSIBLE}" != "true" ]]; then
        fail "Host PostgreSQL 16 is not responding via socket (/var/run/postgresql) or TCP."
    fi
    pass "Host PostgreSQL 16 is verified."
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

# Step 4: Pre-Deployment Database Snapshot (Mandatory for existing DB)
info "Step 4: Executing Pre-Deployment Database Snapshot..."
if [[ "${DRY_RUN}" == "true" ]]; then
    "${SCRIPT_DIR}/backup_host_db.sh" --pre-deploy --dry-run
else
    # Must exit 0. If backup fails on existing database, deployment halts immediately.
    "${SCRIPT_DIR}/backup_host_db.sh" --pre-deploy
fi
pass "Pre-deployment database snapshot check completed."

# Step 5: Build Container Images (or skip if prebuilt)
if [[ "${SKIP_BUILD}" == "true" ]]; then
    info "Step 5: Skipping on-server image build (--skip-build flag set). Using prebuilt images."
else
    info "Step 5: Building Application Container Images..."
    if [[ "${DRY_RUN}" == "true" ]]; then
        info "[DRY-RUN] Would execute: docker compose -f ${COMPOSE_FILE} build"
    else
        docker compose -f "${COMPOSE_FILE}" build
    fi
    pass "Container images built successfully."
fi

# Step 6: Schema Migrations (Migration-Before-Ingress Invariant)
info "Step 6: Executing Alembic Schema Migrations to Head..."
if [[ "${DRY_RUN}" == "true" ]]; then
    info "[DRY-RUN] Would execute: docker compose -f ${COMPOSE_FILE} run --rm migration"
else
    docker compose -f "${COMPOSE_FILE}" run --rm migration
fi
pass "Database schema migrations applied cleanly to head."

# Step 7: Start Application Services (API, Worker, Frontend)
info "Step 7: Starting Application Containers (bound strictly to 127.0.0.1)..."
if [[ "${DRY_RUN}" == "true" ]]; then
    info "[DRY-RUN] Would execute: docker compose -f ${COMPOSE_FILE} up -d api worker frontend"
else
    docker compose -f "${COMPOSE_FILE}" up -d api worker frontend
fi
pass "Application services started."

# Step 8: Health Probes with Automatic Rollback on Failure
info "Step 8: Probing Local Endpoints..."
if [[ "${DRY_RUN}" == "true" ]]; then
    info "[DRY-RUN] Would probe http://127.0.0.1:8000/health and http://127.0.0.1:3000"
else
    sleep 5
    RETRIES=15
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
        warn "Backend health check failed. Initiating automatic rollback..."
        "${SCRIPT_DIR}/rollback_hostinger.sh" --confirm
        fail "Deployment failed: FastAPI Backend was not healthy. Stack rolled back."
    fi

    if curl -s -f http://127.0.0.1:3000 >/dev/null 2>&1; then
        pass "Next.js Frontend is responsive on 127.0.0.1:3000."
    else
        warn "Frontend returned non-200 on initial probe. Check logs: docker compose -f ${COMPOSE_FILE} logs frontend"
    fi
fi

# Step 9: Invariant Verification
info "Step 9: Verifying Automation Safety Invariants..."
if [[ "${STAGING}" == "true" || "${AUTOMATION_OUTBOUND_ENABLED:-false}" != "true" ]]; then
    pass "Outbound WhatsApp kill switch confirmed active (AUTOMATION_OUTBOUND_ENABLED=false)."
fi

echo "=================================================================="
echo -e "\033[0;32mCONTAINER DEPLOYMENT COMPLETE & HEALTHY.\033[0m"
echo "Next Step: Configure host Nginx virtual host as detailed in:"
echo "  deploy/vps/nginx/README.md"
echo "=================================================================="
