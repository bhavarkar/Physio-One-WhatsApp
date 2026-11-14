"""Anthropic Provider Adapter.

Official Anthropic Messages API implementation supporting Claude 3.5 Sonnet / Haiku,
tool-calling, streaming, and error normalization.
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

logger = logging.getLogger("physio_one.llm.anthropic")


class AnthropicProvider(BaseLLMProvider):
    """Adapter for Anthropic Messages API."""

    DEFAULT_BASE_URL = "https://api.anthropic.com/v1"
    DEFAULT_MODELS = ["claude-3-5-sonnet-20241022", "claude-3-haiku-20240307", "claude-3-opus-20240229"]
    API_VERSION = "2023-06-01"

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        effective_base_url = base_url or self.DEFAULT_BASE_URL
        effective_api_key = api_key or ""
        super().__init__(
            name="anthropic",
            base_url=effective_base_url,
            api_key=effective_api_key,
            config=config,
        )

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_tools=True,
            supports_structured_output=False,
            supports_streaming=True,
            supports_vision=True,
        )

    def _format_messages_and_system(
        self, messages: List[ChatMessage]
    ) -> tuple[Optional[str], List[Dict[str, Any]]]:
        """Anthropic separates top-level system prompt from conversation messages."""
        system_prompt: Optional[str] = None
        formatted_messages = []

        for m in messages:
            if m.role == MessageRole.SYSTEM:
                system_prompt = m.content or ""
                continue

            if m.role == MessageRole.USER:
                formatted_messages.append({"role": "user", "content": m.content or ""})
            elif m.role == MessageRole.ASSISTANT:
                content_blocks: List[Dict[str, Any]] = []
                if m.content:
                    content_blocks.append({"type": "text", "text": m.content})
                if m.tool_calls:
                    for tc in m.tool_calls:
                        content_blocks.append({
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.name,
                            "input": tc.arguments,
                        })
                formatted_messages.append({
                    "role": "assistant",
                    "content": content_blocks if content_blocks else [{"type": "text", "text": ""}],
                })
            elif m.role == MessageRole.TOOL:
                formatted_messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": m.tool_call_id,
                            "content": m.content or "",
                        }
                    ],
                })

        return system_prompt, formatted_messages

    def _format_tools(self, tools: Optional[List[ToolDefinition]]) -> Optional[List[Dict[str, Any]]]:
        """Convert ToolDefinition into Anthropic tools schema."""
        if not tools:
            return None
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.parameters,
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
        """Execute chat completion request via Messages API."""
        options = options or LLMOptions()
        start_time = time.perf_counter()

        system_prompt, formatted_messages = self._format_messages_and_system(messages)

        payload: Dict[str, Any] = {
            "model": model,
            "messages": formatted_messages,
            "max_tokens": options.max_tokens,
            "temperature": options.temperature,
        }

        if system_prompt:
            payload["system"] = system_prompt

        formatted_tools = self._format_tools(tools)
        if formatted_tools:
            payload["tools"] = formatted_tools

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.API_VERSION,
            "content-type": "application/json",
            "User-Agent": "PhysioOne-AI-Platform/1.0",
        }

        client = self.config.get("http_client")
        should_close = False
        if client is None:
            client = httpx.AsyncClient(timeout=options.timeout_seconds)
            should_close = True

        try:
            url = f"{self.base_url}/messages"
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

            latency_ms = int((time.perf_counter() - start_time) * 1000)

            # Parse content blocks and tool calls
            text_parts = []
            tool_calls: List[ToolCall] = []

            for block in data.get("content", []):
                b_type = block.get("type")
                if b_type == "text":
                    text_parts.append(block.get("text", ""))
                elif b_type == "tool_use":
                    tc_id = block.get("id", f"call_{len(tool_calls)}")
                    tc_name = block.get("name", "")
                    tc_input = block.get("input", {})
                    tool_calls.append(ToolCall.from_raw(tc_id, tc_name, tc_input))

            final_content = "".join(text_parts) if text_parts else None
            stop_reason = data.get("stop_reason", "end_turn")
            finish_reason = "tool_calls" if tool_calls else ("stop" if stop_reason == "end_turn" else stop_reason)

            usage_data = data.get("usage", {})
            input_tokens = usage_data.get("input_tokens", 0)
            output_tokens = usage_data.get("output_tokens", 0)
            usage = LLMUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            )

            return LLMResponse(
                content=final_content,
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
        """Stream chunks from Anthropic SSE endpoint."""
        options = options or LLMOptions()
        system_prompt, formatted_messages = self._format_messages_and_system(messages)

        payload: Dict[str, Any] = {
            "model": model,
            "messages": formatted_messages,
            "max_tokens": options.max_tokens,
            "temperature": options.temperature,
            "stream": True,
        }
        if system_prompt:
            payload["system"] = system_prompt

        formatted_tools = self._format_tools(tools)
        if formatted_tools:
            payload["tools"] = formatted_tools

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.API_VERSION,
            "content-type": "application/json",
            "User-Agent": "PhysioOne-AI-Platform/1.0",
        }

        client = self.config.get("http_client")
        should_close = False
        if client is None:
            client = httpx.AsyncClient(timeout=options.timeout_seconds)
            should_close = True

        try:
            url = f"{self.base_url}/messages"
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    try:
                        event_json = json.loads(data_str)
                        ev_type = event_json.get("type")
                        if ev_type == "content_block_delta":
                            delta = event_json.get("delta", {})
                            if delta.get("type") == "text_delta":
                                yield LLMStreamChunk(delta_content=delta.get("text"))
                        elif ev_type == "message_stop":
                            yield LLMStreamChunk(finish_reason="stop")
                            break
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            raise self.normalize_error(e)
        finally:
            if should_close:
                await client.aclose()

    async def validate_connection(self) -> ProviderValidationResult:
        """Validate Anthropic credentials."""
        start_time = time.perf_counter()

        if not self.api_key:
            return ProviderValidationResult(
                is_valid=False,
                status="unhealthy",
                latency_ms=0,
                error_message="Anthropic API key is not configured.",
                capabilities=self.capabilities,
                detected_models=[],
            )

        client = self.config.get("http_client")
        should_close = False
        if client is None:
            client = httpx.AsyncClient(timeout=10.0)
            should_close = True

        try:
            # Anthropic validation: probe with a 1-token test message
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": self.API_VERSION,
                "content-type": "application/json",
                "User-Agent": "PhysioOne-AI-Platform/1.0",
            }
            probe_payload = {
                "model": "claude-3-haiku-20240307",
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "ping"}],
            }
            resp = await client.post(f"{self.base_url}/messages", json=probe_payload, headers=headers)
            latency_ms = int((time.perf_counter() - start_time) * 1000)

            if resp.status_code == 200:
                return ProviderValidationResult(
                    is_valid=True,
                    status="healthy",
                    latency_ms=latency_ms,
                    capabilities=self.capabilities,
                    detected_models=self.DEFAULT_MODELS,
                    details={"base_url": self.base_url},
                )
            else:
                return ProviderValidationResult(
                    is_valid=False,
                    status="degraded",
                    latency_ms=latency_ms,
                    error_message=f"Anthropic endpoint returned HTTP {resp.status_code}: {resp.text[:200]}",
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
