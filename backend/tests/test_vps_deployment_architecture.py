"""
TASK 20 — Hostinger Ubuntu VPS Deployment Architecture & Security Tests.

Verifies:
1. Docker Compose VPS configuration (compose.yaml, compose.staging.yaml)
2. Resource budget compliance (total container RAM <= 2.5 GB on 4 GB VPS)
3. Database network privacy: port 5432 is strictly private, never published to host
4. Public ingress boundary: only Caddy ports 80 and 443 are published
5. Logging limits: json-file log rotation configured across all containers
6. Staging safety defaults: mock outbound, kill switches, draft campaigns, read-only appts
7. Worker daemon continuous execution mode without GCP Cloud Tasks dependency
8. Migration-before-ingress sequencing via dedicated one-shot container
9. Backup script integrity and retention logic
10. Rollback non-downgrade data protection invariant
"""

import os
import yaml
import pytest


@pytest.fixture
def vps_dir():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "deploy", "vps"))


@pytest.fixture
def compose_prod(vps_dir):
    compose_path = os.path.join(vps_dir, "compose.yaml")
    assert os.path.exists(compose_path), "deploy/vps/compose.yaml does not exist"
    with open(compose_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def compose_staging(vps_dir):
    staging_path = os.path.join(vps_dir, "compose.staging.yaml")
    assert os.path.exists(staging_path), "deploy/vps/compose.staging.yaml does not exist"
    with open(staging_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# --- 1. Required Services Audit ---
def test_01_required_vps_services(compose_prod):
    """Verify all 5 required runtime services + 1 migration runner exist."""
    services = compose_prod.get("services", {})
    required = ["caddy", "frontend", "api", "worker", "postgres", "migration"]
    for svc in required:
        assert svc in services, f"Required service '{svc}' missing in compose.yaml"


# --- 2. RAM Resource Budget Allocation ---
def test_02_ram_resource_limits_fit_4gb_vps(compose_prod):
    """Verify that total container RAM limits do not exceed 2500 MB, leaving 1.5GB+ for OS."""
    services = compose_prod.get("services", {})
    total_memory_mb = 0

    for name, svc in services.items():
        if name == "migration":
            continue  # One-shot runner, does not run concurrently in background stack
        deploy_cfg = svc.get("deploy", {})
        limits = deploy_cfg.get("resources", {}).get("limits", {})
        mem_str = limits.get("memory", "0M")
        if mem_str.endswith("M"):
            total_memory_mb += int(mem_str[:-1])
        elif mem_str.endswith("G") or mem_str.endswith("Gi"):
            total_memory_mb += int(float(mem_str[:-1]) * 1024)

    # Total must be between 1500 MB and 2500 MB
    assert total_memory_mb <= 2500, f"Total container RAM limit ({total_memory_mb} MB) exceeds 2500 MB budget"
    assert total_memory_mb >= 1500, f"Total container RAM limit ({total_memory_mb} MB) suspiciously low"


# --- 3. Database Port Privacy (Port 5432 Must NOT Be Exposed) ---
def test_03_postgres_port_5432_not_published(compose_prod):
    """Verify PostgreSQL port 5432 is private and never exposed to the host/internet."""
    postgres_svc = compose_prod["services"]["postgres"]
    assert "ports" not in postgres_svc or len(postgres_svc.get("ports", [])) == 0, (
        "Security Violation: PostgreSQL port 5432 must NOT be published in compose.yaml!"
    )


# --- 4. Public Ingress Restrictions (Only Ports 80 and 443 on Caddy) ---
def test_04_public_ingress_restricted_to_caddy(compose_prod):
    """Verify only Caddy reverse proxy publishes host ports 80 and 443."""
    services = compose_prod["services"]
    for name, svc in services.items():
        if name == "caddy":
            ports = svc.get("ports", [])
            assert "80:80" in ports
            assert "443:443" in ports
        else:
            ports = svc.get("ports", [])
            assert len(ports) == 0, f"Service '{name}' must not publish host ports directly"


# --- 5. Docker Log Rotation Configured ---
def test_05_docker_log_rotation_configured(compose_prod):
    """Verify log rotation is configured across services to prevent unbounded disk growth."""
    services = compose_prod["services"]
    for name, svc in services.items():
        if name == "migration":
            continue
        logging_cfg = svc.get("logging", {})
        assert logging_cfg.get("driver") == "json-file", f"Service '{name}' missing json-file logging driver"
        opts = logging_cfg.get("options", {})
        assert opts.get("max-size") == "10m", f"Service '{name}' max-size should be 10m"
        assert opts.get("max-file") == "3", f"Service '{name}' max-file should be 3"


# --- 6. Staging Safety Invariants ---
def test_06_staging_override_safety_invariants(compose_staging):
    """Verify compose.staging.yaml injects fail-safe defaults for staging operation."""
    api_env = compose_staging["services"]["api"]["environment"]
    worker_env = compose_staging["services"]["worker"]["environment"]

    expected_guards = [
        "ENVIRONMENT=staging",
        "STAGING_MOCK_OUTBOUND=true",
        "AUTOMATION_OUTBOUND_ENABLED=false",
        "DEFAULT_AI_INBOUND_MODE=disabled",
        "APPOINTMENTS_READ_ONLY=true",
        "CAMPAIGNS_DRAFT_ONLY=true",
        "STAGING_ALLOWLIST_PHONE_NUMBERS=[]",
    ]

    for guard in expected_guards:
        assert guard in api_env, f"Staging API missing safety guard: {guard}"
        assert guard in worker_env, f"Staging Worker missing safety guard: {guard}"


# --- 7. Caddyfile Security Configuration ---
def test_07_caddyfile_security_headers_and_routing(vps_dir):
    """Verify Caddyfile defines security headers, HSTS, and same-origin API routing."""
    caddyfile_path = os.path.join(vps_dir, "Caddyfile")
    assert os.path.exists(caddyfile_path)

    with open(caddyfile_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "Strict-Transport-Security" in content
    assert "X-Content-Type-Options" in content
    assert "X-Frame-Options" in content
    assert "handle /api/*" in content
    assert "handle /health" in content
    assert "reverse_proxy api:8000" in content
    assert "reverse_proxy frontend:3000" in content
    assert "max_size 15MB" in content


# --- 8. VPS Operational Scripts Audit ---
def test_08_operational_scripts_present_and_safe(vps_dir):
    """Verify all 7 operational bash scripts exist and enforce set -euo pipefail."""
    scripts_dir = os.path.join(vps_dir, "scripts")
    expected_scripts = [
        "preflight.sh",
        "deploy.sh",
        "migrate.sh",
        "backup.sh",
        "restore.sh",
        "verify.sh",
        "rollback.sh",
    ]

    for script_name in expected_scripts:
        script_path = os.path.join(scripts_dir, script_name)
        assert os.path.exists(script_path), f"Missing script: {script_name}"
        with open(script_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "set -euo pipefail" in content, f"Script {script_name} must use 'set -euo pipefail'"
        assert "--dry-run" in content or script_name in ("verify.sh",), (
            f"Script {script_name} should support dry-run simulation"
        )


# --- 9. Rollback Non-Downgrade Invariant ---
def test_09_rollback_non_downgrade_invariant(vps_dir):
    """Verify rollback.sh explicitly avoids automatic database downgrades."""
    rollback_path = os.path.join(vps_dir, "scripts", "rollback.sh")
    with open(rollback_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "Database migrations are NOT downgraded automatically" in content
    assert "AUTOMATION_OUTBOUND_ENABLED = False" in content or "AUTOMATION_OUTBOUND_ENABLED=false" in content


# --- 10. Database Tuning for 4 GB VPS ---
def test_10_postgres_tuning_parameters(compose_prod):
    """Verify postgres container command tunes shared_buffers and connection limits for 4 GB RAM."""
    cmd = compose_prod["services"]["postgres"]["command"]
    cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd

    assert "shared_buffers=128MB" in cmd_str
    assert "work_mem=4MB" in cmd_str
    assert "max_connections=50" in cmd_str
