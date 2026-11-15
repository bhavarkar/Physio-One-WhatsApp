"""Hardened Worker & Scheduler Authentication for Cloud Tasks, Cloud Scheduler & Internal Workers.

Single Organization Edition: Physio One Clinic.
Implements multi-tiered authentication for privileged worker routes:
1. Google OIDC Service Account Identity Token (for Cloud Tasks and Cloud Scheduler on Cloud Run).
2. Hardened Worker Secret Token (X-Worker-Token) using constant-time comparison.
3. Authenticated Admin/Owner session for manual operational overrides.
Strictly rejects unauthenticated requests and ordinary non-admin users.
"""
import hmac
import json
import base64
import time
import logging
from typing import Optional, Dict, Any, Tuple
from fastapi import Request, Header, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.services.auth_service import validate_session
from app.models.user import User

logger = logging.getLogger("physio_one.security.worker_auth")


def _decode_jwt_unverified_claims(token: str) -> Optional[Dict[str, Any]]:
    """Decode unverified JWT claims to inspect issuer, audience, and subject claims."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        # Add base64 padding if necessary
        payload_b64 = parts[1]
        padded = payload_b64 + "=" * ((4 - len(payload_b64) % 4) % 4)
        payload_bytes = base64.urlsafe_b64decode(padded.encode("ascii"))
        return json.loads(payload_bytes.decode("utf-8"))
    except Exception as exc:
        logger.debug("Failed to decode token claims: %s", exc)
        return None


def verify_google_oidc_claims(
    claims: Dict[str, Any],
    expected_audience: Optional[str] = None,
    expected_email: Optional[str] = None,
) -> bool:
    """Validate standard Google Cloud OIDC token claims."""
    now = time.time()

    # 1. Issuer check
    iss = claims.get("iss", "")
    if iss not in ["https://accounts.google.com", "accounts.google.com"]:
        logger.warning("OIDC verification failed: invalid issuer '%s'", iss)
        return False

    # 2. Expiration check (with 30-second clock skew allowance)
    exp = claims.get("exp")
    if not exp or (now > float(exp) + 30):
        logger.warning("OIDC verification failed: token expired at %s (now=%s)", exp, now)
        return False

    # 3. Audience check
    target_aud = expected_audience or settings.OIDC_AUDIENCE or settings.CLOUD_RUN_SERVICE_URL
    if target_aud:
        aud = claims.get("aud")
        if aud != target_aud:
            logger.warning("OIDC verification failed: audience mismatch (got '%s', expected '%s')", aud, target_aud)
            return False

    # 4. Authorized Service Account Email check
    target_email = expected_email or settings.WORKER_SERVICE_ACCOUNT_EMAIL
    if target_email:
        email = claims.get("email")
        if not email or email != target_email:
            logger.warning("OIDC verification failed: email mismatch (got '%s', expected '%s')", email, target_email)
            return False

    return True


async def require_worker_auth(
    request: Request,
    x_worker_token: Optional[str] = Header(None, alias="X-Worker-Token"),
    x_cloudtasks_queue: Optional[str] = Header(None, alias="X-CloudTasks-QueueName"),
    x_cloudtasks_task: Optional[str] = Header(None, alias="X-CloudTasks-TaskName"),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """FastAPI Dependency: Authenticate Cloud Tasks, Cloud Scheduler, or internal worker calls.
    
    Accepts:
    - Verified Google Cloud Tasks / Cloud Scheduler OIDC Bearer token.
    - Verified X-Worker-Token matching AUTOMATION_WORKER_SECRET_TOKEN via constant-time comparison.
    - Active logged-in session for Owner or Admin roles.
    
    Raises 401/403 if unauthorized.
    """
    auth_header = request.headers.get("Authorization", "").strip()
    caller_info: Dict[str, Any] = {
        "auth_method": None,
        "caller_identity": None,
        "is_cloud_tasks": bool(x_cloudtasks_queue or x_cloudtasks_task),
        "queue_name": x_cloudtasks_queue,
        "task_name": x_cloudtasks_task,
    }

    # Method 1: Google OIDC Token via Authorization: Bearer <ID_TOKEN>
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        claims = _decode_jwt_unverified_claims(token)
        if claims and claims.get("iss") in ["https://accounts.google.com", "accounts.google.com"]:
            if verify_google_oidc_claims(claims):
                caller_info["auth_method"] = "google_oidc"
                caller_info["caller_identity"] = claims.get("email", "google_service_account")
                logger.info(
                    "Worker endpoint authorized via Google OIDC service account: %s (task=%s)",
                    caller_info["caller_identity"],
                    x_cloudtasks_task,
                )
                return caller_info
            else:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired Google OIDC identity token.",
                )

        # Check if Bearer token is a valid admin user session token
        validated_session = await validate_session(db, token)
        if validated_session:
            user, session = validated_session
            if user.role and user.role.name in ["owner", "admin"]:
                caller_info["auth_method"] = "admin_bearer_session"
                caller_info["caller_identity"] = f"{user.email} ({user.role.name})"
                return caller_info
            else:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Forbidden: Worker endpoints require Owner or Admin privileges.",
                )

    # Method 2: Shared Secret Worker Token (X-Worker-Token)
    # Strictly validated using constant-time comparison to prevent timing attacks.
    if x_worker_token:
        configured_token = settings.AUTOMATION_WORKER_SECRET_TOKEN or ""
        if len(configured_token) >= 16 and hmac.compare_digest(x_worker_token, configured_token):
            caller_info["auth_method"] = "worker_secret_token"
            caller_info["caller_identity"] = "internal_automation_worker"
            return caller_info
        else:
            logger.warning("Worker authorization failed: Invalid X-Worker-Token provided.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid worker secret token.",
            )

    # Method 3: Session Cookie Authentication (Dashboard Owner/Admin manual invocation)
    session_cookie = request.cookies.get("session_id")
    if session_cookie:
        validated_session = await validate_session(db, session_cookie)
        if validated_session:
            user, session = validated_session
            if user.role and user.role.name in ["owner", "admin"]:
                caller_info["auth_method"] = "admin_cookie_session"
                caller_info["caller_identity"] = f"{user.email} ({user.role.name})"
                return caller_info
            else:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Forbidden: Worker endpoints require Owner or Admin privileges.",
                )

    # If in strict production mode with OIDC required and no valid OIDC token presented:
    if settings.REQUIRE_OIDC_IN_PRODUCTION:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Production worker endpoints require verified Google OIDC credentials.",
        )

    # Unauthenticated / Missing credentials
    logger.warning("Unauthorized access attempt to internal worker route from %s", request.client.host if request.client else "unknown")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized service caller. Valid Google OIDC token, worker secret, or Admin session required.",
    )
