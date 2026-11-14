"""AI Agents, Versioning, and Isolated Test Console API Endpoints.

Single Organization Edition: Physio One Clinic.
RBAC:
- List/Detail agents: require_role(Owner, Admin, Operator, Viewer)
- Create/Update agents & versions: require_role(Owner, Admin)
- Test executions & Execution history: require_role(Owner, Admin, Operator)
"""
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_role, get_current_user
from app.core.rbac import ROLE_OWNER, ROLE_ADMIN, ROLE_OPERATOR, ROLE_VIEWER
from app.models.user import User
from app.models.ai import AIAgent, AIAgentVersion, AIAgentSession
from app.schemas.ai import (
    AIAgentResponse,
    AIAgentCreate,
    AIAgentUpdate,
    AIAgentVersionResponse,
    AIAgentTestRequest,
    AIAgentTestResponse,
    AgentExecutionSessionResponse,
    AgentExecutionStepResponse,
)
from app.services.agent_service import AgentService

router = APIRouter(prefix="/agents", tags=["AI Agents"])


def serialize_agent(a: AIAgent) -> AIAgentResponse:
    """Format AIAgent entity to response model."""
    primary_ident = a.primary_model.model_identifier if a.primary_model else "unknown"
    primary_prov = a.primary_model.provider.name if a.primary_model and a.primary_model.provider else "unknown"
    fallback_ident = a.fallback_model.model_identifier if a.fallback_model else None
    fallback_prov = a.fallback_model.provider.name if a.fallback_model and a.fallback_model.provider else None

    return AIAgentResponse(
        id=a.id,
        name=a.name,
        description=a.description,
        primary_model_id=a.primary_model_id,
        primary_model_identifier=primary_ident,
        primary_provider_name=primary_prov,
        fallback_model_id=a.fallback_model_id,
        fallback_model_identifier=fallback_ident,
        fallback_provider_name=fallback_prov,
        system_prompt=a.system_prompt,
        temperature=float(a.temperature or 0.2),
        max_tokens=a.max_tokens or 1000,
        supported_languages=a.supported_languages or ["en", "hi", "hinglish"],
        allowed_tools=a.allowed_tools or [],
        max_execution_steps=a.max_execution_steps or 5,
        execution_timeout_seconds=a.execution_timeout_seconds or 60,
        context_budget_tokens=a.context_budget_tokens or 4000,
        current_version=a.current_version or 1,
        is_active=a.is_active,
        knowledge_base_id=a.knowledge_base_id,
        rag_enabled=a.rag_enabled or False,
        rag_similarity_threshold=float(a.rag_similarity_threshold or 0.70),
        rag_top_k=a.rag_top_k or 3,
        created_at=a.created_at,
        updated_at=a.updated_at,
    )


def serialize_session(s: AIAgentSession) -> AgentExecutionSessionResponse:
    """Format AIAgentSession and its execution steps."""
    duration_ms = None
    if s.started_at and s.completed_at:
        duration_ms = int((s.completed_at - s.started_at).total_seconds() * 1000)

    exec_steps = [
        AgentExecutionStepResponse(
            step_number=e.step_number,
            status=e.status,
            response_text=e.response_text,
            tool_calls=e.tool_calls,
            input_tokens=e.input_tokens,
            output_tokens=e.output_tokens,
            duration_ms=e.duration_ms,
            error_message=e.error_message,
            created_at=e.created_at,
        )
        for e in sorted(s.executions or [], key=lambda x: x.step_number)
    ]

    return AgentExecutionSessionResponse(
        id=s.id,
        agent_id=s.agent_id,
        agent_version_id=s.agent_version_id,
        conversation_id=s.conversation_id,
        status=s.status,
        total_input_tokens=s.total_input_tokens,
        total_output_tokens=s.total_output_tokens,
        total_execution_steps=s.total_execution_steps,
        error_message=s.error_message,
        started_at=s.started_at,
        completed_at=s.completed_at,
        duration_ms=duration_ms,
        created_at=s.created_at,
        executions=exec_steps,
    )


