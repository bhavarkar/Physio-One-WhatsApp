"""LLM Gateway Package for Physio One WhatsApp AI Platform."""
from app.llm.base import BaseLLMProvider
from app.llm.gateway import LLMGateway
from app.llm.schemas import (
    ChatMessage,
    MessageRole,
    ToolCall,
    ToolDefinition,
    LLMOptions,
    LLMUsage,
    LLMResponse,
    LLMStreamChunk,
    ProviderCapabilities,
    ProviderValidationResult,
)
from app.llm.errors import (
    LLMError,
    LLMConfigurationError,
    LLMAuthenticationError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMServiceUnavailableError,
    LLMContextLengthExceededError,
    LLMUnsupportedCapabilityError,
)

__all__ = [
    "BaseLLMProvider",
    "LLMGateway",
    "ChatMessage",
    "MessageRole",
    "ToolCall",
    "ToolDefinition",
    "LLMOptions",
    "LLMUsage",
    "LLMResponse",
    "LLMStreamChunk",
    "ProviderCapabilities",
    "ProviderValidationResult",
    "LLMError",
    "LLMConfigurationError",
    "LLMAuthenticationError",
    "LLMRateLimitError",
    "LLMTimeoutError",
    "LLMServiceUnavailableError",
    "LLMContextLengthExceededError",
    "LLMUnsupportedCapabilityError",
]
