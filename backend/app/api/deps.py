"""FastAPI Dependencies for Authentication, Sessions, CSRF, and RBAC

Single Organization Edition: Physio One Clinic.
"""
from typing import Optional, Tuple, Callable
import uuid
from fastapi import Request, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import verify_csrf_token
from app.core.rbac import (
    ROLE_OWNER,
    ROLE_ADMIN,
    ROLE_OPERATOR,
    ROLE_VIEWER,
    has_permission,
)
from app.models.user import User, UserSession
from app.services.auth_service import validate_session

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user_and_session(
    request: Request,
    bearer_auth: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Tuple[User, UserSession]:
    """Extract and validate the active session from either HTTP-only cookie or Bearer token.
    
    Enforces CSRF protection on state-changing requests when cookie authentication is used.
    """
    token: Optional[str] = None
    is_cookie_auth = False

    # 1. Check Authorization Bearer header first
    if bearer_auth and bearer_auth.credentials:
        token = bearer_auth.credentials
    else:
        # 2. Check session cookie
        token = request.cookies.get("session_id")
        if token:
            is_cookie_auth = True

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. No valid session token provided.",
        )

    # 3. If authenticated via cookie on state-mutating HTTP methods, enforce CSRF protection
    if is_cookie_auth and request.method in ["POST", "PUT", "DELETE", "PATCH"]:
        csrf_cookie = request.cookies.get("csrf_token")
        csrf_header = request.headers.get("X-CSRF-Token")
        if not verify_csrf_token(csrf_header, csrf_cookie):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF validation failed. Missing or mismatched CSRF token.",
            )

    # 4. Validate session against database
    validated = await validate_session(db, token)
    if not validated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired or is invalid. Please log in again.",
        )

    user, session = validated
    return user, session


async def get_current_user(
    auth_data: Tuple[User, UserSession] = Depends(get_current_user_and_session),
) -> User:
    """Dependency yielding the authenticated User."""
    return auth_data[0]


def require_role(*allowed_roles: str) -> Callable:
    """Dependency factory restricting access to specified roles."""
    async def role_checker(user: User = Depends(get_current_user)) -> User:
        if user.role.name not in allowed_roles and user.role.name != ROLE_OWNER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Requires one of the following roles: {', '.join(allowed_roles)}.",
            )
        return user
    return role_checker


def require_permission(resource: str, action: str) -> Callable:
    """Dependency factory restricting access based on granular RBAC permissions."""
    async def permission_checker(user: User = Depends(get_current_user)) -> User:
        perms = [
            {"resource": p.resource, "action": p.action}
            for p in user.role.permissions
        ]
        if not has_permission(user.role.name, resource, action, perms):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Missing permission: '{resource}:{action}'.",
            )
        return user
    return permission_checker
