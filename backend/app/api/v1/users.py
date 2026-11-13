"""User Management and Roles API Routes

Single Organization Edition: Physio One Clinic.
"""
from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, Request, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.rbac import ROLE_OWNER, ROLE_ADMIN
from app.api.deps import get_current_user, require_role, require_permission
from app.models.user import User, Role
from app.schemas.user import (
    UserResponse,
    UserCreateRequest,
    UserUpdateRequest,
    UserListResponse,
    RoleResponse,
)
from app.services.user_service import (
    list_users,
    get_user_by_id,
    create_user,
    update_user,
    deactivate_user,
)
from app.services.auth_service import revoke_all_sessions

router = APIRouter(prefix="/users", tags=["User Management"])


@router.get("/roles", response_model=List[RoleResponse])
async def get_all_roles(
    current_user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """List all system roles and their configured permissions."""
    stmt = select(Role).options(selectinload(Role.permissions)).order_by(Role.name)
    roles = (await db.execute(stmt)).scalars().all()
    return roles


@router.get("", response_model=UserListResponse)
async def get_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    role_id: Optional[uuid.UUID] = Query(None),
    is_active: Optional[bool] = Query(None),
    current_user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """List staff users with pagination and search filters."""
    users, total = await list_users(
        db,
        page=page,
        page_size=page_size,
        search=search,
        role_id=role_id,
        is_active=is_active,
    )
    return UserListResponse(
        users=users,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def add_new_user(
    payload: UserCreateRequest,
    request: Request,
    current_user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Create a new staff user."""
    client_ip = request.client.host if request.client else None
    return await create_user(
        db,
        requesting_user=current_user,
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        role_id=payload.role_id,
        ip_address=client_ip,
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user_details(
    user_id: uuid.UUID,
    current_user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Get profile and role details of a specific user."""
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return user


@router.put("/{user_id}", response_model=UserResponse)
async def modify_user(
    user_id: uuid.UUID,
    payload: UserUpdateRequest,
    request: Request,
    current_user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Update user attributes with last-active-Owner protection and privilege escalation checks."""
    client_ip = request.client.host if request.client else None
    return await update_user(
        db,
        requesting_user=current_user,
        target_user_id=user_id,
        email=payload.email,
        full_name=payload.full_name,
        role_id=payload.role_id,
        is_active=payload.is_active,
        ip_address=client_ip,
    )


@router.delete("/{user_id}", response_model=UserResponse)
async def remove_user(
    user_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate a staff user account and revoke all their sessions."""
    client_ip = request.client.host if request.client else None
    return await deactivate_user(
        db,
        requesting_user=current_user,
        target_user_id=user_id,
        ip_address=client_ip,
    )


@router.post("/{user_id}/revoke-sessions")
async def force_revoke_user_sessions(
    user_id: uuid.UUID,
    current_user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Force revoke all active sessions for a specific user."""
    count = await revoke_all_sessions(db, user_id=user_id, revoked_by_user_id=current_user.id)
    return {"message": f"Successfully revoked {count} active session(s) for user."}
