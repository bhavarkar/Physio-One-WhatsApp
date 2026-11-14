"""OpenAI Provider Adapter.

Official OpenAI Chat Completions API implementation with full tool-calling,
streaming, structured output, and error normalization.
"""
from typing import Optional, List, Dict, Any, AsyncIterator
import time
import json
import httpx
import logging

from app.llm.base import BaseLLMProvider
from app.llm.schemas import (
    ChatMessage,
    LLMOptions,
    LLMResponse,
    LLMStreamChunk,
    LLMUsage,
    MessageRole,
    ProviderCapabilities,
    ProviderValidationResult,
    ToolCall,
    ToolDefinition,
)
from app.llm.errors import (
    LLMUnsupportedCapabilityError,
)

logger = logging.getLogger("physio_one.llm.openai")


class OpenAIProvider(BaseLLMProvider):
    """Adapter for official OpenAI Chat Completions API."""

    DEFAULT_BASE_URL = "https://api.openai.com/v1"
    DEFAULT_MODELS = ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"]

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        effective_base_url = base_url or self.DEFAULT_BASE_URL
        effective_api_key = api_key or ""
        super().__init__(
            name="openai",
            base_url=effective_base_url,
            api_key=effective_api_key,
            config=config,
        )

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_tools=True,
            supports_structured_output=True,
            supports_streaming=True,
            supports_vision=True,
        )

    def _format_messages(self, messages: List[ChatMessage]) -> List[Dict[str, Any]]:
        """Format normalized ChatMessage instances into OpenAI JSON format."""
        formatted = []
        for m in messages:
            msg: Dict[str, Any] = {"role": m.role.value}
            if m.content is not None:
                msg["content"] = m.content

            if m.name:
                msg["name"] = m.name

            if m.role == MessageRole.ASSISTANT and m.tool_calls:
                msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments) if isinstance(tc.arguments, dict) else str(tc.arguments),
                        },
                    }
                    for tc in m.tool_calls
                ]

            if m.role == MessageRole.TOOL:
                msg["tool_call_id"] = m.tool_call_id
                if "content" not in msg or msg["content"] is None:
                    msg["content"] = ""

            formatted.append(msg)
        return formatted

    def _format_tools(self, tools: Optional[List[ToolDefinition]]) -> Optional[List[Dict[str, Any]]]:
        """Format ToolDefinition instances into OpenAI function calling format."""
        if not tools:
            return None
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]

    async def generate(
        self,
        model: str,
        messages: List[ChatMessage],
        options: Optional[LLMOptions] = None,
        tools: Optional[List[ToolDefinition]] = None,
    ) -> LLMResponse:
        """Execute chat completion request."""
        options = options or LLMOptions()
        start_time = time.perf_counter()

        payload: Dict[str, Any] = {
            "model": model,
            "messages": self._format_messages(messages),
            "temperature": options.temperature,
            "max_tokens": options.max_tokens,
        }

        formatted_tools = self._format_tools(tools)
        if formatted_tools:
            payload["tools"] = formatted_tools
            payload["tool_choice"] = "auto"

        if options.response_format:
            payload["response_format"] = options.response_format

        if options.stop_sequences:
            payload["stop"] = options.stop_sequences

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "PhysioOne-AI-Platform/1.0",
        }

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

            choices = data.get("choices", [])
            content = None
            finish_reason = "stop"
            tool_calls: List[ToolCall] = []

            if choices:
                first_choice = choices[0]
                msg = first_choice.get("message", {})
                content = msg.get("content")
                finish_reason = first_choice.get("finish_reason", "stop")

                raw_tool_calls = msg.get("tool_calls", [])
                for rtc in raw_tool_calls:
                    tc_id = rtc.get("id", f"call_{len(tool_calls)}")
                    fn = rtc.get("function", {})
                    fn_name = fn.get("name", "")
                    fn_args = fn.get("arguments", "{}")
                    tool_calls.append(ToolCall.from_raw(tc_id, fn_name, fn_args))

            usage_data = data.get("usage", {})
            usage = LLMUsage(
                input_tokens=usage_data.get("prompt_tokens", 0),
                output_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
            )

            return LLMResponse(
                content=content,
                tool_calls=tool_calls,
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
        """Stream chunks from OpenAI server-sent events (SSE)."""
        options = options or LLMOptions()
        payload: Dict[str, Any] = {
            "model": model,
            "messages": self._format_messages(messages),
            "temperature": options.temperature,
            "max_tokens": options.max_tokens,
            "stream": True,
        }

        formatted_tools = self._format_tools(tools)
        if formatted_tools:
            payload["tools"] = formatted_tools
            payload["tool_choice"] = "auto"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "PhysioOne-AI-Platform/1.0",
        }

        client = self.config.get("http_client")
        should_close = False
        if client is None:
            client = httpx.AsyncClient(timeout=options.timeout_seconds)
            should_close = True

        try:
            url = f"{self.base_url}/chat/completions"
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk_json = json.loads(data_str)
                        choices = chunk_json.get("choices", [])
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {})
                        delta_content = delta.get("content")
                        finish_reason = choices[0].get("finish_reason")

                        yield LLMStreamChunk(
                            delta_content=delta_content,
                            finish_reason=finish_reason,
                        )
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            raise self.normalize_error(e)
        finally:
            if should_close:
                await client.aclose()

    async def validate_connection(self) -> ProviderValidationResult:
        """Validate credentials against OpenAI /v1/models endpoint."""
        start_time = time.perf_counter()

        if not self.api_key:
            return ProviderValidationResult(
                is_valid=False,
                status="unhealthy",
                latency_ms=0,
                error_message="OpenAI API key is not configured.",
                capabilities=self.capabilities,
                detected_models=[],
            )

        client = self.config.get("http_client")
        should_close = False
        if client is None:
            client = httpx.AsyncClient(timeout=10.0)
            should_close = True

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": "PhysioOne-AI-Platform/1.0",
            }
            resp = await client.get(f"{self.base_url}/models", headers=headers)
            latency_ms = int((time.perf_counter() - start_time) * 1000)

            if resp.status_code == 200:
                data = resp.json()
                detected = [m.get("id") for m in data.get("data", []) if "gpt" in m.get("id", "")]
                return ProviderValidationResult(
                    is_valid=True,
                    status="healthy",
                    latency_ms=latency_ms,
                    capabilities=self.capabilities,
                    detected_models=detected[:10] if detected else self.DEFAULT_MODELS,
                    details={"base_url": self.base_url},
                )
            else:
                return ProviderValidationResult(
                    is_valid=False,
                    status="degraded",
                    latency_ms=latency_ms,
                    error_message=f"OpenAI endpoint returned HTTP {resp.status_code}: {resp.text[:200]}",
                    capabilities=self.capabilities,
                    detected_models=self.DEFAULT_MODELS,
                )
        except Exception as e:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            normalized = self.normalize_error(e)
            return ProviderValidationResult(
                is_valid=False,
                status="unhealthy",
                latency_ms=latency_ms,
                error_message=f"Connection test failed: {normalized.message}",
                capabilities=self.capabilities,
                detected_models=self.DEFAULT_MODELS,
            )
        finally:
            if should_close:
                await client.aclose()
