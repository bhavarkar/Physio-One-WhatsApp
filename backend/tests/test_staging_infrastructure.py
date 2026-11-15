"""Task 14: Cloud Tasks opt-in/fail-safe, deterministic dedup; OIDC fails closed.

Negative cases: forged (unsigned) JWT, wrong audience, wrong service-account
email, expired token — all must be rejected. No real Cloud Tasks are created:
dispatch is tested only with CLOUD_TASKS_ENABLED=false (default) or
unconfigured credentials.
"""
import base64
import json
import time

from app.services.cloud_tasks import dispatch_worker_task, task_name_for
from app.core.worker_auth import verify_google_oidc_claims, verify_google_oidc_token
from app.core.config import settings


def _fake_jwt(payload):
    def b64(o):
        return base64.urlsafe_b64encode(json.dumps(o).encode()).decode().rstrip("=")
    return f"{b64({'alg': 'RS256', 'kid': 'fake'})}.{b64(payload)}.forgedsignature"


def _payload(**over):
    p = {"iss": "https://accounts.google.com", "aud": "https://api.example",
         "email": "worker@proj.iam.gserviceaccount.com", "exp": time.time() + 600, "iat": time.time()}
    p.update(over)
    return p


def test_dispatch_disabled_by_default():
    assert dispatch_worker_task("automation", "job-1") == {"dispatched": False, "reason": "cloud_tasks_disabled"}


def test_dispatch_unknown_kind():
    assert dispatch_worker_task("nope", "x")["dispatched"] is False


def test_dispatch_enabled_but_unconfigured_creates_nothing(monkeypatch):
    monkeypatch.setattr(settings, "CLOUD_TASKS_ENABLED", True)
    monkeypatch.setattr(settings, "GCP_PROJECT_ID", None)
    assert dispatch_worker_task("automation", "job-1") == {"dispatched": False, "reason": "cloud_tasks_unconfigured"}


def test_task_name_deterministic_and_unique():
    assert task_name_for("q", "job-1") == task_name_for("q", "job-1")
    assert task_name_for("q", "job-1") != task_name_for("q", "job-2")


def test_valid_claims_accepted_with_explicit_expectations():
    assert verify_google_oidc_claims(_payload(), expected_audience="https://api.example",
                                     expected_email="worker@proj.iam.gserviceaccount.com") is True


def test_wrong_audience_rejected():
    assert verify_google_oidc_claims(_payload(), expected_audience="https://other.example",
                                     expected_email="worker@proj.iam.gserviceaccount.com") is False


def test_wrong_service_account_email_rejected():
    assert verify_google_oidc_claims(_payload(), expected_audience="https://api.example",
                                     expected_email="attacker@proj.iam.gserviceaccount.com") is False


def test_expired_token_rejected():
    assert verify_google_oidc_claims(_payload(exp=time.time() - 100), expected_audience="https://api.example",
                                     expected_email="worker@proj.iam.gserviceaccount.com") is False


def test_bad_issuer_rejected():
    assert verify_google_oidc_claims(_payload(iss="https://evil.example"), expected_audience="https://api.example",
                                     expected_email="worker@proj.iam.gserviceaccount.com") is False


def test_claims_fail_closed_without_configured_audience(monkeypatch):
    monkeypatch.setattr(settings, "OIDC_AUDIENCE", None)
    monkeypatch.setattr(settings, "CLOUD_RUN_SERVICE_URL", None)
    assert verify_google_oidc_claims(_payload()) is False


def test_forged_unsigned_jwt_rejected(monkeypatch):
    """A self-minted token with correct-looking claims must fail signature verification."""
    monkeypatch.setattr(settings, "OIDC_AUDIENCE", "https://api.example")
    monkeypatch.setattr(settings, "WORKER_SERVICE_ACCOUNT_EMAIL", "worker@proj.iam.gserviceaccount.com")
    assert verify_google_oidc_token(_fake_jwt(_payload())) is None
    assert verify_google_oidc_token("not-a-jwt") is None
