"""Authentication, Session Management, and Audit Service

Single Organization Edition: Physio One Clinic.
"""
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, List, Dict
from sqlalchemy import select, func, and_, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.core.config import settings
from app.core.security import (
    hash_password,
    verify_password,
    generate_session_token,
    hash_session_token,
    generate_csrf_token,
    login_rate_limiter,
)
from app.core.rbac import (
    ROLE_OWNER,
    ROLE_ADMIN,
    ROLE_OPERATOR,
    ROLE_VIEWER,
    INITIAL_ROLES,
    ROLE_DEFAULT_PERMISSIONS,
)
from app.models.user import User, Role, Permission, UserSession, AuditLog


async def log_audit_event(
    db: AsyncSession,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    user_id: Optional[uuid.UUID] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    payload: Optional[dict] = None,
):
    """Record an immutable security audit event. Strips sensitive fields from payload."""
    clean_payload = None
    if payload:
        clean_payload = {
            k: ("***" if "password" in k.lower() or "token" in k.lower() or "secret" in k.lower() else v)
            for k, v in payload.items()
        }

    audit_entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=ip_address,
        user_agent=user_agent,
        payload=clean_payload,
    )
    db.add(audit_entry)
    await db.flush()


async def ensure_initial_roles(db: AsyncSession) -> Dict[str, Role]:
    """Ensure all 4 core roles and their default permissions exist in the database."""
    role_map: Dict[str, Role] = {}
    
    for role_name in INITIAL_ROLES:
        role_stmt = select(Role).options(selectinload(Role.permissions)).where(Role.name == role_name)
        role = (await db.execute(role_stmt)).scalar_one_or_none()
        if not role:
            role = Role(
                name=role_name,
                description=f"{role_name} role for Physio One platform",
            )
            db.add(role)
            await db.flush()

            # Seed permissions
            perms = ROLE_DEFAULT_PERMISSIONS.get(role_name, [])
            for p in perms:
                perm_entry = Permission(
                    role_id=role.id,
                    resource=p["resource"],
                    action=p["action"],
                )
                db.add(perm_entry)
            await db.flush()
        
        role_map[role_name] = role

    return role_map


async def get_setup_status(db: AsyncSession) -> Tuple[bool, int]:
    """Check if the system has at least one active Owner."""
    owner_role = (await db.execute(select(Role).where(Role.name == ROLE_OWNER))).scalar_one_or_none()
    if not owner_role:
        return False, 0

    count_stmt = select(func.count(User.id)).where(
        and_(User.role_id == owner_role.id, User.is_active == True)
    )
    owner_count = (await db.execute(count_stmt)).scalar() or 0
    return (owner_count > 0), owner_count


