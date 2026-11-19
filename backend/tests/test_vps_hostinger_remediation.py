"""
TASK 23.1 Automated Verification Suite
Validates Hostinger KVM 1 deployment remediation:
1. PostgreSQL Unix domain socket vs TCP URL resolution
2. compose.hostinger.yaml loopback-only (127.0.0.1) port binding enforcement
3. Absence of Caddy and unmapped port 5432
4. Database provisioning safety (NOSUPERUSER, dynamic password, extensions)
5. Deployment script invariants (strict error handling, pre-deploy backup, rollback safeguards)
6. Outbound WhatsApp fail-closed defaults
"""

import os
import re
import pytest
import yaml
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEPLOY_DIR = REPO_ROOT / "deploy" / "vps"
COMPOSE_HOSTINGER_PATH = DEPLOY_DIR / "compose.hostinger.yaml"
INIT_SQL_PATH = DEPLOY_DIR / "database" / "init_host_postgres.sql"
VERIFY_SQL_PATH = DEPLOY_DIR / "database" / "verify_host_postgres.sql"
DEPLOY_SCRIPT_PATH = DEPLOY_DIR / "scripts" / "deploy_hostinger.sh"
ROLLBACK_SCRIPT_PATH = DEPLOY_DIR / "scripts" / "rollback_hostinger.sh"
BACKUP_SCRIPT_PATH = DEPLOY_DIR / "scripts" / "backup_host_db.sh"
RESTORE_SCRIPT_PATH = DEPLOY_DIR / "scripts" / "restore_host_db.sh"


def test_settings_database_url_unix_socket_resolution():
    """Verify that Settings cleanly resolves Unix domain socket URLs."""
    from app.core.config import Settings

    # Case A: Explicit Unix socket DATABASE_URL
    s1 = Settings(
        DATABASE_URL="postgresql+asyncpg://physio_user:secret@/physio_db?host=/var/run/postgresql",
        DATABASE_URL_SYNC="postgresql+psycopg2://physio_user:secret@/physio_db?host=/var/run/postgresql",
    )
    assert s1.async_database_url == "postgresql+asyncpg://physio_user:secret@/physio_db?host=/var/run/postgresql"
    assert s1.sync_database_url == "postgresql+psycopg2://physio_user:secret@/physio_db?host=/var/run/postgresql"

    # Case B: Resolution via POSTGRES_SOCKET_DIR
    s2 = Settings(
        DATABASE_URL=None,
        DATABASE_URL_SYNC=None,
        POSTGRES_USER="physio_user",
        POSTGRES_PASSWORD="securepassword",
        POSTGRES_DB="physio_db",
        POSTGRES_SOCKET_DIR="/var/run/postgresql",
    )
    assert s2.async_database_url == "postgresql+asyncpg://physio_user:securepassword@/physio_db?host=/var/run/postgresql"
    assert s2.sync_database_url == "postgresql+psycopg2://physio_user:securepassword@/physio_db?host=/var/run/postgresql"


