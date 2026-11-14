"""Unified LLM Gateway with Provider Resolution, Resilient Fallback, and Usage Tracking.

Single Organization Edition: Physio One Clinic.
Acts as the central provider-agnostic bridge between AI agent runtimes and LLM APIs.
"""
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
import uuid
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.crypto import decrypt_secret
from app.models.ai import AIProvider, AIModel, LLMUsageLog
from app.llm.base import BaseLLMProvider
from app.llm.providers.muse import MuseProvider
from app.llm.providers.openai import OpenAIProvider
from app.llm.providers.anthropic import AnthropicProvider
from app.llm.providers.generic_openai import GenericOpenAIProvider
from app.llm.schemas import (
    ChatMessage,
    LLMOptions,
    LLMResponse,
    ToolDefinition,
)
from app.llm.errors import (
    LLMError,
    LLMConfigurationError,
    LLMUnsupportedCapabilityError,
)

logger = logging.getLogger("physio_one.llm.gateway")


class LLMGateway:
    """Provider-agnostic LLM Gateway orchestrating requests, fallbacks, and telemetry."""

    @staticmethod
    def create_provider_adapter(
        name: str,
        base_url: str,
        api_key: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> BaseLLMProvider:
        """Instantiate appropriate provider adapter based on provider name."""
        norm_name = name.lower().strip()
        if norm_name == "muse":
            return MuseProvider(base_url=base_url, api_key=api_key, config=config)
        elif norm_name == "openai":
            return OpenAIProvider(base_url=base_url, api_key=api_key, config=config)
        elif norm_name == "anthropic":
            return AnthropicProvider(base_url=base_url, api_key=api_key, config=config)
        elif norm_name in ["generic_openai", "custom", "local"]:
            return GenericOpenAIProvider(base_url=base_url, api_key=api_key, config=config)
        else:
            raise LLMConfigurationError(
                f"Unsupported LLM provider: '{name}'. Supported providers: muse, openai, anthropic, generic_openai.",
                provider=name,
            )

    @classmethod
    async def resolve_adapter_for_model(
        cls,
        db: AsyncSession,
        model_id: uuid.UUID,
        override_http_client: Optional[Any] = None,
    ) -> Tuple[BaseLLMProvider, str]:
        """Resolve AIModel and decrypt parent AIProvider credentials to build an active adapter."""
        stmt = (
            select(AIModel)
            .options(selectinload(AIModel.provider))
            .where(AIModel.id == model_id)
        )
        model_entity = (await db.execute(stmt)).scalar_one_or_none()
        if not model_entity:
            raise LLMConfigurationError(f"Model ID '{model_id}' does not exist.")

        provider_entity = model_entity.provider
        if not provider_entity or not provider_entity.is_enabled:
            raise LLMConfigurationError(
                f"Provider '{provider_entity.name if provider_entity else 'unknown'}' is disabled or not found."
            )

        # Decrypt API key
        raw_key = ""
        if provider_entity.api_key_encrypted:
            try:
                raw_key = decrypt_secret(provider_entity.api_key_encrypted)
            except Exception as e:
                logger.error(f"Failed to decrypt credentials for provider '{provider_entity.name}': {e}")
                raise LLMConfigurationError(
                    f"Credential decryption failed for provider '{provider_entity.name}'."
                )

        config = dict(provider_entity.config or {})
        if override_http_client:
            config["http_client"] = override_http_client

        adapter = cls.create_provider_adapter(
            name=provider_entity.name,
            base_url=provider_entity.base_url,
            api_key=raw_key,
            config=config,
        )
        return adapter, model_entity.model_identifier

    @classmethod
    async def execute(
        cls,
        primary_provider: BaseLLMProvider,
        primary_model: str,
        messages: List[ChatMessage],
        options: Optional[LLMOptions] = None,
        tools: Optional[List[ToolDefinition]] = None,
        fallback_provider: Optional[BaseLLMProvider] = None,
        fallback_model: Optional[str] = None,
        allow_fallback: bool = False,
        has_mutating_side_effects: bool = False,
        session_id: Optional[uuid.UUID] = None,
        agent_id: Optional[uuid.UUID] = None,
        db: Optional[AsyncSession] = None,
    ) -> LLMResponse:
        """Execute chat completion with optional rate-limit fallback and token accounting.
        
        Fallback Policy:
        - Disabled by default.
        - Applies only to eligible retryable errors (rate limits, timeouts, upstream outages).
        - Strictly rejected if mutating side effects have occurred.
        - Records which provider and model actually executed the request.
        """
        options = options or LLMOptions()
        request_ts = datetime.now(timezone.utc)
        response_ts: Optional[datetime] = None

        # Verify tool capabilities upfront
        if tools and len(tools) > 0 and not primary_provider.capabilities.supports_tools:
            if not (allow_fallback and fallback_provider and fallback_provider.capabilities.supports_tools):
                raise LLMUnsupportedCapabilityError(
                    f"Provider '{primary_provider.name}' does not support tools and no compatible fallback is configured.",
                    provider=primary_provider.name,
                )

        try:
            # 1. Attempt primary provider
            resp = await primary_provider.generate(
                model=primary_model,
                messages=messages,
                options=options,
                tools=tools,
            )
            response_ts = datetime.now(timezone.utc)

            # Record telemetry
            if db:
                await cls._record_usage_log(
                    db=db,
                    session_id=session_id,
                    agent_id=agent_id,
                    provider_name=primary_provider.name,
                    model_identifier=primary_model,
                    request_ts=request_ts,
                    response_ts=response_ts,
                    latency_ms=resp.latency_ms,
                    input_tokens=resp.usage.input_tokens,
                    output_tokens=resp.usage.output_tokens,
                    total_tokens=resp.usage.total_tokens,
                    is_success=True,
                    tool_call_count=len(resp.tool_calls),
                )

            return resp

        except Exception as primary_exc:
            response_ts = datetime.now(timezone.utc)
            norm_err = primary_provider.normalize_error(primary_exc)
            latency_ms = int((response_ts - request_ts).total_seconds() * 1000)

            # Record primary failure telemetry
            if db:
                await cls._record_usage_log(
                    db=db,
                    session_id=session_id,
                    agent_id=agent_id,
                    provider_name=primary_provider.name,
                    model_identifier=primary_model,
                    request_ts=request_ts,
                    response_ts=response_ts,
                    latency_ms=latency_ms,
                    input_tokens=0,
                    output_tokens=0,
                    total_tokens=0,
                    is_success=False,
                    error_category=norm_err.__class__.__name__,
                    tool_call_count=0,
                )

            # Check fallback eligibility
            can_fallback = (
                allow_fallback
                and fallback_provider is not None
                and fallback_model is not None
                and norm_err.is_retryable
                and not has_mutating_side_effects
            )

            if not can_fallback:
                logger.warning(
                    f"LLM request failed on {primary_provider.name}: {norm_err.message}. Fallback not eligible."
                )
                raise norm_err

            # 2. Attempt fallback provider
            logger.info(
                f"Falling back from {primary_provider.name} ({primary_model}) to {fallback_provider.name} ({fallback_model}) due to: {norm_err.message}"
            )
            fallback_req_ts = datetime.now(timezone.utc)
            try:
                fallback_resp = await fallback_provider.generate(
                    model=fallback_model,
                    messages=messages,
                    options=options,
                    tools=tools,
                )
                fallback_resp_ts = datetime.now(timezone.utc)

                if db:
                    await cls._record_usage_log(
                        db=db,
                        session_id=session_id,
                        agent_id=agent_id,
                        provider_name=fallback_provider.name,
                        model_identifier=fallback_model,
                        request_ts=fallback_req_ts,
                        response_ts=fallback_resp_ts,
                        latency_ms=fallback_resp.latency_ms,
                        input_tokens=fallback_resp.usage.input_tokens,
                        output_tokens=fallback_resp.usage.output_tokens,
                        total_tokens=fallback_resp.usage.total_tokens,
                        is_success=True,
                        tool_call_count=len(fallback_resp.tool_calls),
                    )

                return fallback_resp

            except Exception as fb_exc:
                fb_norm_err = fallback_provider.normalize_error(fb_exc)
                logger.error(f"Fallback provider {fallback_provider.name} also failed: {fb_norm_err.message}")
                raise fb_norm_err

    @staticmethod
    async def _record_usage_log(
        db: AsyncSession,
        session_id: Optional[uuid.UUID],
        agent_id: Optional[uuid.UUID],
        provider_name: str,
        model_identifier: str,
        request_ts: datetime,
        response_ts: datetime,
        latency_ms: int,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
        is_success: bool,
        error_category: Optional[str] = None,
        tool_call_count: int = 0,
    ) -> None:
        """Persist structured token and latency metrics to database."""
        try:
            log_entry = LLMUsageLog(
                session_id=session_id,
                agent_id=agent_id,
                provider_name=provider_name,
                model_identifier=model_identifier,
                request_timestamp=request_ts,
                response_timestamp=response_ts,
                latency_ms=latency_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                is_success=is_success,
                error_category=error_category,
                tool_call_count=tool_call_count,
            )
            db.add(log_entry)
            await db.flush()
        except Exception as e:
            logger.warning(f"Failed to record LLM usage log: {e}")
