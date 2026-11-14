"""Registered Tools API Endpoints.

Single Organization Edition: Physio One Clinic.
Exposes registered tools, schemas, and parameter requirements to authenticated operators and admins.
"""
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_role
from app.core.rbac import ROLE_OWNER, ROLE_ADMIN, ROLE_OPERATOR
from app.models.user import User
from app.schemas.ai import RegisteredToolResponse
from app.tools.registry import ToolRegistry

router = APIRouter(prefix="/tools", tags=["AI Tools"])


@router.get("", response_model=List[RegisteredToolResponse])
async def list_tools(
    user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN, ROLE_OPERATOR)),
):
    """List all registered AI tools and execution parameter schemas."""
    tools = ToolRegistry.list_tools()
    return [
        RegisteredToolResponse(
            name=t.name,
            description=t.description,
            parameters_schema=t.parameters_schema,
            requires_permission=t.requires_permission,
            is_mutation=t.is_mutation,
            is_idempotent=t.is_idempotent,
            timeout_seconds=t.timeout_seconds,
            is_enabled=True,
        )
        for t in tools
    ]