def test_compose_hostinger_port_bindings_strictly_loopback():
    """Verify all published ports in compose.hostinger.yaml are strictly 127.0.0.1 to avoid Docker iptables bypass."""
    assert COMPOSE_HOSTINGER_PATH.exists(), f"Missing {COMPOSE_HOSTINGER_PATH}"
    with open(COMPOSE_HOSTINGER_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    services = data.get("services", {})
    for svc_name, svc_conf in services.items():
        ports = svc_conf.get("ports", [])
        for port_entry in ports:
            port_str = str(port_entry)
            assert port_str.startswith("127.0.0.1:"), (
                f"Security violation in service '{svc_name}': port '{port_str}' is not bound to 127.0.0.1! "
                f"Docker will expose this to 0.0.0.0, bypassing host firewalls."
            )


def test_compose_hostinger_caddy_and_postgres_port_exclusion():
    """Ensure Caddy is NOT present and port 5432 is NOT published in compose.hostinger.yaml."""
    with open(COMPOSE_HOSTINGER_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    services = data.get("services", {})
    assert "caddy" not in services, "caddy service must not be included in compose.hostinger.yaml (host Nginx owns ports 80/443)"

    # If fallback postgres service is present, it must NOT publish any host ports
    if "postgres" in services:
        pg_ports = services["postgres"].get("ports", [])
        assert len(pg_ports) == 0, f"Fallback postgres service must not publish host ports: {pg_ports}"


def test_compose_hostinger_unix_socket_volume_mount():
    """Verify api, worker, and migration mount /var/run/postgresql for host DB connectivity."""
    with open(COMPOSE_HOSTINGER_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    services = data.get("services", {})
    for svc in ["api", "worker", "migration"]:
        assert svc in services, f"Service '{svc}' missing from compose.hostinger.yaml"
        volumes = services[svc].get("volumes", [])
        socket_mounted = any("/var/run/postgresql" in str(v) for v in volumes)
        assert socket_mounted, f"Service '{svc}' does not mount /var/run/postgresql for direct host DB access"


def test_init_host_postgres_sql_safety_and_least_privilege():
    """Verify init_host_postgres.sql enforces least privilege, non-hardcoded passwords, and extensions."""
    assert INIT_SQL_PATH.exists(), f"Missing {INIT_SQL_PATH}"
    content = INIT_SQL_PATH.read_text(encoding="utf-8")

    # 1. No hardcoded passwords in script
    assert "GENERATE_STRONG_PASSWORD_32_CHARS" not in content, "Hardcoded placeholder password found in init_host_postgres.sql"
    assert "physio_password" in content, "Script must use dynamic parameter :physio_password"

    # 2. Least privilege enforcement
    assert "NOSUPERUSER" in content, "Application role physio_user must be NOSUPERUSER"
    assert "NOCREATEDB" in content, "Application role physio_user must be NOCREATEDB"
    assert "NOCREATEROLE" in content, "Application role physio_user must be NOCREATEROLE"

    # 3. Database ownership and extensions
    assert "CREATE DATABASE physio_db" in content
    assert "OWNER TO physio_user" in content or "OWNER physio_user" in content
    assert "CREATE EXTENSION IF NOT EXISTS vector" in content
    assert "CREATE EXTENSION IF NOT EXISTS btree_gist" in content


def test_verify_host_postgres_sql_checks():
    """Verify verify_host_postgres.sql validates extensions, role permissions, and HNSW indexes."""
    assert VERIFY_SQL_PATH.exists(), f"Missing {VERIFY_SQL_PATH}"
    content = VERIFY_SQL_PATH.read_text(encoding="utf-8")

    assert "extname IN ('vector', 'btree_gist'" in content or "vector" in content
    assert "rolsuper" in content, "Must check rolsuper to verify NOSUPERUSER"
    assert "USING hnsw (embedding vector_cosine_ops)" in content, "Must test HNSW cosine index creation"


def test_deployment_scripts_invariants_and_error_handling():
    """Verify all deployment bash scripts enforce strict error handling, pre-deploy backup, and rollback safety."""
    scripts = [
        DEPLOY_SCRIPT_PATH,
        ROLLBACK_SCRIPT_PATH,
        BACKUP_SCRIPT_PATH,
        RESTORE_SCRIPT_PATH,
    ]

    for s in scripts:
        assert s.exists(), f"Missing script {s}"
        text = s.read_text(encoding="utf-8")
        assert "set -euo pipefail" in text, f"{s.name} must specify 'set -euo pipefail'"

    # deploy_hostinger.sh specific invariants
    deploy_text = DEPLOY_SCRIPT_PATH.read_text(encoding="utf-8")
    assert "backup_host_db.sh" in deploy_text, "deploy_hostinger.sh must call backup_host_db.sh before migrations"
    assert "migration" in deploy_text, "deploy_hostinger.sh must execute migrations"
    assert "rollback_hostinger.sh" in deploy_text, "deploy_hostinger.sh must invoke rollback on health failure"

    # rollback_hostinger.sh specific invariants
    rollback_text = ROLLBACK_SCRIPT_PATH.read_text(encoding="utf-8")
    assert "AUTOMATION_OUTBOUND_ENABLED = False" in rollback_text, "Rollback must re-assert outbound kill switch"
    assert "DOWNGRADE" not in rollback_text.upper() or "NOT DOWNGRADED" in rollback_text.upper(), (
        "Rollback must never automatically down-migrate database schemas"
    )

    # restore_host_db.sh specific invariants
    restore_text = RESTORE_SCRIPT_PATH.read_text(encoding="utf-8")
    assert "gzip -t" in restore_text, "Restore script must verify gzip archive integrity"
    assert "--confirm-restore" in restore_text, "Restore script must enforce --confirm-restore gate"


def test_compose_hostinger_outbound_fail_closed_defaults():
    """Verify compose.hostinger.yaml enforces fail-closed outbound messaging by default."""
    with open(COMPOSE_HOSTINGER_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    for svc in ["api", "worker"]:
        env_list = data["services"][svc]["environment"]
        env_dict = {}
        for item in env_list:
            if "=" in item:
                k, v = item.split("=", 1)
                env_dict[k] = v

        assert "AUTOMATION_OUTBOUND_ENABLED" in env_dict
        assert "false" in env_dict["AUTOMATION_OUTBOUND_ENABLED"].lower()
        assert "STAGING_MOCK_OUTBOUND" in env_dict
        assert "true" in env_dict["STAGING_MOCK_OUTBOUND"].lower()
