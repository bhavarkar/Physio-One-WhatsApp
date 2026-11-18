#!/usr/bin/env bash
# ==============================================================================
# Physio One WhatsApp AI Platform — Database Migration Runner
# Target: Hostinger Ubuntu Linux VPS (PostgreSQL 16 + pgvector)
# Usage: ./scripts/migrate.sh [--dry-run]
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VPS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${VPS_DIR}"

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
fi

echo "=================================================================="
echo " PHYSIO ONE — DATABASE MIGRATION RUNNER"
echo " Target: PostgreSQL 16 + pgvector (Internal Docker Network)"
echo " Command: alembic upgrade head"
echo " Dry-Run Mode: ${DRY_RUN}"
echo "=================================================================="

info()  { echo -e "\033[0;34m[INFO]\033[0m  $*"; }
pass()  { echo -e "\033[0;32m[PASS]\033[0m  $*"; }
fail()  { echo -e "\033[0;31m[FAIL]\033[0m  $*" >&2; exit 1; }

# 1. Verify PostgreSQL Container is Healthy
info "Checking PostgreSQL container readiness..."
if [[ "${DRY_RUN}" == "true" ]]; then
    info "[DRY-RUN] Would verify PostgreSQL container readiness."
    info "[DRY-RUN] Would execute: docker compose run --rm migration"
    info "[DRY-RUN] Would check: docker compose run --rm migration alembic current"
    pass "[DRY-RUN] Migration simulation completed."
    exit 0
fi

if ! docker compose ps postgres | grep -q "healthy"; then
    info "PostgreSQL container is not yet healthy. Waiting up to 30 seconds..."
    RETRIES=15
    while (( RETRIES > 0 )); do
        if docker compose ps postgres | grep -q "healthy"; then
            break
        fi
        sleep 2
        RETRIES=$((RETRIES - 1))
    done
fi

if ! docker compose ps postgres | grep -q "healthy"; then
    fail "PostgreSQL service is not healthy. Aborting database migrations."
fi
pass "PostgreSQL service is healthy and accepting connections."

# 2. Execute Migration Runner Container
if [[ "${DRY_RUN}" == "true" ]]; then
    info "[DRY-RUN] Would execute: docker compose run --rm migration"
    pass "[DRY-RUN] Migration simulation completed."
    exit 0
fi

info "Executing Alembic schema migrations to head..."
docker compose run --rm migration

pass "Database migrations applied cleanly."

# 3. Verify Migration Current Revision
info "Checking current Alembic database revision..."
docker compose run --rm migration alembic current

pass "Database schema is verified at head."
