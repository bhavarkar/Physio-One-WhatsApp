"""API and RBAC Integration Tests for Knowledge Base, Documents, and Retrieval Endpoints."""
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import Role
from app.services.agent_service import AgentService


async def setup_test_users(client: AsyncClient, async_session: AsyncSession):
    """Initializes system owner and creates an operator and viewer."""
    setup_resp = await client.post(
        "/api/v1/auth/setup",
        json={"email": "owner_kb@physio.test", "password": "OwnerPass2026!", "full_name": "KB Owner"},
    )
    assert setup_resp.status_code == 201
    owner_csrf = client.cookies.get("csrf_token")

    roles = (await async_session.execute(select(Role))).scalars().all()
    role_map = {r.name: r.id for r in roles}

    # Create Operator
    await client.post(
        "/api/v1/users",
        json={
            "email": "operator_kb@physio.test",
            "password": "OperatorPass2026!",
            "full_name": "KB Operator",
            "role_id": str(role_map["Operator"]),
        },
        headers={"X-CSRF-Token": owner_csrf},
    )

    # Create Viewer
    await client.post(
        "/api/v1/users",
        json={
            "email": "viewer_kb@physio.test",
            "password": "ViewerPass2026!",
            "full_name": "KB Viewer",
            "role_id": str(role_map["Viewer"]),
        },
        headers={"X-CSRF-Token": owner_csrf},
    )

    return owner_csrf


@pytest.mark.asyncio
async def test_knowledge_base_rbac_and_csrf(client: AsyncClient, async_session: AsyncSession):
    await AgentService.ensure_default_ai_entities(async_session)
    owner_csrf = await setup_test_users(client, async_session)

    # 1. Owner can list KBs
    resp = await client.get("/api/v1/knowledge/bases")
    assert resp.status_code == 200
    kbs = resp.json()
    assert len(kbs) >= 1

    # 2. Owner can create a new KB (with CSRF)
    create_resp = await client.post(
        "/api/v1/knowledge/bases",
        json={
            "name": "Sports Injury Protocols",
            "description": "Verified sports physiotherapy treatment protocols.",
            "embedding_model": "text-embedding-3-small",
            "vector_dimension": 1536,
        },
        headers={"X-CSRF-Token": owner_csrf},
    )
    assert create_resp.status_code == 201
    kb_id = create_resp.json()["id"]

    # 3. Mutating without CSRF must fail (403 Forbidden)
    no_csrf_resp = await client.post(
        "/api/v1/knowledge/bases",
        json={"name": "No CSRF KB"},
    )
    assert no_csrf_resp.status_code == 403

    # 4. Login as Viewer
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "viewer_kb@physio.test", "password": "ViewerPass2026!"},
    )
    assert login_resp.status_code == 200
    viewer_csrf = client.cookies.get("csrf_token")

    # Viewer can read KBs
    viewer_read = await client.get("/api/v1/knowledge/bases")
    assert viewer_read.status_code == 200

    # Viewer CANNOT create KB (403 Forbidden)
    viewer_create = await client.post(
        "/api/v1/knowledge/bases",
        json={"name": "Viewer Forbidden KB"},
        headers={"X-CSRF-Token": viewer_csrf},
    )
    assert viewer_create.status_code == 403

    # Viewer CANNOT delete KB (403 Forbidden)
    viewer_del = await client.delete(
        f"/api/v1/knowledge/bases/{kb_id}",
        headers={"X-CSRF-Token": viewer_csrf},
    )
    assert viewer_del.status_code == 403


@pytest.mark.asyncio
async def test_document_upload_and_search_api(client: AsyncClient, async_session: AsyncSession):
    await AgentService.ensure_default_ai_entities(async_session)
    owner_csrf = await setup_test_users(client, async_session)

    # 1. Login as Owner
    await client.post(
        "/api/v1/auth/login",
        json={"email": "owner_kb@physio.test", "password": "OwnerPass2026!"},
    )
    owner_csrf = client.cookies.get("csrf_token")

    # 2. Get default KB
    kbs = (await client.get("/api/v1/knowledge/bases")).json()
    kb_id = kbs[0]["id"]

    # 3. Upload Document as Owner
    file_content = b"Physio One clinic hours: 9 AM to 8 PM Monday to Saturday. Closed on Sundays."
    files = {"file": ("clinic_faq.txt", file_content, "text/plain")}
    data = {"knowledge_base_id": kb_id, "title": "Clinic FAQ & Hours"}

    upload_resp = await client.post(
        "/api/v1/knowledge/documents/upload",
        data=data,
        files=files,
        headers={"X-CSRF-Token": owner_csrf},
    )
    assert upload_resp.status_code == 201
    doc_data = upload_resp.json()
    assert doc_data["status"] == "ready"
    assert doc_data["chunk_count"] > 0
    doc_id = doc_data["id"]

    # 4. Search endpoint (Operator can search)
    await client.post(
        "/api/v1/auth/login",
        json={"email": "operator_kb@physio.test", "password": "OperatorPass2026!"},
    )
    op_csrf = client.cookies.get("csrf_token")

    search_resp = await client.post(
        "/api/v1/knowledge/search",
        json={"query": "Are you open on Sundays?", "knowledge_base_id": kb_id, "top_k": 3},
        headers={"X-CSRF-Token": op_csrf},
    )
    assert search_resp.status_code == 200
    search_data = search_resp.json()
    assert search_data["count"] > 0
    assert any("Sundays" in s["chunk_text"] for s in search_data["snippets"])
