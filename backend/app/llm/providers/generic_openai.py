"""Generic OpenAI-Compatible Provider Adapter.

Supports local and private cloud endpoints conforming to OpenAI Chat Completions API
(e.g., Ollama, vLLM, LMStudio, Azure OpenAI, self-hosted gateways).
"""
from typing import Optional, Dict, Any
from app.llm.providers.openai import OpenAIProvider


class GenericOpenAIProvider(OpenAIProvider):
    """Adapter for generic OpenAI-compatible endpoints."""

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            base_url=base_url,
            api_key=api_key or "sk-local-no-key",
            config=config,
        )
        self.name = "generic_openai"
