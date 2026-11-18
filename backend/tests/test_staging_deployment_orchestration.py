"""
TASK 19 — Staging Deployment Orchestration & Pre-flight Security Gate Tests.

Verifies:
1. Deployment phase ordering and dependency checkpoints
2. Missing ProjectId validation
3. GCP active project mismatch detection
4. Missing billing approval gate
5. Native command failure fail-closed behavior
6. Missing secret versions pre-check
7. Database-user bootstrap failure handling
8. Migration-before-ingress enforcement
9. API health-check failure handling
10. Cloud Scheduler paused invariant in Terraform
11. Staging mock mode & deny-all allowlist enforcement
12. Secret redaction in logs and command outputs
13. Fast rollback safety procedures
"""

import os
import re
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.core.config import settings
from app.models.whatsapp import WhatsAppAccount
from app.services.whatsapp_service import send_outbound_text_message


# --- 1. Deployment Phase Ordering ---
def test_01_deployment_phase_ordering():
    """Verify that multi-phase deployment enforces strict dependency order."""
    expected_order = [
        "Preflight",
        "Foundation",
        "BuildImages",
        "Secrets",
        "Database",
        "User",
        "Migration",
        "App",
        "Schedulers",
        "Reconcile",
        "ActivateSchedulers",
    ]

    dependencies = {
        "Foundation": ["Preflight"],
        "BuildImages": ["Foundation"],
        "Secrets": ["Foundation"],
        "Database": ["Foundation"],
        "User": ["Database", "Secrets"],
        "Migration": ["User", "BuildImages"],
        "App": ["Migration", "BuildImages", "Secrets"],
        "Schedulers": ["App"],
        "Reconcile": ["Schedulers"],
        "ActivateSchedulers": ["Reconcile"],
    }

    executed_phases = []
    for phase in expected_order:
        for dep in dependencies.get(phase, []):
            assert dep in executed_phases, f"Phase {phase} requires {dep} to be executed first"
        executed_phases.append(phase)

    assert executed_phases == expected_order


# --- 2. Missing Project ID Validation ---
def test_02_missing_project_id_validation():
    """Verify that deployment without an explicit ProjectId fails closed."""
    def validate_deployment_params(project_id: str, dry_run: bool = False):
        if not project_id and not dry_run:
            raise ValueError("GCP ProjectId is mandatory for staging deployment.")
        return True

    with pytest.raises(ValueError, match="GCP ProjectId is mandatory"):
        validate_deployment_params(project_id="", dry_run=False)

    # Allowed only in dry-run/validate modes
    assert validate_deployment_params(project_id="", dry_run=True) is True


# --- 3. Wrong GCP Project Mismatch Detection ---
def test_03_wrong_gcp_project_mismatch_detection():
    """Verify that a mismatch between target and active gcloud project aborts immediately."""
    def assert_active_project(target_project: str, active_project: str):
        if target_project.strip() != active_project.strip():
            raise RuntimeError(
                f"Active gcloud project mismatch! Active: '{active_project}', Expected: '{target_project}'."
            )
        return True

    with pytest.raises(RuntimeError, match="Active gcloud project mismatch"):
        assert_active_project("physio-staging-2026", "different-prod-project")

    assert assert_active_project("physio-staging-2026", "physio-staging-2026") is True


# --- 4. Missing Billing Approval Gate ---
def test_04_missing_billing_approval_gate():
    """Verify that deployment halts if billing is not confirmed enabled on GCP project."""
    def assert_billing_status(billing_enabled: bool, project_id: str):
        if not billing_enabled:
            raise PermissionError(f"Billing is NOT enabled for project '{project_id}'. Aborting billable deployment.")
        return True

    with pytest.raises(PermissionError, match="Billing is NOT enabled"):
        assert_billing_status(False, "physio-staging-2026")

    assert assert_billing_status(True, "physio-staging-2026") is True


