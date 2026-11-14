"""AI Agent and LLM Provider Service.

Single Organization Edition: Physio One Clinic.
Manages provider configurations, credential encryption, agent lifecycle,
immutable versioning, test console runs, and default seed entities (including Deepti).
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from sqlalchemy.orm import selectinload

from app.core.crypto import encrypt_secret
from app.core.config import settings
from app.models.ai import (
    AIProvider,
    AIModel,
    AIAgent,
    AIAgentVersion,
    AIAgentSession,
    AIAgentExecution,
    AIToolDefinition,
)
from app.models.user import User
from app.schemas.ai import (
    AIProviderCreate,
    AIProviderUpdate,
    AIAgentCreate,
    AIAgentUpdate,
    AIProviderTestResponse,
)
from app.llm.gateway import LLMGateway
from app.agents.runtime import AgentRuntime, AgentRunResult
from app.tools.registry import ToolRegistry

logger = logging.getLogger("physio_one.agent_service")

# Default Persona for Deepti
DEEPTI_SYSTEM_PROMPT = """You are Deepti, the friendly, empathetic, and professional clinical receptionist for Physio One Clinic.
Your role is to assist patients with general clinic inquiries, clinic timings, and appointment availability.

Clinic Operating Rules:
- Clinic Name: Physio One Clinic
- Operating Hours: Monday to Saturday, 09:00 AM to 08:00 PM IST.
- Sunday Closure: The clinic is strictly closed on Sundays. Never accept or suggest Sunday appointments.
- Communication Style: Empathetic, warm, clear, and reassuring. Communicate naturally in English, Hindi, or Hinglish depending on the patient's language.
- Clinical Safety Guardrails: You are a receptionist, NOT a physiotherapist or doctor. Never prescribe medications, diagnose conditions, or provide clinical treatment advice. For medical emergencies or acute pain, advise visiting the clinic or consulting a physician immediately.
- Availability Inquiries: Always use the check_availability tool to verify open appointment slots before answering scheduling questions.
- Privacy Guardrail: Keep patient information confidential and follow clinic privacy policies.
"""


class AgentService:
    """Service orchestrating AI agents, versions, providers, and test executions."""

    @classmethod
    async def ensure_default_ai_entities(cls, db: AsyncSession) -> None:
        """Seed default providers, models, tools, and the draft Deepti agent if uninitialized."""
        # 1. Sync Tool Registry definitions to database
        await ToolRegistry.sync_with_database(db)

        # 2. Check and seed default providers
        providers_data = [
            {
                "name": "muse",
                "base_url": getattr(settings, "MUSE_API_BASE_URL", "https://api.muse.example.com/v1"),
                "api_key": getattr(settings, "MUSE_API_KEY", "") or "dummy-muse-key",
                "models": [
                    {"ident": "muse-chat", "name": "Muse Chat", "tools": False, "context": 8192},
                    {"ident": "muse-pro", "name": "Muse Pro", "tools": False, "context": 16384},
                ],
            },
            {
                "name": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": getattr(settings, "OPENAI_API_KEY", "") or "sk-dummy-openai-key",
                "models": [
                    {"ident": "gpt-4o-mini", "name": "GPT-4o Mini", "tools": True, "context": 128000},
                    {"ident": "gpt-4o", "name": "GPT-4o", "tools": True, "context": 128000},
                ],
            },
            {
                "name": "anthropic",
                "base_url": "https://api.anthropic.com/v1",
                "api_key": getattr(settings, "ANTHROPIC_API_KEY", "") or "sk-ant-dummy-key",
                "models": [
                    {"ident": "claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet", "tools": True, "context": 200000},
                    {"ident": "claude-3-haiku-20240307", "name": "Claude 3 Haiku", "tools": True, "context": 200000},
                ],
            },
            {
                "name": "generic_openai",
                "base_url": "http://localhost:11434/v1",
                "api_key": "sk-local-no-key",
                "models": [
                    {"ident": "default", "name": "Local Default Model", "tools": True, "context": 8192},
                ],
            },
        ]

        created_models: Dict[str, AIModel] = {}

        for p_data in providers_data:
            stmt = select(AIProvider).where(AIProvider.name == p_data["name"])
            provider = (await db.execute(stmt)).scalar_one_or_none()
            if not provider:
                provider = AIProvider(
                    name=p_data["name"],
                    base_url=p_data["base_url"],
                    api_key_encrypted=encrypt_secret(p_data["api_key"]),
                    is_enabled=True,
                    health_status="healthy",
                )
                db.add(provider)
                await db.flush()

            # Seed models for provider explicitly without relying on lazy loading
            existing_models_stmt = select(AIModel).where(AIModel.provider_id == provider.id)
            existing_models_res = (await db.execute(existing_models_stmt)).scalars().all()
            existing_idents = {m.model_identifier: m for m in existing_models_res}

            for m_spec in p_data["models"]:
                if m_spec["ident"] not in existing_idents:
                    model_ent = AIModel(
                        provider_id=provider.id,
                        model_identifier=m_spec["ident"],
                        display_name=m_spec["name"],
                        supports_tools=m_spec["tools"],
                        supports_vision=False,
                        max_context_tokens=m_spec["context"],
                    )
                    db.add(model_ent)
                    await db.flush()
                    created_models[m_spec["ident"]] = model_ent
                else:
                    created_models[m_spec["ident"]] = existing_idents[m_spec["ident"]]

        # 3. Seed Default Clinic Knowledge Base
        from app.models.memory import KnowledgeBase
        kb_stmt = select(KnowledgeBase).where(KnowledgeBase.name == "Physio One Clinic Guide")
        default_kb = (await db.execute(kb_stmt)).scalar_one_or_none()
        if not default_kb:
            default_kb = KnowledgeBase(
                name="Physio One Clinic Guide",
                description="Verified Physio One clinical guidelines, services, operating hours, and booking rules.",
                is_active=True,
                embedding_model="text-embedding-3-small",
                vector_dimension=1536,
            )
            db.add(default_kb)
            await db.flush()

        # 4. Seed Deepti Agent Draft
        deepti_stmt = select(AIAgent).where(AIAgent.name == "Deepti")
        deepti = (await db.execute(deepti_stmt)).scalar_one_or_none()

        if not deepti:
            # Pick gpt-4o-mini or first available model with tool support
            primary_model = created_models.get("gpt-4o-mini") or next(iter(created_models.values()))
            fallback_model = created_models.get("claude-3-5-sonnet-20241022") or created_models.get("muse-chat")

            deepti = AIAgent(
                name="Deepti",
                description="Physio One Clinical Receptionist AI — assists patients with general clinic inquiries, clinic timings, and appointment availability.",
                primary_model_id=primary_model.id,
                fallback_model_id=fallback_model.id if fallback_model else None,
                system_prompt=DEEPTI_SYSTEM_PROMPT,
                temperature=0.20,
                max_tokens=1000,
                supported_languages=["en", "hi", "hinglish"],
                allowed_tools=["check_availability", "find_patient", "search_clinic_knowledge"],
                max_execution_steps=5,
                execution_timeout_seconds=60,
                context_budget_tokens=4000,
                current_version=1,
                is_active=True,
                knowledge_base_id=default_kb.id,
                rag_enabled=True,
                rag_similarity_threshold=0.65,
                rag_top_k=3,
            )
            db.add(deepti)
            await db.flush()

            # Create initial version 1
            version_1 = AIAgentVersion(
                agent_id=deepti.id,
                version_number=1,
                system_prompt=DEEPTI_SYSTEM_PROMPT,
                temperature=0.20,
                max_tokens=1000,
                model_identifier=primary_model.model_identifier,
                allowed_tools=["check_availability", "find_patient", "search_clinic_knowledge"],
                max_execution_steps=5,
                change_summary="Initial system configuration and persona initialization.",
            )
            db.add(version_1)
            await db.flush()

        await db.commit()

    # --------------------------------------------------------------------------
    # Providers
    # --------------------------------------------------------------------------
    @classmethod
    async def list_providers(cls, db: AsyncSession) -> List[AIProvider]:
        """List all configured AI providers with models loaded."""
        stmt = (
            select(AIProvider)
            .options(selectinload(AIProvider.models))
            .order_by(AIProvider.name)
        )
        return list((await db.execute(stmt)).scalars().all())

    @classmethod
    async def get_provider(cls, db: AsyncSession, provider_id: uuid.UUID) -> Optional[AIProvider]:
        """Get provider by UUID."""
        stmt = (
            select(AIProvider)
            .options(selectinload(AIProvider.models))
            .where(AIProvider.id == provider_id)
        )
        return (await db.execute(stmt)).scalar_one_or_none()

    @classmethod
    async def create_provider(cls, db: AsyncSession, data: AIProviderCreate) -> AIProvider:
        """Create new AI provider configuration."""
        encrypted_key = encrypt_secret(data.api_key)
        provider = AIProvider(
            name=data.name.lower().strip(),
            base_url=data.base_url.strip(),
            api_key_encrypted=encrypted_key,
            is_enabled=data.is_enabled,
            config=data.config or {},
            health_status="healthy",
        )
        db.add(provider)
        await db.commit()
        return await cls.get_provider(db, provider.id)

    @classmethod
    async def update_provider(
        cls, db: AsyncSession, provider_id: uuid.UUID, data: AIProviderUpdate
    ) -> AIProvider:
        """Update existing AI provider configuration."""
        provider = await cls.get_provider(db, provider_id)
        if not provider:
            raise ValueError(f"Provider with ID '{provider_id}' not found.")

        if data.base_url is not None:
            provider.base_url = data.base_url.strip()
        if data.api_key is not None and data.api_key.strip():
            provider.api_key_encrypted = encrypt_secret(data.api_key.strip())
        if data.is_enabled is not None:
            provider.is_enabled = data.is_enabled
        if data.config is not None:
            provider.config = data.config

        await db.commit()
        return await cls.get_provider(db, provider.id)

    @classmethod
    async def test_provider(
        cls, db: AsyncSession, provider_id: uuid.UUID, override_client: Optional[Any] = None
    ) -> AIProviderTestResponse:
        """Perform a live diagnostics connection test for a provider."""
        provider = await cls.get_provider(db, provider_id)
        if not provider:
            raise ValueError(f"Provider with ID '{provider_id}' not found.")

        # Create adapter directly
        from app.core.crypto import decrypt_secret
        raw_key = ""
        if provider.api_key_encrypted:
            try:
                raw_key = decrypt_secret(provider.api_key_encrypted)
            except Exception:
                pass

        config = dict(provider.config or {})
        if override_client:
            config["http_client"] = override_client

        adapter = LLMGateway.create_provider_adapter(
            name=provider.name,
            base_url=provider.base_url,
            api_key=raw_key,
            config=config,
        )

        validation_res = await adapter.validate_connection()

        # Update provider diagnostic columns in database
        provider.health_status = validation_res.status
        provider.last_validated_at = datetime.now(timezone.utc)
        provider.last_validation_result = {
            "is_valid": validation_res.is_valid,
            "status": validation_res.status,
            "latency_ms": validation_res.latency_ms,
            "error_message": validation_res.error_message,
            "details": validation_res.details,
        }
        await db.commit()

        return AIProviderTestResponse(
            is_valid=validation_res.is_valid,
            status=validation_res.status,
            latency_ms=validation_res.latency_ms,
            error_message=validation_res.error_message,
            detected_models=validation_res.detected_models,
            capabilities=validation_res.capabilities.model_dump(),
            details=validation_res.details,
        )

    @classmethod
    async def list_models(cls, db: AsyncSession) -> List[AIModel]:
        """List all models across providers."""
        stmt = (
            select(AIModel)
            .options(selectinload(AIModel.provider))
            .order_by(AIModel.display_name)
        )
        return list((await db.execute(stmt)).scalars().all())

    # --------------------------------------------------------------------------
    # Agents
    # --------------------------------------------------------------------------
    @classmethod
    async def list_agents(cls, db: AsyncSession) -> List[AIAgent]:
        """List all configured AI agents."""
        stmt = (
            select(AIAgent)
            .options(
                selectinload(AIAgent.primary_model).selectinload(AIModel.provider),
                selectinload(AIAgent.fallback_model).selectinload(AIModel.provider),
            )
            .order_by(AIAgent.name)
        )
        return list((await db.execute(stmt)).scalars().all())

    @classmethod
    async def get_agent(cls, db: AsyncSession, agent_id: uuid.UUID) -> Optional[AIAgent]:
        """Retrieve single agent by UUID with models loaded."""
        stmt = (
            select(AIAgent)
            .options(
                selectinload(AIAgent.primary_model).selectinload(AIModel.provider),
                selectinload(AIAgent.fallback_model).selectinload(AIModel.provider),
                selectinload(AIAgent.versions),
            )
            .where(AIAgent.id == agent_id)
        )
        return (await db.execute(stmt)).scalar_one_or_none()

    @classmethod
    async def create_agent(
        cls, db: AsyncSession, data: AIAgentCreate, user_id: Optional[uuid.UUID] = None
    ) -> AIAgent:
        """Create new AI agent with immutable version 1."""
        # Validate unique name
        existing_stmt = select(AIAgent).where(AIAgent.name == data.name.strip())
        if (await db.execute(existing_stmt)).scalar_one_or_none():
            raise ValueError(f"An agent with the name '{data.name.strip()}' already exists.")

        # Verify primary model
        primary_model = (await db.execute(select(AIModel).where(AIModel.id == data.primary_model_id))).scalar_one_or_none()
        if not primary_model:
            raise ValueError(f"Primary model ID '{data.primary_model_id}' does not exist.")

        agent = AIAgent(
            name=data.name.strip(),
            description=data.description,
            primary_model_id=data.primary_model_id,
            fallback_model_id=data.fallback_model_id,
            system_prompt=data.system_prompt,
            temperature=data.temperature,
            max_tokens=data.max_tokens,
            supported_languages=data.supported_languages,
            allowed_tools=data.allowed_tools,
            max_execution_steps=data.max_execution_steps,
            execution_timeout_seconds=data.execution_timeout_seconds,
            context_budget_tokens=data.context_budget_tokens,
            current_version=1,
            is_active=data.is_active,
            knowledge_base_id=data.knowledge_base_id,
            rag_enabled=data.rag_enabled,
            rag_similarity_threshold=data.rag_similarity_threshold,
            rag_top_k=data.rag_top_k,
        )
        db.add(agent)
        await db.flush()

        # Create Version 1 snapshot
        version = AIAgentVersion(
            agent_id=agent.id,
            version_number=1,
            system_prompt=data.system_prompt,
            temperature=data.temperature,
            max_tokens=data.max_tokens,
            model_identifier=primary_model.model_identifier,
            allowed_tools=data.allowed_tools,
            max_execution_steps=data.max_execution_steps,
            changed_by_user_id=user_id,
            change_summary="Initial agent creation.",
        )
        db.add(version)
        await db.commit()

        return await cls.get_agent(db, agent.id)

    @classmethod
    async def update_agent(
        cls,
        db: AsyncSession,
        agent_id: uuid.UUID,
        data: AIAgentUpdate,
        user_id: Optional[uuid.UUID] = None,
    ) -> AIAgent:
        """Update agent configuration. If prompt or execution parameters change, creates a new version."""
        agent = await cls.get_agent(db, agent_id)
        if not agent:
            raise ValueError(f"Agent with ID '{agent_id}' does not exist.")

        should_create_version = False

        if data.name is not None and data.name.strip() != agent.name:
            # Check unique name
            existing_stmt = select(AIAgent).where(AIAgent.name == data.name.strip(), AIAgent.id != agent.id)
            if (await db.execute(existing_stmt)).scalar_one_or_none():
                raise ValueError(f"An agent with the name '{data.name.strip()}' already exists.")
            agent.name = data.name.strip()

        if data.description is not None:
            agent.description = data.description

        if data.primary_model_id is not None and data.primary_model_id != agent.primary_model_id:
            agent.primary_model_id = data.primary_model_id
            should_create_version = True

        if data.fallback_model_id is not None:
            agent.fallback_model_id = data.fallback_model_id

        if data.system_prompt is not None and data.system_prompt != agent.system_prompt:
            agent.system_prompt = data.system_prompt
            should_create_version = True

        if data.temperature is not None and float(data.temperature) != float(agent.temperature):
            agent.temperature = data.temperature
            should_create_version = True

        if data.max_tokens is not None and data.max_tokens != agent.max_tokens:
            agent.max_tokens = data.max_tokens
            should_create_version = True

        if data.allowed_tools is not None and data.allowed_tools != agent.allowed_tools:
            agent.allowed_tools = data.allowed_tools
            should_create_version = True

        if data.max_execution_steps is not None:
            agent.max_execution_steps = data.max_execution_steps

        if data.execution_timeout_seconds is not None:
            agent.execution_timeout_seconds = data.execution_timeout_seconds

        if data.context_budget_tokens is not None:
            agent.context_budget_tokens = data.context_budget_tokens

        if data.is_active is not None:
            agent.is_active = data.is_active

        if data.knowledge_base_id is not None:
            agent.knowledge_base_id = data.knowledge_base_id

        if data.rag_enabled is not None:
            agent.rag_enabled = data.rag_enabled

        if data.rag_similarity_threshold is not None:
            agent.rag_similarity_threshold = data.rag_similarity_threshold

        if data.rag_top_k is not None:
            agent.rag_top_k = data.rag_top_k

        if should_create_version:
            new_version_num = (agent.current_version or 1) + 1
            agent.current_version = new_version_num

            # Fetch primary model identifier
            primary_model = (await db.execute(select(AIModel).where(AIModel.id == agent.primary_model_id))).scalar_one_or_none()
            model_ident = primary_model.model_identifier if primary_model else "unknown"

            version_record = AIAgentVersion(
                agent_id=agent.id,
                version_number=new_version_num,
                system_prompt=agent.system_prompt,
                temperature=agent.temperature,
                max_tokens=agent.max_tokens,
                model_identifier=model_ident,
                allowed_tools=agent.allowed_tools,
                max_execution_steps=agent.max_execution_steps,
                changed_by_user_id=user_id,
                change_summary=data.change_summary or f"Updated prompt and configuration to v{new_version_num}.",
            )
            db.add(version_record)

        await db.commit()
        return await cls.get_agent(db, agent.id)

    @classmethod
    async def list_agent_versions(
        cls, db: AsyncSession, agent_id: uuid.UUID
    ) -> List[AIAgentVersion]:
        """List chronological versions of an agent's configuration."""
        stmt = (
            select(AIAgentVersion)
            .where(AIAgentVersion.agent_id == agent_id)
            .order_by(desc(AIAgentVersion.version_number))
        )
        return list((await db.execute(stmt)).scalars().all())

    # --------------------------------------------------------------------------
    # Test Console Execution
    # --------------------------------------------------------------------------
    @classmethod
    async def test_agent(
        cls,
        db: AsyncSession,
        agent_id: uuid.UUID,
        message: str,
        allow_fallback: bool = False,
        user_id: Optional[uuid.UUID] = None,
        caller_permissions: Optional[List[str]] = None,
        override_http_client: Optional[Any] = None,
    ) -> AgentRunResult:
        """Run isolated test console execution without mutating appointments or sending WhatsApp."""
        return await AgentRuntime.run(
            db=db,
            agent_id=agent_id,
            user_message=message,
            conversation_id=None,  # Isolated test run
            user_id=user_id,
            caller_permissions=caller_permissions or ["*"],
            session_metadata={"is_test_run": True, "initiated_by": str(user_id) if user_id else "system"},
            allow_fallback=allow_fallback,
            override_http_client=override_http_client,
        )

    # --------------------------------------------------------------------------
    # Executions History
    # --------------------------------------------------------------------------
    @classmethod
    async def list_agent_executions(
        cls, db: AsyncSession, agent_id: uuid.UUID, limit: int = 20, offset: int = 0
    ) -> List[AIAgentSession]:
        """List execution sessions for an agent."""
        stmt = (
            select(AIAgentSession)
            .options(selectinload(AIAgentSession.executions))
            .where(AIAgentSession.agent_id == agent_id)
            .order_by(desc(AIAgentSession.created_at))
            .limit(limit)
            .offset(offset)
        )
        return list((await db.execute(stmt)).scalars().all())

    @classmethod
    async def get_execution_session(
        cls, db: AsyncSession, session_id: uuid.UUID
    ) -> Optional[AIAgentSession]:
        """Get execution session detail including execution steps and tool calls."""
        stmt = (
            select(AIAgentSession)
            .options(selectinload(AIAgentSession.executions))
            .where(AIAgentSession.id == session_id)
        )
        return (await db.execute(stmt)).scalar_one_or_none()