async def setup_initial_owner(
    db: AsyncSession,
    email: str,
    password: str,
    full_name: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Tuple[User, str, str]:
    """Create the initial system Owner account. Allowed only once when zero Owners exist."""
    is_init, _ = await get_setup_status(db)
    if is_init:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System is already initialized with an active Owner.",
        )

    roles = await ensure_initial_roles(db)
    owner_role = roles[ROLE_OWNER]

    hashed = hash_password(password)
    new_owner = User(
        role_id=owner_role.id,
        email=email.strip().lower(),
        password_hash=hashed,
        full_name=full_name.strip(),
        is_active=True,
        last_login_at=datetime.now(timezone.utc),
    )
    db.add(new_owner)
    await db.flush()

    # Generate session
    session_token = generate_session_token()
    token_hash = hash_session_token(session_token)
    csrf_token = generate_csrf_token()

    session = UserSession(
        user_id=new_owner.id,
        token_hash=token_hash,
        ip_address=ip_address,
        user_agent=user_agent,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(session)
    await db.flush()

    await log_audit_event(
        db,
        action="INITIAL_SETUP_OWNER_CREATED",
        resource_type="users",
        resource_id=str(new_owner.id),
        user_id=new_owner.id,
        ip_address=ip_address,
        user_agent=user_agent,
        payload={"email": email, "full_name": full_name},
    )

    await db.commit()
    # Reload with role
    user_stmt = select(User).options(selectinload(User.role)).where(User.id == new_owner.id)
    reloaded_owner = (await db.execute(user_stmt)).scalar_one()

    return reloaded_owner, session_token, csrf_token


async def authenticate_user(
    db: AsyncSession,
    email: str,
    password: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Tuple[User, str, str]:
    """Authenticate staff credentials with rate limiting and generic error responses."""
    clean_email = email.strip().lower()

    # Rate limiting check (per IP and per email)
    rate_key = f"{ip_address or 'unknown'}:{clean_email}"
    is_locked, remaining_sec = login_rate_limiter.is_locked(rate_key)
    if is_locked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed login attempts. Please wait {remaining_sec} seconds before trying again.",
        )

    # Fetch user
    stmt = select(User).options(selectinload(User.role).selectinload(Role.permissions)).where(User.email == clean_email)
    user = (await db.execute(stmt)).scalar_one_or_none()

    # Generic invalid credentials message
    invalid_cred_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials. Please verify your email and password.",
    )

    if not user:
        login_rate_limiter.record_attempt(rate_key, success=False)
        await log_audit_event(
            db,
            action="LOGIN_FAILED",
            resource_type="auth",
            ip_address=ip_address,
            user_agent=user_agent,
            payload={"email": clean_email, "reason": "user_not_found"},
        )
        await db.commit()
        raise invalid_cred_exc

    if not user.is_active:
        await log_audit_event(
            db,
            action="LOGIN_FAILED",
            resource_type="auth",
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            payload={"email": clean_email, "reason": "account_deactivated"},
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Please contact your system Owner.",
        )

    # Verify password hash
    if not verify_password(password, user.password_hash):
        login_rate_limiter.record_attempt(rate_key, success=False)
        await log_audit_event(
            db,
            action="LOGIN_FAILED",
            resource_type="auth",
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            payload={"email": clean_email, "reason": "invalid_password"},
        )
        await db.commit()
        raise invalid_cred_exc

    # Login successful: reset rate limiter
    login_rate_limiter.record_attempt(rate_key, success=True)

    # Update last login
    user.last_login_at = datetime.now(timezone.utc)

    # Create session
    session_token = generate_session_token()
    token_hash = hash_session_token(session_token)
    csrf_token = generate_csrf_token()

    session = UserSession(
        user_id=user.id,
        token_hash=token_hash,
        ip_address=ip_address,
        user_agent=user_agent,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(session)

    await log_audit_event(
        db,
        action="LOGIN_SUCCESS",
        resource_type="auth",
        user_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent,
        payload={"session_id": str(session.id)},
    )

    await db.commit()
    return user, session_token, csrf_token


async def validate_session(
    db: AsyncSession,
    session_token: str,
) -> Optional[Tuple[User, UserSession]]:
    """Validate a session token, returning (user, session) or None if invalid/expired/revoked."""
    if not session_token:
        return None

    token_hash = hash_session_token(session_token)
    stmt = (
        select(UserSession)
        .options(selectinload(UserSession.user).selectinload(User.role).selectinload(Role.permissions))
        .where(UserSession.token_hash == token_hash)
    )
    session = (await db.execute(stmt)).scalar_one_or_none()

    if not session:
        return None

    if session.is_revoked:
        return None

    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at < datetime.now(timezone.utc):
        return None

    if not session.user or not session.user.is_active:
        return None

    return session.user, session


async def revoke_session_by_id(
    db: AsyncSession,
    session_id: uuid.UUID,
    requesting_user: User,
) -> bool:
    """Revoke a specific session. A user can revoke their own, or an Owner/Admin can revoke any."""
    stmt = select(UserSession).where(UserSession.id == session_id)
    session = (await db.execute(stmt)).scalar_one_or_none()
    if not session:
        return False

    # Permission check: user owns session or is Admin/Owner
    is_owner_or_admin = requesting_user.role.name in [ROLE_OWNER, ROLE_ADMIN]
    if session.user_id != requesting_user.id and not is_owner_or_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied to revoke another user's session.",
        )

    session.is_revoked = True
    await log_audit_event(
        db,
        action="SESSION_REVOKED",
        resource_type="user_sessions",
        resource_id=str(session.id),
        user_id=requesting_user.id,
        payload={"target_user_id": str(session.user_id)},
    )
    await db.commit()
    return True


async def revoke_all_sessions(
    db: AsyncSession,
    user_id: uuid.UUID,
    except_session_id: Optional[uuid.UUID] = None,
    revoked_by_user_id: Optional[uuid.UUID] = None,
) -> int:
    """Revoke all active sessions of a user (optionally preserving the current active session)."""
    conditions = [UserSession.user_id == user_id, UserSession.is_revoked == False]
    if except_session_id:
        conditions.append(UserSession.id != except_session_id)

    stmt = update(UserSession).where(and_(*conditions)).values(is_revoked=True)
    result = await db.execute(stmt)
    count = result.rowcount

    await log_audit_event(
        db,
        action="ALL_SESSIONS_REVOKED",
        resource_type="users",
        resource_id=str(user_id),
        user_id=revoked_by_user_id or user_id,
        payload={"revoked_count": count},
    )
    await db.commit()
    return count


async def change_password(
    db: AsyncSession,
    user: User,
    current_password: str,
    new_password: str,
    revoke_other_sessions: bool,
    current_session_id: uuid.UUID,
    ip_address: Optional[str] = None,
) -> bool:
    """Change a user's password, verify current password, and optionally revoke other sessions."""
    if not verify_password(current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )

    user.password_hash = hash_password(new_password)

    if revoke_other_sessions:
        await revoke_all_sessions(
            db,
            user_id=user.id,
            except_session_id=current_session_id,
            revoked_by_user_id=user.id,
        )

    await log_audit_event(
        db,
        action="PASSWORD_CHANGED",
        resource_type="users",
        resource_id=str(user.id),
        user_id=user.id,
        ip_address=ip_address,
    )
    await db.commit()
    return True
