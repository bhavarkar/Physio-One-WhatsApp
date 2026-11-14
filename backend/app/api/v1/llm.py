"""LLM Providers and Models API Endpoints.

Single Organization Edition: Physio One Clinic.
RBAC:
- List/Detail/Test providers & models: require_role(ROLE_OWNER, ROLE_ADMIN)
- Create/Update provider credentials: require_role(ROLE_OWNER, ROLE_ADMIN)
"""
import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_role
from app.core.rbac import ROLE_OWNER, ROLE_ADMIN
from app.models.user import User
from app.models.ai import AIProvider, AIModel
from app.schemas.ai import (
    AIProviderResponse,
    AIProviderCreate,
    AIProviderUpdate,
    AIProviderTestResponse,
    AIModelResponse,
)
from app.services.agent_service import AgentService
from app.core.crypto import decrypt_secret

router = APIRouter(prefix="/llm", tags=["LLM Gateway"])


def serialize_provider(p: AIProvider) -> AIProviderResponse:
    """Format AIProvider model with masked credentials and nested models."""
    has_key = bool(p.api_key_encrypted)
    masked = "Not configured"
    if has_key:
        try:
            raw = decrypt_secret(p.api_key_encrypted)
            if len(raw) <= 8:
                masked = "****"
            else:
                masked = f"{raw[:4]}...{raw[-4:]}"
        except Exception:
            masked = "Encrypted (Decryption Failed)"

    models = [
        AIModelResponse(
            id=m.id,
            provider_id=m.provider_id,
            provider_name=p.name,
            model_identifier=m.model_identifier,
            display_name=m.display_name,
            supports_tools=m.supports_tools,
            supports_vision=m.supports_vision,
            max_context_tokens=m.max_context_tokens,
            created_at=m.created_at,
        )
        for m in (p.models or [])
    ]

    return AIProviderResponse(
        id=p.id,
        name=p.name,
        base_url=p.base_url,
        has_api_key=has_key,
        masked_api_key=masked,
        is_enabled=p.is_enabled,
        config=p.config,
        health_status=p.health_status,
        last_validated_at=p.last_validated_at,
        last_validation_result=p.last_validation_result,
        models=models,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


@router.get("/providers", response_model=List[AIProviderResponse])
async def list_providers(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN)),
):
    """List all configured LLM providers with masked credentials."""
    providers = await AgentService.list_providers(db)
    return [serialize_provider(p) for p in providers]


@router.post("/providers", response_model=AIProviderResponse, status_code=status.HTTP_201_CREATED)
async def create_provider(
    payload: AIProviderCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN)),
):
    """Create a new LLM provider configuration with encrypted credentials."""
    try:
        provider = await AgentService.create_provider(db, payload)
        return serialize_provider(provider)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/providers/{provider_id}", response_model=AIProviderResponse)
async def get_provider(
    provider_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN)),
):
    """Get single provider configuration."""
    provider = await AgentService.get_provider(db, provider_id)
    if not provider:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found.")
    return serialize_provider(provider)


@router.patch("/providers/{provider_id}", response_model=AIProviderResponse)
async def update_provider(
    provider_id: uuid.UUID,
    payload: AIProviderUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN)),
):
    """Update provider settings, base URL, or encrypted credentials."""
    try:
        provider = await AgentService.update_provider(db, provider_id, payload)
        return serialize_provider(provider)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/providers/{provider_id}/test", response_model=AIProviderTestResponse)
async def test_provider_connection(
    provider_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN)),
):
    """Run connection and credential validation test against provider."""
    try:
        return await AgentService.test_provider(db, provider_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/models", response_model=List[AIModelResponse])
async def list_models(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN)),
):
    """List all available models across providers."""
    models = await AgentService.list_models(db)
    return [
        AIModelResponse(
            id=m.id,
            provider_id=m.provider_id,
            provider_name=m.provider.name if m.provider else "unknown",
            model_identifier=m.model_identifier,
            display_name=m.display_name,
            supports_tools=m.supports_tools,
            supports_vision=m.supports_vision,
            max_context_tokens=m.max_context_tokens,
            created_at=m.created_at,
        )
        for m in models
    ]