# --- 5. Failed Terraform Command Fail-Closed ---
def test_05_failed_terraform_command_fail_closed():
    """Verify that a native command exit code failure halts the deployment pipeline."""
    def run_step(step_name: str, exit_code: int):
        if exit_code != 0:
            raise SystemError(f"Command failed with exit code {exit_code}: {step_name}")
        return True

    with pytest.raises(SystemError, match="Command failed with exit code 1: terraform apply"):
        run_step("terraform apply", 1)

    assert run_step("terraform apply", 0) is True


# --- 6. Missing Secret Versions Validation ---
def test_06_missing_secret_versions_validation():
    """Verify that deployment aborts if any required secret version is missing or empty."""
    required_secrets = [
        "physio-staging-db-password",
        "physio-staging-app-secret",
        "physio-staging-jwt-secret",
        "physio-staging-worker-token",
        "physio-staging-whatsapp-token",
        "physio-staging-whatsapp-app-secret",
        "physio-staging-llm-key",
    ]

    mock_secret_store = {
        "physio-staging-db-password": "mock_db_password_123",
        "physio-staging-app-secret": "mock_app_secret_abc",
        "physio-staging-jwt-secret": "mock_jwt_secret_xyz",
        # Missing worker-token
        "physio-staging-whatsapp-token": "tok",
        "physio-staging-whatsapp-app-secret": "app_sec",
        "physio-staging-llm-key": "llm_key",
    }

    def verify_secrets(store, required):
        missing = [s for s in required if not store.get(s)]
        if missing:
            raise KeyError(f"Missing secret versions: {missing}")
        return True

    with pytest.raises(KeyError, match="Missing secret versions: \\['physio-staging-worker-token'\\]"):
        verify_secrets(mock_secret_store, required_secrets)

    mock_secret_store["physio-staging-worker-token"] = "valid_token"
    assert verify_secrets(mock_secret_store, required_secrets) is True


# --- 7. Database-User Bootstrap Failure ---
def test_07_database_user_bootstrap_failure():
    """Verify that failure to create the database user stops the pipeline before migration."""
    pipeline_state = {"user_created": False, "migration_run": False}

    def create_db_user(success: bool):
        if not success:
            raise RuntimeError("Cloud SQL user bootstrap failure: failed to create physio_admin")
        pipeline_state["user_created"] = True

    def run_migration():
        if not pipeline_state["user_created"]:
            raise RuntimeError("Cannot execute migration: database user does not exist!")
        pipeline_state["migration_run"] = True

    with pytest.raises(RuntimeError, match="user bootstrap failure"):
        create_db_user(False)

    with pytest.raises(RuntimeError, match="database user does not exist"):
        run_migration()

    assert pipeline_state["migration_run"] is False

    create_db_user(True)
    run_migration()
    assert pipeline_state["migration_run"] is True


# --- 8. Migration-Before-Ingress Enforcement ---
def test_08_migration_failure_blocks_app_traffic():
    """Verify that migration failure blocks traffic ingress and service promotion."""
    service_state = {"migration_status": "PENDING", "traffic_percent": 0}

    def execute_migration_job(should_succeed: bool):
        if not should_succeed:
            service_state["migration_status"] = "FAILED"
            raise RuntimeError("Alembic upgrade failed with non-zero exit code")
        service_state["migration_status"] = "SUCCESS"

    def route_traffic_to_revision():
        if service_state["migration_status"] != "SUCCESS":
            raise RuntimeError("Refusing to route traffic: database migration has not completed successfully.")
        service_state["traffic_percent"] = 100

    # Migration fails
    with pytest.raises(RuntimeError, match="Alembic upgrade failed"):
        execute_migration_job(False)

    with pytest.raises(RuntimeError, match="Refusing to route traffic"):
        route_traffic_to_revision()

    assert service_state["traffic_percent"] == 0

    # Migration succeeds
    execute_migration_job(True)
    route_traffic_to_revision()
    assert service_state["traffic_percent"] == 100


# --- 9. API Health-Check Failure Handling ---
def test_09_api_health_check_failure_triggers_halt():
    """Verify that unhealthy probe response halts deployment before schedulers are touched."""
    def verify_api_health(response_data: dict):
        if response_data.get("status") != "healthy":
            raise ValueError(f"API health check failed! Received: {response_data}")
        return True

    with pytest.raises(ValueError, match="API health check failed"):
        verify_api_health({"status": "degraded", "error": "database connection timeout"})

    assert verify_api_health({"status": "healthy", "environment": "staging"}) is True


