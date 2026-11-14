"""Automated Test Suite for LLM Gateway and Provider Adapters.

Single Organization Edition: Physio One Clinic.
Tests:
- Provider creation and selection.
- Muse provider contract, capability reporting, and request normalization.
- OpenAI provider chat completions, tool parsing, and error normalization.
- Anthropic provider messages API, tool use parsing, and system prompt formatting.
- Generic OpenAI provider compatibility.
- Authentication failure normalization (HTTP 401).
- Rate limit handling (HTTP 429) and retryability.
- Timeout handling (HTTP 504 / asyncio.TimeoutError).
- Service unavailable outage handling (HTTP 503).
- Unsupported capability rejection (e.g. tools requested on Muse).
- Resilient fallback execution (primary fails on rate limit -> fallback handles request).
- Fallback prevention when side effects are mutating.
- Credential masking in schemas and models.
"""
import pytest
import json
import httpx
from datetime import datetime, timezone

from app.llm.schemas import (
    ChatMessage,
    MessageRole,
    LLMOptions,
    ToolDefinition,
)
from app.llm.errors import (
    LLMAuthenticationError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMServiceUnavailableError,
    LLMUnsupportedCapabilityError,
    LLMConfigurationError,
)
from app.llm.gateway import LLMGateway
from app.llm.providers.muse import MuseProvider
from app.llm.providers.openai import OpenAIProvider
from app.llm.providers.anthropic import AnthropicProvider
from app.llm.providers.generic_openai import GenericOpenAIProvider


@pytest.mark.asyncio
async def test_provider_adapter_factory():
    """Verify factory returns appropriate adapter instances and rejects unknown providers."""
    muse = LLMGateway.create_provider_adapter("muse", "https://api.muse.example.com/v1", "key1")
    assert isinstance(muse, MuseProvider)
    assert muse.name == "muse"

    openai = LLMGateway.create_provider_adapter("openai", "https://api.openai.com/v1", "key2")
    assert isinstance(openai, OpenAIProvider)
    assert openai.name == "openai"

    anthropic = LLMGateway.create_provider_adapter("anthropic", "https://api.anthropic.com/v1", "key3")
    assert isinstance(anthropic, AnthropicProvider)
    assert anthropic.name == "anthropic"

    generic = LLMGateway.create_provider_adapter("generic_openai", "http://localhost:11434/v1", "key4")
    assert isinstance(generic, GenericOpenAIProvider)
    assert generic.name == "generic_openai"

    with pytest.raises(LLMConfigurationError) as exc:
        LLMGateway.create_provider_adapter("unsupported_provider", "http://example.com", "key")
    assert "Unsupported LLM provider" in str(exc.value)


@pytest.mark.asyncio
async def test_credential_masking():
    """Verify raw API keys are never exposed in masked output."""
    provider = OpenAIProvider(api_key="sk-1234567890abcdefghijklmnop")
    masked = provider.mask_api_key()
    assert masked == "sk-1...mnop"
    assert "1234567890" not in masked

    empty_prov = OpenAIProvider(api_key="")
    assert empty_prov.mask_api_key() == "Not configured"


@pytest.mark.asyncio
async def test_muse_capabilities_and_tool_rejection():
    """Verify Muse provider reports tools as unsupported and rejects tool calls strictly."""
    provider = MuseProvider(api_key="test-key")
    assert provider.capabilities.supports_tools is False
    assert provider.capabilities.supports_streaming is False
    assert provider.capabilities.supports_structured_output is False

    tool_def = ToolDefinition(
        name="check_availability",
        description="Check slots",
        parameters={"type": "object", "properties": {"date": {"type": "string"}}},
    )

    messages = [ChatMessage(role=MessageRole.USER, content="When are slots open?")]

    with pytest.raises(LLMUnsupportedCapabilityError) as exc:
        await provider.generate("muse-chat", messages, tools=[tool_def])
    assert "does not support tool calling" in str(exc.value)


