"""Embedding Provider Base Contract and Exception Definitions.

Single Organization Edition: Physio One Clinic.
Provider-independent embedding abstraction with vector dimension validation.
"""
from abc import ABC, abstractmethod
from typing import List, Optional
import math

from app.llm.errors import LLMError


class EmbeddingError(LLMError):
    """Base exception for embedding generation failures."""
    pass


class EmbeddingDimensionMismatchError(EmbeddingError):
    """Raised when the returned vector dimension differs from the configured dimension."""
    pass


class BaseEmbeddingProvider(ABC):
    """Abstract base class for embedding providers."""

    def __init__(self, model_name: str, dimension: int = 1536):
        self.model_name = model_name
        self.dimension = dimension

    def validate_dimension(self, vector: List[float]) -> None:
        """Enforce strict vector dimension compatibility."""
        if len(vector) != self.dimension:
            raise EmbeddingDimensionMismatchError(
                f"Embedding vector dimension {len(vector)} does not match configured dimension {self.dimension} "
                f"for model '{self.model_name}'."
            )

    @staticmethod
    def normalize_l2(vector: List[float]) -> List[float]:
        """Normalize vector to unit length for accurate cosine distance comparison."""
        norm = math.sqrt(sum(x * x for x in vector))
        if norm == 0:
            return vector
        return [x / norm for x in vector]

    @abstractmethod
    async def embed_query(self, text: str) -> List[float]:
        """Generate normalized embedding vector for a single search query."""
        pass

    @abstractmethod
    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Batch generate normalized embedding vectors for text chunks."""
        pass
