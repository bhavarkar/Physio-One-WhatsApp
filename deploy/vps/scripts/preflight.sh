#!/usr/bin/env bash
# ==============================================================================
# Physio One WhatsApp AI Platform — VPS Pre-flight System & Environment Checker
# Target: Hostinger Ubuntu Linux VPS (4 GB RAM, 50 GB SSD)
# Usage: ./scripts/preflight.sh [--dry-run]
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
echo " PHYSIO ONE — VPS PRE-FLIGHT VERIFICATION"
echo " Target: Hostinger Ubuntu Linux VPS (Docker Compose Architecture)"
echo " Dry-Run Mode: ${DRY_RUN}"
echo "=================================================================="

# Helper loggers
info()  { echo -e "\033[0;34m[INFO]\033[0m  $*"; }
pass()  { echo -e "\033[0;32m[PASS]\033[0m  $*"; }
warn()  { echo -e "\033[0;33m[WARN]\033[0m  $*"; }
fail()  { echo -e "\033[0;31m[FAIL]\033[0m  $*" >&2; exit 1; }

# 1. Operating System Check
info "Checking Operating System..."
if [[ -f /etc/os-release ]]; then
    . /etc/os-release
    pass "Detected OS: ${PRETTY_NAME:-Linux}"
else
    warn "Cannot verify /etc/os-release. Proceeding with caution."
fi

# 2. RAM Sizing Verification (Minimum 3.5 GB for 4 GB VPS tier)
info "Checking System Memory (RAM)..."
if [[ -f /proc/meminfo ]]; then
    TOTAL_MEM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
    TOTAL_MEM_MB=$((TOTAL_MEM_KB / 1024))
    if (( TOTAL_MEM_MB < 3200 )); then
        fail "Insufficient system memory: ${TOTAL_MEM_MB} MB available. Minimum required: 3200 MB."
    else
        pass "System Memory: ${TOTAL_MEM_MB} MB (Meets 4 GB VPS budget)."
    fi
else
    warn "/proc/meminfo not accessible; skipping RAM threshold check."
fi

# 3. Available Disk Space Verification (Minimum 5 GB free)
info "Checking Available Disk Space..."
AVAILABLE_KB=$(df -k . | awk 'NR==2 {print $4}')
AVAILABLE_MB=$((AVAILABLE_KB / 1024))
if (( AVAILABLE_MB < 5120 )); then
    fail "Insufficient free disk space: ${AVAILABLE_MB} MB. Minimum required: 5120 MB (5 GB)."
else
    pass "Available Disk Space: ${AVAILABLE_MB} MB (${AVAILABLE_KB} KB)."
fi

# 4. Docker Engine & Docker Compose v2 Inspection
info "Checking Docker and Docker Compose..."
if ! command -v docker >/dev/null 2>&1; then
    fail "Docker is not installed or not in PATH. Please install Docker Engine."
fi

DOCKER_VER=$(docker --version 2>/dev/null || true)
pass "Docker CLI: ${DOCKER_VER}"

if ! docker info >/dev/null 2>&1; then
    fail "Docker daemon is not running or current user lacks docker group permissions."
fi
pass "Docker daemon is active and responsive."

if ! docker compose version >/dev/null 2>&1; then
    fail "Docker Compose v2 plugin is not installed ('docker compose version' failed)."
fi
COMPOSE_VER=$(docker compose version 2>/dev/null || true)
pass "Docker Compose: ${COMPOSE_VER}"

# 5. Environment File & Permissions Inspection
info "Checking Environment File (.env)..."
if [[ ! -f .env ]]; then
    fail "Missing .env file in ${VPS_DIR}. Copy .env.example to .env and configure secrets."
fi

# Check file permissions (should be 600 or 400 on Linux)
ENV_PERM=$(stat -c "%a" .env 2>/dev/null || stat -f "%Lp" .env 2>/dev/null || echo "unknown")
if [[ "${ENV_PERM}" =~ ^[64]00$ ]]; then
    pass ".env permissions: ${ENV_PERM} (Secure: read/write strictly by owner)."
else
    warn ".env permissions are ${ENV_PERM}. Recommended: chmod 600 .env"
fi

# 6. Required Environment Variables Validation
info "Validating Required Security & Database Variables..."
source .env

REQUIRED_VARS=(
    "POSTGRES_PASSWORD"
    "APP_SECRET"
    "JWT_SECRET_KEY"
    "AUTOMATION_WORKER_SECRET_TOKEN"
)

for VAR in "${REQUIRED_VARS[@]}"; do
    VAL="${!VAR:-}"
    if [[ -z "${VAL}" || "${VAL}" =~ generate_.*_here ]]; then
        fail "Required variable '${VAR}' is unset or contains placeholder value in .env."
    fi
    pass "Variable '${VAR}' is configured (length: ${#VAL} chars)."
done

# 7. Compose Configuration Syntax Validation
info "Validating Docker Compose Configuration..."
if [[ -f compose.staging.yaml && "${ENVIRONMENT:-}" == "staging" ]]; then
    docker compose -f compose.yaml -f compose.staging.yaml config -q
    pass "Docker Compose staging configuration is valid."
else
    docker compose -f compose.yaml config -q
    pass "Docker Compose production configuration is valid."
fi

echo "=================================================================="
echo -e "\033[0;32mALL PRE-FLIGHT CHECKS PASSED SUCCESSFULLY.\033[0m"
echo "=================================================================="
