"""Authentication and Session Management API Routes

Single Organization Edition: Physio One Clinic.
"""
from typing import List, Tuple
import uuid
from fastapi import APIRouter, Depends, Request, Response, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.api.deps import get_current_user_and_session, get_current_user
from app.schemas.auth import (
    SetupStatusResponse,
    SetupRequest,
    LoginRequest,
    PasswordChangeRequest,
    SessionResponse,
)
from app.schemas.user import UserResponse
from app.models.user import User, UserSession
from app.services.auth_service import (
    get_setup_status,
    setup_initial_owner,
    authenticate_user,
    revoke_session_by_id,
    revoke_all_sessions,
    change_password,
    log_audit_event,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


def set_auth_cookies(response: Response, session_token: str, csrf_token: str):
    """Set secure HTTP-only session cookie and JavaScript-accessible CSRF cookie."""
    is_prod = (settings.ENVIRONMENT in ("production", "staging") or settings.COOKIE_SECURE)
    
    response.set_cookie(
        key="session_id",
        value=session_token,
        httponly=True,
        secure=is_prod,
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/",
    )
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,  # Accessible to frontend for X-CSRF-Token header
        secure=is_prod,
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/",
    )


def clear_auth_cookies(response: Response):
    """Delete session and CSRF cookies."""
    response.delete_cookie("session_id", path="/")
    response.delete_cookie("csrf_token", path="/")


@router.get("/setup-status", response_model=SetupStatusResponse)
async def check_setup_status(db: AsyncSession = Depends(get_db)):
    """Check if the initial Owner account has been created."""
    is_init, count = await get_setup_status(db)
    return SetupStatusResponse(is_initialized=is_init, owner_count=count)


@router.post("/setup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def initialize_system(
    payload: SetupRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Controlled initial setup process: creates the first Owner account.
    
    Allowed only once when no active Owners exist.
    """
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    owner, session_token, csrf_token = await setup_initial_owner(
        db,
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        ip_address=client_ip,
        user_agent=user_agent,
    )

    set_auth_cookies(response, session_token, csrf_token)
    return owner


@router.post("/login", response_model=UserResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate staff user, issue session cookies, and return user profile."""
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    user, session_token, csrf_token = await authenticate_user(
        db,
        email=payload.email,
        password=payload.password,
        ip_address=client_ip,
        user_agent=user_agent,
    )

    set_auth_cookies(response, session_token, csrf_token)
    return user


@router.post("/logout")
async def logout(
    response: Response,
    auth_data: Tuple[User, UserSession] = Depends(get_current_user_and_session),
    db: AsyncSession = Depends(get_db),
):
    """Invalidate current active session and clear browser cookies."""
    user, session = auth_data
    session.is_revoked = True
    await log_audit_event(
        db,
        action="LOGOUT",
        resource_type="auth",
        resource_id=str(session.id),
        user_id=user.id,
    )
    await db.commit()
    clear_auth_cookies(response)
    return {"message": "Successfully logged out."}


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    user: User = Depends(get_current_user),
):
    """Retrieve profile of the currently authenticated staff member."""
    return user


@router.get("/sessions", response_model=List[SessionResponse])
async def list_my_active_sessions(
    auth_data: Tuple[User, UserSession] = Depends(get_current_user_and_session),
    db: AsyncSession = Depends(get_db),
):
    """List all active sessions for the authenticated user."""
    user, current_session = auth_data

    stmt = select(UserSession).where(
        UserSession.user_id == user.id,
        UserSession.is_revoked == False,
    ).order_by(UserSession.created_at.desc())
    
    sessions = (await db.execute(stmt)).scalars().all()

    result = []
    for s in sessions:
        resp = SessionResponse.model_validate(s)
        resp.is_current = (s.id == current_session.id)
        result.append(resp)

    return result


@router.post("/sessions/{session_id}/revoke")
async def revoke_session(
    session_id: uuid.UUID,
    auth_data: Tuple[User, UserSession] = Depends(get_current_user_and_session),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a specific session."""
    user, _ = auth_data
    revoked = await revoke_session_by_id(db, session_id, requesting_user=user)
    if not revoked:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    return {"message": "Session successfully revoked."}


@router.post("/sessions/revoke-all")
async def revoke_all_other_sessions(
    auth_data: Tuple[User, UserSession] = Depends(get_current_user_and_session),
    db: AsyncSession = Depends(get_db),
):
    """Revoke all sessions belonging to the current user except the active one."""
    user, current_session = auth_data
    count = await revoke_all_sessions(
        db,
        user_id=user.id,
        except_session_id=current_session.id,
        revoked_by_user_id=user.id,
    )
    return {"message": f"Successfully revoked {count} other session(s)."}


@router.post("/change-password")
async def update_my_password(
    payload: PasswordChangeRequest,
    request: Request,
    auth_data: Tuple[User, UserSession] = Depends(get_current_user_and_session),
    db: AsyncSession = Depends(get_db),
):
    """Change current user's password with verification and optional revocation of other sessions."""
    user, current_session = auth_data
    client_ip = request.client.host if request.client else None

    await change_password(
        db,
        user=user,
        current_password=payload.current_password,
        new_password=payload.new_password,
        revoke_other_sessions=payload.revoke_other_sessions,
        current_session_id=current_session.id,
        ip_address=client_ip,
    )
    return {"message": "Password successfully updated."}

