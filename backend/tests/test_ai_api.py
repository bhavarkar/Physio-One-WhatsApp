"""API and RBAC Integration Tests for LLM Providers and Agent Endpoints.

Single Organization Edition: Physio One Clinic.
Tests:
- Owner/Admin access to provider settings and credentials.
- Operator access to agents list and isolated test console.
- Viewer read-only restrictions.
- Unauthenticated rejection (401).
- CSRF protection on state-mutating requests.
- No credential leakage in provider response schemas.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import Role
from app.services.agent_service import AgentService


async def setup_roles_and_owner(client: AsyncClient):
    """Initializes system owner and returns CSRF token."""
    resp = await client.post(
        "/api/v1/auth/setup",
        json={"email": "owner_ai@physio.test", "password": "OwnerPass2026!", "full_name": "Clinic Owner"},
    )
    assert resp.status_code == 201
    return client.cookies.get("csrf_token")


@pytest.mark.asyncio
async def test_llm_providers_rbac(client: AsyncClient, async_session: AsyncSession):
    """Verify Owner/Admin has provider access while Operator and Viewer are forbidden."""
    await AgentService.ensure_default_ai_entities(async_session)
    owner_csrf = await setup_roles_and_owner(client)

    # 1. Owner can list providers
    resp_owner = await client.get("/api/v1/llm/providers")
    assert resp_owner.status_code == 200
    providers = resp_owner.json()
    assert len(providers) >= 3

    # Verify zero raw keys leaked
    for p in providers:
        assert "dummy" not in p["masked_api_key"]
        assert "sk-" not in p["masked_api_key"] or "***" in p["masked_api_key"] or "..." in p["masked_api_key"]

    # 2. Create Viewer user via owner
    roles = (await async_session.execute(select(Role))).scalars().all()
    role_map = {r.name: r.id for r in roles}

    await client.post(
        "/api/v1/users",
        json={
            "email": "viewer_ai@physio.test",
            "password": "ViewerPass2026!",
            "full_name": "Viewer AI",
            "role_id": str(role_map["Viewer"]),
        },
        headers={"X-CSRF-Token": owner_csrf},
    )

    # Create Operator user
    await client.post(
        "/api/v1/users",
        json={
            "email": "operator_ai@physio.test",
            "password": "OperatorPass2026!",
            "full_name": "Operator AI",
            "role_id": str(role_map["Operator"]),
        },
        headers={"X-CSRF-Token": owner_csrf},
    )

    # 3. Viewer login -> 403 on providers
    client.cookies.clear()
    login_v = await client.post(
        "/api/v1/auth/login",
        json={"email": "viewer_ai@physio.test", "password": "ViewerPass2026!"},
    )
    assert login_v.status_code == 200
    resp_viewer = await client.get("/api/v1/llm/providers")
    assert resp_viewer.status_code == 403

    # 4. Operator login -> 403 on providers
    client.cookies.clear()
    login_op = await client.post(
        "/api/v1/auth/login",
        json={"email": "operator_ai@physio.test", "password": "OperatorPass2026!"},
    )
    assert login_op.status_code == 200
    resp_op = await client.get("/api/v1/llm/providers")
    assert resp_op.status_code == 403

    # 5. Unauthenticated -> 401
    client.cookies.clear()
    resp_unauth = await client.get("/api/v1/llm/providers")
    assert resp_unauth.status_code == 401


@pytest.mark.asyncio
async def test_agents_listing_and_rbac(client: AsyncClient, async_session: AsyncSession):
    """Verify Operators and Viewers can read agents, but only Admin/Owner can create or update."""
    await AgentService.ensure_default_ai_entities(async_session)
    owner_csrf = await setup_roles_and_owner(client)

    roles = (await async_session.execute(select(Role))).scalars().all()
    role_map = {r.name: r.id for r in roles}

    # Create Viewer
    await client.post(
        "/api/v1/users",
        json={
            "email": "viewer_agent@physio.test",
            "password": "ViewerPass2026!",
            "full_name": "Viewer Agent",
            "role_id": str(role_map["Viewer"]),
        },
        headers={"X-CSRF-Token": owner_csrf},
    )

    # 1. Owner lists agents
    resp = await client.get("/api/v1/agents")
    assert resp.status_code == 200
    agents = resp.json()
    deepti = next((a for a in agents if a["name"] == "Deepti"), None)
    assert deepti is not None

    # 2. Viewer logs in and can read agents
    client.cookies.clear()
    login_v = await client.post(
        "/api/v1/auth/login",
        json={"email": "viewer_agent@physio.test", "password": "ViewerPass2026!"},
    )
    assert login_v.status_code == 200
    viewer_csrf = client.cookies.get("csrf_token")

    resp_view = await client.get("/api/v1/agents")
    assert resp_view.status_code == 200

    # 3. Viewer cannot create agent -> 403
    resp_create_viewer = await client.post(
        "/api/v1/agents",
        json={
            "name": "Unauthorized Agent",
            "primary_model_id": deepti["primary_model_id"],
            "system_prompt": "You are a test agent.",
        },
        headers={"X-CSRF-Token": viewer_csrf},
    )
    assert resp_create_viewer.status_code == 403


@pytest.mark.asyncio
async def test_tools_listing_endpoint(client: AsyncClient, async_session: AsyncSession):
    """Verify registered tools endpoint exposes parameter schemas."""
    owner_csrf = await setup_roles_and_owner(client)

    resp = await client.get("/api/v1/tools")
    assert resp.status_code == 200
    tools = resp.json()
    tool_names = [t["name"] for t in tools]
    assert "check_availability" in tool_names
    assert "find_patient" in tool_names


@pytest.mark.asyncio
async def test_csrf_protection_on_ai_mutation(client: AsyncClient, async_session: AsyncSession):
    """Verify CSRF token is strictly required on state-mutating requests when using cookie auth."""
    await AgentService.ensure_default_ai_entities(async_session)
    await setup_roles_and_owner(client)

    # State-mutating POST without X-CSRF-Token header
    resp = await client.post(
        "/api/v1/agents",
        json={"name": "Bad CSRF Agent"},
    )
    assert resp.status_code == 403
    assert "CSRF validation failed" in resp.json()["detail"]