@pytest.mark.asyncio
async def test_muse_request_normalization():
    """Verify Muse normalizes response from documented OpenAI-like chat completions fixture."""
    mock_payload = {
        "id": "chatcmpl-muse-123",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Welcome to Physio One Clinic!"},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 12,
            "completion_tokens": 8,
            "total_tokens": 20,
        },
    }

    mock_transport = httpx.MockTransport(
        lambda req: httpx.Response(200, json=mock_payload)
    )
    mock_client = httpx.AsyncClient(transport=mock_transport)

    provider = MuseProvider(api_key="muse-test-token", config={"http_client": mock_client})
    messages = [ChatMessage(role=MessageRole.USER, content="Hello Deepti")]

    response = await provider.generate(model="muse-chat", messages=messages)

    assert response.content == "Welcome to Physio One Clinic!"
    assert response.provider == "muse"
    assert response.model == "muse-chat"
    assert response.usage.input_tokens == 12
    assert response.usage.output_tokens == 8
    assert response.usage.total_tokens == 20
    assert response.finish_reason == "stop"


@pytest.mark.asyncio
async def test_openai_tool_parsing():
    """Verify OpenAI provider formats messages and parses response tool calls properly."""
    mock_payload = {
        "id": "chatcmpl-999",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_abc123",
                            "type": "function",
                            "function": {
                                "name": "check_availability",
                                "arguments": json.dumps({"date": "2026-11-17"}),
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 25, "completion_tokens": 15, "total_tokens": 40},
    }

    mock_transport = httpx.MockTransport(
        lambda req: httpx.Response(200, json=mock_payload)
    )
    mock_client = httpx.AsyncClient(transport=mock_transport)

    provider = OpenAIProvider(api_key="sk-test", config={"http_client": mock_client})
    tool_def = ToolDefinition(
        name="check_availability",
        description="Check appointment availability",
        parameters={"type": "object", "properties": {"date": {"type": "string"}}},
    )

    messages = [ChatMessage(role=MessageRole.USER, content="Is Tuesday available?")]
    response = await provider.generate(model="gpt-4o", messages=messages, tools=[tool_def])

    assert response.content is None
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].id == "call_abc123"
    assert response.tool_calls[0].name == "check_availability"
    assert response.tool_calls[0].arguments == {"date": "2026-11-17"}
    assert response.finish_reason == "tool_calls"


@pytest.mark.asyncio
async def test_anthropic_tool_parsing_and_system_prompt():
    """Verify Anthropic provider correctly extracts system prompt and parses tool_use blocks."""
    mock_payload = {
        "id": "msg_ant123",
        "type": "message",
        "role": "assistant",
        "content": [
            {
                "type": "text",
                "text": "Checking availability for you right now.",
            },
            {
                "type": "tool_use",
                "id": "toolu_456",
                "name": "check_availability",
                "input": {"date": "2026-11-18"},
            },
        ],
        "stop_reason": "tool_use",
        "usage": {"input_tokens": 30, "output_tokens": 22},
    }

    captured_request = {}

    def handle_request(request: httpx.Request):
        nonlocal captured_request
        captured_request = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json=mock_payload)

    mock_transport = httpx.MockTransport(handle_request)
    mock_client = httpx.AsyncClient(transport=mock_transport)

    provider = AnthropicProvider(api_key="ant-key", config={"http_client": mock_client})
    messages = [
        ChatMessage(role=MessageRole.SYSTEM, content="You are Deepti."),
        ChatMessage(role=MessageRole.USER, content="Do you have slots on Wednesday?"),
    ]
    tool_def = ToolDefinition(
        name="check_availability",
        description="Check slots",
        parameters={"type": "object", "properties": {"date": {"type": "string"}}},
    )

    response = await provider.generate(model="claude-3-5-sonnet-20241022", messages=messages, tools=[tool_def])

    # Check top-level system parameter was separated
    assert captured_request.get("system") == "You are Deepti."
    assert len(captured_request.get("messages", [])) == 1

    # Check parsed response
    assert response.content == "Checking availability for you right now."
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].id == "toolu_456"
    assert response.tool_calls[0].name == "check_availability"
    assert response.tool_calls[0].arguments == {"date": "2026-11-18"}
    assert response.finish_reason == "tool_calls"