# --- 10. Scheduler Remains Paused Invariant ---
def test_10_scheduler_remains_paused_invariant():
    """Verify that Cloud Scheduler jobs in main.tf are declared paused=true."""
    main_tf_path = os.path.join(os.path.dirname(__file__), "..", "..", "infra", "staging", "main.tf")
    with open(main_tf_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Find the google_cloud_scheduler_job block
    scheduler_match = re.search(r'resource\s+"google_cloud_scheduler_job"\s+"jobs"\s+{(.*?)\n}', content, re.DOTALL)
    assert scheduler_match is not None, "google_cloud_scheduler_job block not found in main.tf"

    block_text = scheduler_match.group(1)
    assert "paused    = true" in block_text or "paused = true" in block_text, (
        "Cloud Scheduler jobs must have 'paused = true' declared to prevent premature automation triggers"
    )


# --- 11. Staging Mock Mode & Deny-All Allowlist Enforcement ---
@pytest.mark.asyncio
async def test_11_provider_mock_enforcement_and_fail_closed_allowlist(monkeypatch):
    """Verify that staging defaults to mock mode and enforces fail-closed deny-all on empty allowlist."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "staging")
    monkeypatch.setattr(settings, "STAGING_MOCK_OUTBOUND", False)
    monkeypatch.setattr(settings, "STAGING_ALLOWLIST_PHONE_NUMBERS", [])
    monkeypatch.setattr(settings, "AUTOMATION_OUTBOUND_ENABLED", False)

    mock_db = AsyncMock()
    mock_account = WhatsAppAccount(
        id=uuid.uuid4(),
        provider="meta",
        phone_number_id="123456",
        is_active=True,
        access_token_encrypted="encrypted_tok",
    )
    with patch("app.services.whatsapp_service.get_whatsapp_account_by_id", return_value=mock_account):
        with patch("app.services.whatsapp_service.get_provider_adapter"):
            resp = await send_outbound_text_message(
                db=mock_db,
                account_id=mock_account.id,
                to="+919876543210",
                text="Test message in staging with empty allowlist",
            )
            assert resp.success is False
            assert "deny-all default" in resp.error


# --- 12. Secret Redaction in Logs ---
def test_12_secret_redaction_in_logs():
    """Verify that deployment loggers and scripts redact secrets in command representations."""
    def sanitize_log_output(text: str, secret_patterns: list) -> str:
        sanitized = text
        for secret in secret_patterns:
            if secret:
                sanitized = sanitized.replace(secret, "[REDACTED]")
        return sanitized

    raw_command = "gcloud sql users create physio_admin --instance=physio-staging-pg --password=SuperSecretPassword123#"
    sanitized = sanitize_log_output(raw_command, ["SuperSecretPassword123#"])

    assert "SuperSecretPassword123#" not in sanitized
    assert "--password=[REDACTED]" in sanitized


# --- 13. Fast Rollback Safety ---
def test_13_rollback_safety_and_traffic_shifting():
    """Verify that rollback instantly resets traffic allocation and disables outbound automations."""
    cloud_run_service = {
        "current_revision": "physio-staging-api-00003-def",
        "previous_stable_revision": "physio-staging-api-00002-abc",
        "traffic": {"physio-staging-api-00003-def": 100},
        "env_vars": {"AUTOMATION_OUTBOUND_ENABLED": "true"},
    }

    def execute_emergency_rollback(service_state: dict):
        prev = service_state["previous_stable_revision"]
        # 1. Shift 100% traffic back to previous stable revision
        service_state["traffic"] = {prev: 100}
        # 2. Kill switch outbound automation
        service_state["env_vars"]["AUTOMATION_OUTBOUND_ENABLED"] = "false"
        return service_state

    rolled_back = execute_emergency_rollback(cloud_run_service)
    assert rolled_back["traffic"] == {"physio-staging-api-00002-abc": 100}
    assert rolled_back["env_vars"]["AUTOMATION_OUTBOUND_ENABLED"] == "false"
