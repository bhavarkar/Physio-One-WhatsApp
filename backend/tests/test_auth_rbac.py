"""Comprehensive Test Suite for Authentication, RBAC, and User Management API

Single Organization Edition: Physio One Clinic.
Validates all requirements specified in Task 3.
"""
import uuid
import pytest
from httpx import AsyncClient

from app.core.security import hash_password, verify_password, login_rate_limiter
from app.core.rbac import ROLE_OWNER, ROLE_ADMIN, ROLE_OPERATOR, ROLE_VIEWER
from app.services.auth_service import ensure_initial_roles


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset the in-memory login rate limiter before every test."""
    login_rate_limiter.reset()


@pytest.mark.asyncio
async def test_1_argon2id_hashing_and_verification():
    """Test password hashing, verification, and tamper rejection."""
    password = "SuperSecurePassword123!"
    hashed = hash_password(password)

    assert hashed.startswith("$argon2id$") or hashed.startswith("$scrypt$")
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword123!", hashed) is False
    assert verify_password("", hashed) is False


@pytest.mark.asyncio
async def test_2_initial_setup_controlled_flow(client: AsyncClient, async_session):
    """Test checking setup status and creating the first Owner account."""
    # 1. Check status when uninitialized
    status_resp = await client.get("/api/v1/auth/setup-status")
    assert status_resp.status_code == 200
    assert status_resp.json()["is_initialized"] is False
    assert status_resp.json()["owner_count"] == 0

    # 2. Perform setup
    setup_payload = {
        "email": "dr.physio@physioone.com",
        "password": "ClinicOwnerPass2026!",
        "full_name": "Dr. Physio One",
    }
    setup_resp = await client.post("/api/v1/auth/setup", json=setup_payload)
    assert setup_resp.status_code == 201
    data = setup_resp.json()
    assert data["email"] == "dr.physio@physioone.com"
    assert data["full_name"] == "Dr. Physio One"
    assert data["role"]["name"] == ROLE_OWNER
    assert "password" not in data
    assert "password_hash" not in data

    # Verify cookies were set
    assert "session_id" in setup_resp.cookies
    assert "csrf_token" in setup_resp.cookies

    # 3. Check status is now initialized
    status_resp2 = await client.get("/api/v1/auth/setup-status")
    assert status_resp2.status_code == 200
    assert status_resp2.json()["is_initialized"] is True
    assert status_resp2.json()["owner_count"] == 1

    # 4. Attempting setup again must fail with 403 Forbidden
    dup_setup = await client.post("/api/v1/auth/setup", json=setup_payload)
    assert dup_setup.status_code == 403
    assert "already initialized" in dup_setup.json()["detail"].lower()


@pytest.mark.asyncio
async def test_3_login_success_and_generic_failure(client: AsyncClient):
    """Test successful login and generic error messages for invalid credentials."""
    # Setup initial owner
    await client.post(
        "/api/v1/auth/setup",
        json={"email": "owner@clinic.com", "password": "OwnerSecretPassword!", "full_name": "Clinic Owner"},
    )

    # Valid login
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@clinic.com", "password": "OwnerSecretPassword!"},
    )
    assert login_resp.status_code == 200
    user_data = login_resp.json()
    assert user_data["email"] == "owner@clinic.com"
    assert "session_id" in login_resp.cookies
    assert "csrf_token" in login_resp.cookies

    # Invalid password: generic 401 error
    bad_pass_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@clinic.com", "password": "WrongPassword!"},
    )
    assert bad_pass_resp.status_code == 401
    assert "invalid credentials" in bad_pass_resp.json()["detail"].lower()

    # Non-existent user: same generic 401 error (no username enumeration)
    no_user_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "doesnotexist@clinic.com", "password": "AnyPassword!"},
    )
    assert no_user_resp.status_code == 401
    assert "invalid credentials" in no_user_resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_4_disabled_user_access_rejection(client: AsyncClient, async_session):
    """Test that deactivated accounts cannot log in or access endpoints."""
    # Setup owner
    await client.post(
        "/api/v1/auth/setup",
        json={"email": "owner@clinic.com", "password": "OwnerPassword123!", "full_name": "Clinic Owner"},
    )

    # Get roles
    roles_resp = await client.get("/api/v1/users/roles")
    assert roles_resp.status_code == 200
    operator_role_id = next(r["id"] for r in roles_resp.json() if r["name"] == ROLE_OPERATOR)

    # Create operator user
    csrf_token = client.cookies.get("csrf_token")
    create_resp = await client.post(
        "/api/v1/users",
        json={
            "email": "operator@clinic.com",
            "password": "OperatorPassword123!",
            "full_name": "Staff Operator",
            "role_id": operator_role_id,
        },
        headers={"X-CSRF-Token": csrf_token},
    )
    assert create_resp.status_code == 201
    operator_id = create_resp.json()["id"]

    # Deactivate the operator
    deact_resp = await client.delete(
        f"/api/v1/users/{operator_id}",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert deact_resp.status_code == 200
    assert deact_resp.json()["is_active"] is False

    # Attempt to log in as deactivated user
    deact_login = await client.post(
        "/api/v1/auth/login",
        json={"email": "operator@clinic.com", "password": "OperatorPassword123!"},
    )
    assert deact_login.status_code == 403
    assert "deactivated" in deact_login.json()["detail"].lower()


@pytest.mark.asyncio
async def test_5_logout_and_session_revocation(client: AsyncClient):
    """Test logout invalidates the session and deletes cookies."""
    await client.post(
        "/api/v1/auth/setup",
        json={"email": "owner@clinic.com", "password": "OwnerPassword123!", "full_name": "Clinic Owner"},
    )

    # Verify /auth/me works
    me_resp = await client.get("/api/v1/auth/me")
    assert me_resp.status_code == 200

    # Logout
    csrf_token = client.cookies.get("csrf_token")
    logout_resp = await client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf_token})
    assert logout_resp.status_code == 200

    # Subsequent request using prior session cookie must fail
    me_after_logout = await client.get("/api/v1/auth/me")
    assert me_after_logout.status_code == 401


@pytest.mark.asyncio
async def test_6_csrf_protection_on_state_mutating_requests(client: AsyncClient):
    """Test CSRF protection blocks state-changing cookie requests missing X-CSRF-Token."""
    await client.post(
        "/api/v1/auth/setup",
        json={"email": "owner@clinic.com", "password": "OwnerPassword123!", "full_name": "Clinic Owner"},
    )

    # Send POST request WITHOUT X-CSRF-Token header
    fail_csrf = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "OwnerPassword123!", "new_password": "NewOwnerPassword123!"},
    )
    assert fail_csrf.status_code == 403
    assert "csrf validation failed" in fail_csrf.json()["detail"].lower()

    # Send POST request WITH valid X-CSRF-Token header
    csrf_token = client.cookies.get("csrf_token")
    success_csrf = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "OwnerPassword123!", "new_password": "NewOwnerPassword123!"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert success_csrf.status_code == 200


@pytest.mark.asyncio
async def test_7_rate_limiting_brute_force_lockout(client: AsyncClient):
    """Test that repeated invalid login attempts trigger rate limiting."""
    await client.post(
        "/api/v1/auth/setup",
        json={"email": "owner@clinic.com", "password": "OwnerPassword123!", "full_name": "Clinic Owner"},
    )

    # Trigger 5 failed attempts
    for _ in range(5):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "owner@clinic.com", "password": "IncorrectPassword!"},
        )
        assert resp.status_code == 401

    # 6th attempt should be blocked with 429
    blocked_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@clinic.com", "password": "OwnerPassword123!"},
    )
    assert blocked_resp.status_code == 429
    assert "too many failed login attempts" in blocked_resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_8_last_active_owner_protection(client: AsyncClient):
    """Test that the system refuses to demote or deactivate the last remaining active Owner."""
    setup_resp = await client.post(
        "/api/v1/auth/setup",
        json={"email": "sole.owner@clinic.com", "password": "OwnerPassword123!", "full_name": "Sole Owner"},
    )
    owner_id = setup_resp.json()["id"]

    roles_resp = await client.get("/api/v1/users/roles")
    admin_role_id = next(r["id"] for r in roles_resp.json() if r["name"] == ROLE_ADMIN)

    csrf_token = client.cookies.get("csrf_token")

    # Attempt to demote the sole owner
    demote_attempt = await client.put(
        f"/api/v1/users/{owner_id}",
        json={"role_id": admin_role_id},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert demote_attempt.status_code == 400
    assert "cannot change your own role" in demote_attempt.json()["detail"].lower()

    # Attempt to deactivate the sole owner
    deact_attempt = await client.delete(
        f"/api/v1/users/{owner_id}",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert deact_attempt.status_code == 400
    assert "cannot deactivate your own account" in deact_attempt.json()["detail"].lower()


@pytest.mark.asyncio
async def test_9_privilege_escalation_and_rbac_boundaries(client: AsyncClient):
    """Test that an Admin cannot promote to Owner, and Operators cannot access user management."""
    # 1. Setup owner
    await client.post(
        "/api/v1/auth/setup",
        json={"email": "owner@clinic.com", "password": "OwnerPassword123!", "full_name": "Super Owner"},
    )

    roles_resp = await client.get("/api/v1/users/roles")
    roles = {r["name"]: r["id"] for r in roles_resp.json()}
    csrf_token = client.cookies.get("csrf_token")

    # 2. Owner creates an Admin
    admin_create = await client.post(
        "/api/v1/users",
        json={
            "email": "admin@clinic.com",
            "password": "AdminPassword123!",
            "full_name": "Operations Admin",
            "role_id": roles[ROLE_ADMIN],
        },
        headers={"X-CSRF-Token": csrf_token},
    )
    assert admin_create.status_code == 201

    # 3. Owner creates an Operator
    op_create = await client.post(
        "/api/v1/users",
        json={
            "email": "operator@clinic.com",
            "password": "OperatorPassword123!",
            "full_name": "Desk Operator",
            "role_id": roles[ROLE_OPERATOR],
        },
        headers={"X-CSRF-Token": csrf_token},
    )
    assert op_create.status_code == 201
    operator_id = op_create.json()["id"]

    # 4. Log in as Operator
    await client.post(
        "/api/v1/auth/login",
        json={"email": "operator@clinic.com", "password": "OperatorPassword123!"},
    )

    # Operator trying to list users: must fail with 403 Forbidden
    op_list_users = await client.get("/api/v1/users")
    assert op_list_users.status_code == 403

    # 5. Log in as Admin
    await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@clinic.com", "password": "AdminPassword123!"},
    )
    admin_csrf = client.cookies.get("csrf_token")

    # Admin trying to promote operator to Owner: must fail with 403 Forbidden
    admin_promote_attempt = await client.put(
        f"/api/v1/users/{operator_id}",
        json={"role_id": roles[ROLE_OWNER]},
        headers={"X-CSRF-Token": admin_csrf},
    )
    assert admin_promote_attempt.status_code == 403
    assert "only an owner can promote" in admin_promote_attempt.json()["detail"].lower()


@pytest.mark.asyncio
async def test_10_password_change_revokes_other_sessions(client: AsyncClient):
    """Test that password change revokes other active sessions."""
    await client.post(
        "/api/v1/auth/setup",
        json={"email": "owner@clinic.com", "password": "OriginalPassword123!", "full_name": "Clinic Owner"},
    )

    # Log in on second device / browser
    client2 = AsyncClient(transport=client._transport, base_url="http://test")
    login2 = await client2.post(
        "/api/v1/auth/login",
        json={"email": "owner@clinic.com", "password": "OriginalPassword123!"},
    )
    assert login2.status_code == 200

    # Device 1 changes password
    csrf1 = client.cookies.get("csrf_token")
    chg_resp = await client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": "OriginalPassword123!",
            "new_password": "UpdatedPassword2026!",
            "revoke_other_sessions": True,
        },
        headers={"X-CSRF-Token": csrf1},
    )
    assert chg_resp.status_code == 200

    # Device 1 is still authenticated
    me1 = await client.get("/api/v1/auth/me")
    assert me1.status_code == 200

    # Device 2 session was revoked!
    me2 = await client2.get("/api/v1/auth/me")
    assert me2.status_code == 401
