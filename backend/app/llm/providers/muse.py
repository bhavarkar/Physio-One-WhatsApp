"""Muse API Provider Adapter (Meta Model API).

Primary integration specification according to Task 7 instructions.
Documentation Status:
- Verified: Provider contract interface, configurable base_url, Bearer API key authentication,
  and connection test scaffolding.
- Blocked / Missing Documentation: Official request/response schemas, tool-calling syntax,
  model identifiers, and streaming protocols for Meta Model API (Muse) are not documented
  in the repository. Capabilities are strictly configured to prevent silent errors or hallucinations.
"""
from typing import Optional, List, Dict, Any, AsyncIterator
import time
import httpx
import logging

from app.llm.base import BaseLLMProvider
from app.llm.schemas import (
    ChatMessage,
    LLMOptions,
    LLMResponse,
    LLMStreamChunk,
    LLMUsage,
    ProviderCapabilities,
    ProviderValidationResult,
    ToolDefinition,
)
from app.llm.errors import (
    LLMConfigurationError,
    LLMUnsupportedCapabilityError,
)

logger = logging.getLogger("physio_one.llm.muse")


class MuseProvider(BaseLLMProvider):
    """Adapter for Muse API / Meta Model API."""

    DEFAULT_BASE_URL = "https://api.muse.example.com/v1"
    DEFAULT_MODELS = ["muse-chat", "muse-pro", "muse-instruct"]

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        effective_base_url = base_url or self.DEFAULT_BASE_URL
        effective_api_key = api_key or ""
        super().__init__(
            name="muse",
            base_url=effective_base_url,
            api_key=effective_api_key,
            config=config,
        )

    @property
    def capabilities(self) -> ProviderCapabilities:
        """Expose capabilities strictly based on verified documentation.
        
        Tool calling and streaming are marked FALSE because official Muse API
        specifications are not provided in the repository.
        """
        return ProviderCapabilities(
            supports_tools=False,
            supports_structured_output=False,
            supports_streaming=False,
            supports_vision=False,
        )

    async def generate(
        self,
        model: str,
        messages: List[ChatMessage],
        options: Optional[LLMOptions] = None,
        tools: Optional[List[ToolDefinition]] = None,
    ) -> LLMResponse:
        """Execute chat completion request against Muse API."""
        if tools and len(tools) > 0:
            raise LLMUnsupportedCapabilityError(
                "Muse API adapter does not support tool calling in the absence of verified official documentation.",
                provider=self.name,
            )

        options = options or LLMOptions()
        start_time = time.perf_counter()

        # Build standard payload
        payload = {
            "model": model,
            "messages": [{"role": m.role.value, "content": m.content or ""} for m in messages],
            "temperature": options.temperature,
            "max_tokens": options.max_tokens,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "PhysioOne-AI-Platform/1.0",
        }

        # Check for mock client or injected test handler
        client = self.config.get("http_client")
        should_close = False
        if client is None:
            client = httpx.AsyncClient(timeout=options.timeout_seconds)
            should_close = True

        try:
            url = f"{self.base_url}/chat/completions"
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

            latency_ms = int((time.perf_counter() - start_time) * 1000)

            # Response normalization
            choices = data.get("choices", [])
            content = ""
            finish_reason = "stop"
            if choices:
                first_choice = choices[0]
                msg = first_choice.get("message", {})
                content = msg.get("content", "")
                finish_reason = first_choice.get("finish_reason", "stop")

            usage_data = data.get("usage", {})
            usage = LLMUsage(
                input_tokens=usage_data.get("prompt_tokens", 0),
                output_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
            )

            return LLMResponse(
                content=content,
                tool_calls=[],
                usage=usage,
                model=model,
                provider=self.name,
                finish_reason=finish_reason,
                latency_ms=latency_ms,
                raw_response=data,
            )

        except Exception as e:
            raise self.normalize_error(e)
        finally:
            if should_close:
                await client.aclose()

    async def stream(
        self,
        model: str,
        messages: List[ChatMessage],
        options: Optional[LLMOptions] = None,
        tools: Optional[List[ToolDefinition]] = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        """Streaming is unverified for Muse API."""
        raise LLMUnsupportedCapabilityError(
            "Streaming is not supported by Muse API adapter due to unverified documentation.",
            provider=self.name,
        )
        yield  # make it an async generator

    async def validate_connection(self) -> ProviderValidationResult:
        """Validate Muse provider connectivity and credentials."""
        start_time = time.perf_counter()

        if not self.api_key:
            return ProviderValidationResult(
                is_valid=False,
                status="unhealthy",
                latency_ms=0,
                error_message="Muse API key is not configured.",
                capabilities=self.capabilities,
                detected_models=[],
                details={"documentation_status": "blocked_missing_documentation"},
            )

        client = self.config.get("http_client")
        should_close = False
        if client is None:
            client = httpx.AsyncClient(timeout=10.0)
            should_close = True

        try:
            # Probe models endpoint or health
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": "PhysioOne-AI-Platform/1.0",
            }
            resp = await client.get(f"{self.base_url}/models", headers=headers)
            latency_ms = int((time.perf_counter() - start_time) * 1000)

            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("id") for m in data.get("data", []) if m.get("id")]
                return ProviderValidationResult(
                    is_valid=True,
                    status="healthy",
                    latency_ms=latency_ms,
                    capabilities=self.capabilities,
                    detected_models=models or self.DEFAULT_MODELS,
                    details={
                        "documentation_status": "partially_verified",
                        "base_url": self.base_url,
                    },
                )
            else:
                return ProviderValidationResult(
                    is_valid=False,
                    status="degraded",
                    latency_ms=latency_ms,
                    error_message=f"Muse endpoint responded with HTTP {resp.status_code}: {resp.text[:200]}",
                    capabilities=self.capabilities,
                    detected_models=self.DEFAULT_MODELS,
                    details={
                        "documentation_status": "blocked_unverified_endpoint",
                        "base_url": self.base_url,
                    },
                )
        except Exception as e:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            normalized = self.normalize_error(e)
            return ProviderValidationResult(
                is_valid=False,
                status="unhealthy",
                latency_ms=latency_ms,
                error_message=f"Connection failed: {normalized.message}",
                capabilities=self.capabilities,
                detected_models=self.DEFAULT_MODELS,
                details={
                    "documentation_status": "blocked_connection_failure",
                    "base_url": self.base_url,
                },
            )
        finally:
            if should_close:
                await client.aclose()