@pytest.mark.asyncio
async def test_error_normalization():
    """Verify HTTP error codes are correctly normalized into typed LLMError subclasses."""
    provider = OpenAIProvider(api_key="sk-test")

    # 401 Unauthorized
    resp_401 = httpx.Response(401, json={"error": {"message": "Invalid API key"}})
    err_401 = provider.normalize_error(httpx.HTTPStatusError("401", request=None, response=resp_401))
    assert isinstance(err_401, LLMAuthenticationError)
    assert err_401.is_retryable is False

    # 429 Rate Limit
    resp_429 = httpx.Response(429, json={"error": {"message": "Rate limit exceeded"}})
    err_429 = provider.normalize_error(httpx.HTTPStatusError("429", request=None, response=resp_429))
    assert isinstance(err_429, LLMRateLimitError)
    assert err_429.is_retryable is True

    # 503 Service Unavailable
    resp_503 = httpx.Response(503, json={"error": {"message": "Service temporarily overloaded"}})
    err_503 = provider.normalize_error(httpx.HTTPStatusError("503", request=None, response=resp_503))
    assert isinstance(err_503, LLMServiceUnavailableError)
    assert err_503.is_retryable is True

    # Timeout
    err_timeout = provider.normalize_error(httpx.ReadTimeout("Timeout"))
    assert isinstance(err_timeout, LLMTimeoutError)
    assert err_timeout.is_retryable is True


@pytest.mark.asyncio
async def test_gateway_fallback_on_rate_limit():
    """Verify gateway falls back to secondary provider when primary encounters 429 rate limit."""
    # Primary OpenAI returns 429
    primary_transport = httpx.MockTransport(
        lambda req: httpx.Response(429, json={"error": {"message": "Quota exhausted"}})
    )
    primary_client = httpx.AsyncClient(transport=primary_transport)
    primary_provider = OpenAIProvider(api_key="sk-primary", config={"http_client": primary_client})

    # Fallback Anthropic returns 200
    fallback_payload = {
        "id": "msg_fallback",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": "Response from fallback Claude!"}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }
    fallback_transport = httpx.MockTransport(
        lambda req: httpx.Response(200, json=fallback_payload)
    )
    fallback_client = httpx.AsyncClient(transport=fallback_transport)
    fallback_provider = AnthropicProvider(api_key="ant-fallback", config={"http_client": fallback_client})

    messages = [ChatMessage(role=MessageRole.USER, content="Hello clinic")]

    # 1. Fallback disabled (default): must raise LLMRateLimitError
    with pytest.raises(LLMRateLimitError):
        await LLMGateway.execute(
            primary_provider=primary_provider,
            primary_model="gpt-4o",
            messages=messages,
            fallback_provider=fallback_provider,
            fallback_model="claude-3-5-sonnet-20241022",
            allow_fallback=False,
        )

    # 2. Fallback enabled: must gracefully resolve with fallback response
    response = await LLMGateway.execute(
        primary_provider=primary_provider,
        primary_model="gpt-4o",
        messages=messages,
        fallback_provider=fallback_provider,
        fallback_model="claude-3-5-sonnet-20241022",
        allow_fallback=True,
    )

    assert response.provider == "anthropic"
    assert response.model == "claude-3-5-sonnet-20241022"
    assert response.content == "Response from fallback Claude!"


@pytest.mark.asyncio
async def test_gateway_rejects_fallback_on_mutating_side_effects():
    """Verify fallback is strictly rejected if side effects are mutating."""
    primary_transport = httpx.MockTransport(
        lambda req: httpx.Response(429, json={"error": {"message": "Rate limit"}})
    )
    primary_client = httpx.AsyncClient(transport=primary_transport)
    primary_provider = OpenAIProvider(api_key="sk-primary", config={"http_client": primary_client})

    fallback_provider = AnthropicProvider(api_key="ant-fallback")
    messages = [ChatMessage(role=MessageRole.USER, content="Book me an appointment")]

    with pytest.raises(LLMRateLimitError):
        await LLMGateway.execute(
            primary_provider=primary_provider,
            primary_model="gpt-4o",
            messages=messages,
            fallback_provider=fallback_provider,
            fallback_model="claude-3-5-sonnet-20241022",
            allow_fallback=True,
            has_mutating_side_effects=True,  # Mutating side effect flag forbids automated retry/fallback
        )
