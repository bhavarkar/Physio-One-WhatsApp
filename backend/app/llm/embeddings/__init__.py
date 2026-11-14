"""Embeddings Package and Factory Function."""
import os
from typing import Optional

from app.llm.embeddings.base import (
    BaseEmbeddingProvider,
    EmbeddingError,
    EmbeddingDimensionMismatchError,
)
from app.llm.embeddings.deterministic import DeterministicEmbeddingProvider
from app.llm.embeddings.openai import OpenAIEmbeddingProvider


def get_embedding_provider(
    provider_type: Optional[str] = None,
    model_name: Optional[str] = None,
    api_key: Optional[str] = None,
    dimension: int = 1536,
) -> BaseEmbeddingProvider:
    """Factory resolving the active embedding provider.
    
    In production (ENVIRONMENT=production), requires a verified real embedding provider
    and strictly forbids falling back to deterministic mock embeddings.
    """
    env = os.getenv("ENVIRONMENT", "development").lower()
    selected_type = (provider_type or os.getenv("EMBEDDING_PROVIDER", "deterministic")).lower()
    
    if selected_type == "openai":
        resolved_key = api_key or os.getenv("OPENAI_API_KEY")
        if not resolved_key or resolved_key.startswith("your_"):
            if env == "production":
                raise EmbeddingError(
                    "Production embedding provider 'openai' requires a valid OPENAI_API_KEY. "
                    "Cannot initialize semantic search without credentials."
                )
        else:
            return OpenAIEmbeddingProvider(
                api_key=resolved_key,
                model_name=model_name or "text-embedding-3-small",
                dimension=dimension,
            )
    
    # Production guardrail: Deterministic mock vectors are NEVER permitted in production
    if env == "production":
        raise EmbeddingError(
            f"Deterministic mock embeddings are strictly disallowed in production. "
            f"Configured provider '{selected_type}' is not a valid production embedding provider. "
            f"Configure EMBEDDING_PROVIDER=openai with a valid API key."
        )

    # Local development / offline testing fallback: Deterministic provider
    return DeterministicEmbeddingProvider(
        model_name=model_name or "deterministic-1536",
        dimension=dimension,
    )


__all__ = [
    "BaseEmbeddingProvider",
    "EmbeddingError",
    "EmbeddingDimensionMismatchError",
    "DeterministicEmbeddingProvider",
    "OpenAIEmbeddingProvider",
    "get_embedding_provider",
]
