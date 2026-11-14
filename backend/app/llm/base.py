"""Abstract Base Class for LLM Provider Adapters.

Single Organization Edition: Physio One Clinic.
Enforces a uniform contract across all LLM backends (Muse, OpenAI, Anthropic, Generic).
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, AsyncIterator
import httpx
import logging

from app.llm.schemas import (
    ChatMessage,
    LLMOptions,
    LLMResponse,
    LLMStreamChunk,
    ProviderCapabilities,
    ProviderValidationResult,
    ToolDefinition,
)
from app.llm.errors import (
    LLMError,
    LLMAuthenticationError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMServiceUnavailableError,
    LLMConfigurationError,
)

logger = logging.getLogger("physio_one.llm")


class BaseLLMProvider(ABC):
    """Abstract interface for LLM provider adapters."""

    def __init__(
        self,
        name: str,
        base_url: str,
        api_key: str,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.config = config or {}
        self.validate_configuration()

    def validate_configuration(self) -> None:
        """Validate essential configuration parameters."""
        if not self.base_url:
            raise LLMConfigurationError(f"Provider '{self.name}' requires a valid base_url.", provider=self.name)

    @property
    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        """Return explicit capability matrix supported by this provider."""
        pass

    @abstractmethod
    async def generate(
        self,
        model: str,
        messages: List[ChatMessage],
        options: Optional[LLMOptions] = None,
        tools: Optional[List[ToolDefinition]] = None,
    ) -> LLMResponse:
        """Execute a synchronous/non-streaming chat completion."""
        pass

    @abstractmethod
    async def stream(
        self,
        model: str,
        messages: List[ChatMessage],
        options: Optional[LLMOptions] = None,
        tools: Optional[List[ToolDefinition]] = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        """Stream completion tokens and tool call chunks."""
        pass

    @abstractmethod
    async def validate_connection(self) -> ProviderValidationResult:
        """Perform a live diagnostics handshake verifying credentials and API availability."""
        pass

    def mask_api_key(self) -> str:
        """Return a masked representation of the API key for safe frontend / logging presentation."""
        if not self.api_key:
            return "Not configured"
        key = self.api_key.strip()
        if len(key) <= 8:
            return "****"
        return f"{key[:4]}...{key[-4:]}"

    def normalize_error(self, exc: Exception) -> LLMError:
        """Normalize generic exceptions and HTTP errors into typed LLMError instances."""
        if isinstance(exc, LLMError):
            return exc

        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            err_text = ""
            try:
                err_data = exc.response.json()
                err_text = err_data.get("error", {}).get("message") or str(err_data)
            except Exception:
                err_text = exc.response.text[:200]

            if status in [401, 403]:
                return LLMAuthenticationError(
                    f"Authentication rejected by {self.name}: {err_text}",
                    provider=self.name,
                    details={"status_code": status},
                )
            elif status == 429:
                return LLMRateLimitError(
                    f"Rate limit or quota exceeded for {self.name}: {err_text}",
                    provider=self.name,
                    details={"status_code": status},
                )
            elif status in [500, 502, 503, 504]:
                return LLMServiceUnavailableError(
                    f"Upstream service outage for {self.name} (HTTP {status}): {err_text}",
                    provider=self.name,
                    details={"status_code": status},
                )
            return LLMError(
                f"HTTP {status} from {self.name}: {err_text}",
                provider=self.name,
                status_code=status,
            )

        if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
            return LLMTimeoutError(f"Request to {self.name} timed out.", provider=self.name)

        if isinstance(exc, (httpx.ConnectError, httpx.NetworkError)):
            return LLMServiceUnavailableError(
                f"Failed to connect to {self.name} at {self.base_url}.", provider=self.name
            )

        return LLMError(f"Unexpected error communicating with {self.name}: {str(exc)}", provider=self.name)
