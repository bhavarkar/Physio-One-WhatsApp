"""User Management Service with Safeguards and RBAC Integrity

Single Organization Edition: Physio One Clinic.
"""
import uuid
from typing import Optional, Tuple, List
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.core.security import hash_password
from app.core.rbac import ROLE_OWNER, ROLE_ADMIN
from app.models.user import User, Role
from app.services.auth_service import log_audit_event, revoke_all_sessions


async def count_active_owners(db: AsyncSession) -> int:
    """Return the total count of currently active users with the Owner role."""
    owner_role = (await db.execute(select(Role).where(Role.name == ROLE_OWNER))).scalar_one_or_none()
    if not owner_role:
        return 0
    count_stmt = select(func.count(User.id)).where(
        and_(User.role_id == owner_role.id, User.is_active == True)
    )
    return (await db.execute(count_stmt)).scalar() or 0


async def list_users(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
    role_id: Optional[uuid.UUID] = None,
    is_active: Optional[bool] = None,
) -> Tuple[List[User], int]:
    """Retrieve paginated staff users with filters."""
    query = select(User).options(selectinload(User.role))
    count_query = select(func.count(User.id))

    filters = []
    if role_id:
        filters.append(User.role_id == role_id)
    if is_active is not None:
        filters.append(User.is_active == is_active)
    if search:
        search_filter = or_(
            User.email.ilike(f"%{search}%"),
            User.full_name.ilike(f"%{search}%"),
        )
        filters.append(search_filter)

    if filters:
        query = query.where(and_(*filters))
        count_query = count_query.where(and_(*filters))

    total = (await db.execute(count_query)).scalar() or 0

    offset = (page - 1) * page_size
    query = query.order_by(User.created_at.desc()).offset(offset).limit(page_size)
    users = (await db.execute(query)).scalars().all()

    return list(users), total


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> Optional[User]:
    """Fetch user by UUID with role and permissions."""
    stmt = (
        select(User)
        .options(selectinload(User.role).selectinload(Role.permissions))
        .where(User.id == user_id)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def create_user(
    db: AsyncSession,
    requesting_user: User,
    email: str,
    password: str,
    full_name: str,
    role_id: uuid.UUID,
    ip_address: Optional[str] = None,
) -> User:
    """Create a new staff user with authorization safeguards."""
    clean_email = email.strip().lower()

    # Check email duplicate
    existing = (await db.execute(select(User).where(User.email == clean_email))).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email address already exists.",
        )

    # Fetch target role
    target_role = (await db.execute(select(Role).where(Role.id == role_id))).scalar_one_or_none()
    if not target_role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Specified role does not exist.")

    # Privilege escalation safeguard: Only an Owner can assign the Owner role
    if target_role.name == ROLE_OWNER and requesting_user.role.name != ROLE_OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an Owner can create another Owner account.",
        )

    new_user = User(
        role_id=target_role.id,
        email=clean_email,
        password_hash=hash_password(password),
        full_name=full_name.strip(),
        is_active=True,
    )
    db.add(new_user)
    await db.flush()

    await log_audit_event(
        db,
        action="USER_CREATED",
        resource_type="users",
        resource_id=str(new_user.id),
        user_id=requesting_user.id,
        ip_address=ip_address,
        payload={"email": clean_email, "role": target_role.name, "created_by": requesting_user.email},
    )

    await db.commit()
    return await get_user_by_id(db, new_user.id)


async def update_user(
    db: AsyncSession,
    requesting_user: User,
    target_user_id: uuid.UUID,
    email: Optional[str] = None,
    full_name: Optional[str] = None,
    role_id: Optional[uuid.UUID] = None,
    is_active: Optional[bool] = None,
    ip_address: Optional[str] = None,
) -> User:
    """Update user with last-active-Owner protection and privilege escalation prevention."""
    target_user = await get_user_by_id(db, target_user_id)
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    is_self = (requesting_user.id == target_user.id)
    is_target_owner = (target_user.role.name == ROLE_OWNER)
    is_requester_owner = (requesting_user.role.name == ROLE_OWNER)

    # Safeguard 1: Non-owners cannot modify an Owner
    if is_target_owner and not is_requester_owner and not is_self:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied. Only an Owner can modify another Owner account.",
        )

    # Safeguard 2: Self-demotion / self-deactivation prevention
    if is_self:
        if role_id is not None and role_id != target_user.role_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot change your own role. Ask an administrator.",
            )
        if is_active is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot deactivate your own account.",
            )

    # Safeguard 3: Last active Owner protection
    active_owners = await count_active_owners(db)
    will_demote_owner = is_target_owner and role_id is not None and role_id != target_user.role_id
    will_deactivate_owner = is_target_owner and is_active is False

    if (will_demote_owner or will_deactivate_owner) and active_owners <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot demote or deactivate the last remaining active Owner.",
        )

    # Safeguard 4: Privilege escalation - non-owners cannot promote anyone to Owner
    if role_id is not None and role_id != target_user.role_id:
        new_role = (await db.execute(select(Role).where(Role.id == role_id))).scalar_one_or_none()
        if not new_role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Specified role does not exist.")
        if new_role.name == ROLE_OWNER and not is_requester_owner:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only an Owner can promote a user to the Owner role.",
            )
        target_user.role_id = new_role.id

    # Email updates (check uniqueness)
    if email is not None:
        clean_email = email.strip().lower()
        if clean_email != target_user.email:
            existing = (await db.execute(select(User).where(User.email == clean_email))).scalar_one_or_none()
            if existing:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already in use.")
            target_user.email = clean_email

    if full_name is not None:
        target_user.full_name = full_name.strip()

    if is_active is not None:
        target_user.is_active = is_active
        # If deactivating, immediately revoke all active sessions
        if not is_active:
            await revoke_all_sessions(db, target_user.id, revoked_by_user_id=requesting_user.id)

    await log_audit_event(
        db,
        action="USER_UPDATED",
        resource_type="users",
        resource_id=str(target_user.id),
        user_id=requesting_user.id,
        ip_address=ip_address,
        payload={"target_email": target_user.email, "updated_by": requesting_user.email},
    )

    await db.commit()
    return await get_user_by_id(db, target_user.id)


async def deactivate_user(
    db: AsyncSession,
    requesting_user: User,
    target_user_id: uuid.UUID,
    ip_address: Optional[str] = None,
) -> User:
    """Deactivate a user and revoke all sessions."""
    return await update_user(
        db,
        requesting_user=requesting_user,
        target_user_id=target_user_id,
        is_active=False,
        ip_address=ip_address,
    )