@router.get("", response_model=List[AIAgentResponse])
async def list_agents(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN, ROLE_OPERATOR, ROLE_VIEWER)),
):
    """List configured AI agents."""
    agents = await AgentService.list_agents(db)
    return [serialize_agent(a) for a in agents]


@router.post("", response_model=AIAgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    payload: AIAgentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN)),
):
    """Create new AI agent with immutable version snapshot."""
    try:
        agent = await AgentService.create_agent(db, payload, user_id=user.id)
        return serialize_agent(agent)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/executions/{execution_id}", response_model=AgentExecutionSessionResponse)
async def get_execution_session(
    execution_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN, ROLE_OPERATOR)),
):
    """Get single execution session and its step logs."""
    session = await AgentService.get_execution_session(db, execution_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution session not found.")
    return serialize_session(session)


@router.get("/{agent_id}", response_model=AIAgentResponse)
async def get_agent(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN, ROLE_OPERATOR, ROLE_VIEWER)),
):
    """Get agent configuration details."""
    agent = await AgentService.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found.")
    return serialize_agent(agent)


@router.patch("/{agent_id}", response_model=AIAgentResponse)
async def update_agent(
    agent_id: uuid.UUID,
    payload: AIAgentUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN)),
):
    """Update agent prompt or settings; creates version snapshot when modified."""
    try:
        agent = await AgentService.update_agent(db, agent_id, payload, user_id=user.id)
        return serialize_agent(agent)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{agent_id}/versions", response_model=List[AIAgentVersionResponse])
async def list_agent_versions(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN, ROLE_OPERATOR)),
):
    """List historical immutable versions for an agent."""
    versions = await AgentService.list_agent_versions(db, agent_id)
    return [
        AIAgentVersionResponse(
            id=v.id,
            agent_id=v.agent_id,
            version_number=v.version_number,
            system_prompt=v.system_prompt,
            temperature=float(v.temperature),
            max_tokens=v.max_tokens,
            model_identifier=v.model_identifier,
            allowed_tools=v.allowed_tools,
            max_execution_steps=v.max_execution_steps,
            changed_by_user_id=v.changed_by_user_id,
            change_summary=v.change_summary,
            created_at=v.created_at,
        )
        for v in versions
    ]


@router.post("/{agent_id}/test", response_model=AIAgentTestResponse)
async def test_agent_console(
    agent_id: uuid.UUID,
    payload: AIAgentTestRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN, ROLE_OPERATOR)),
):
    """Execute an isolated test prompt in the test console.
    
    Safe execution:
    - Never mutates appointments.
    - Never sends real WhatsApp messages.
    - Runs in sandboxed runtime with tool dispatcher.
    """
    try:
        user_perms = [f"{p.resource}:{p.action}" for p in user.role.permissions] if user.role else ["*"]
        result = await AgentService.test_agent(
            db=db,
            agent_id=agent_id,
            message=payload.message,
            allow_fallback=payload.allow_fallback,
            user_id=user.id,
            caller_permissions=user_perms,
        )
        return AIAgentTestResponse(
            session_id=result.session_id,
            agent_id=result.agent_id,
            agent_name=result.agent_name,
            status=result.status,
            response_text=result.response_text or "",
            steps=result.steps,
            tool_calls=result.tool_calls,
            rag_sources=result.rag_sources,
            total_input_tokens=result.total_input_tokens,
            total_output_tokens=result.total_output_tokens,
            total_tokens=result.total_tokens,
            duration_ms=result.duration_ms,
            model=result.model,
            provider=result.provider,
            error_message=result.error_message,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{agent_id}/executions", response_model=List[AgentExecutionSessionResponse])
async def list_agent_executions(
    agent_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN, ROLE_OPERATOR)),
):
    """List execution history sessions for an agent."""
    sessions = await AgentService.list_agent_executions(db, agent_id, limit=limit, offset=offset)
    return [serialize_session(s) for s in sessions]
