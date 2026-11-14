"""Deterministic Embedding Provider for Offline, Testing, and Local Development.

Single Organization Edition: Physio One Clinic.
Generates reproducible, normalized vectors without external network calls or API costs.
Explicitly identified for testing/development - does NOT masquerade as live production embeddings.
"""
import hashlib
import random
import re
from typing import List

from app.llm.embeddings.base import BaseEmbeddingProvider


class DeterministicEmbeddingProvider(BaseEmbeddingProvider):
    """Reproducible, zero-network embedding provider for tests and sandbox environments."""

    is_test_provider: bool = True

    def __init__(self, model_name: str = "deterministic-1536", dimension: int = 1536):
        import os
        from app.llm.embeddings.base import EmbeddingError
        if os.getenv("ENVIRONMENT", "").lower() == "production":
            raise EmbeddingError("Deterministic mock embeddings are test-only and strictly disallowed in production.")
        super().__init__(model_name=model_name, dimension=dimension)

    def _generate_vector(self, text: str) -> List[float]:
        """Derive a reproducible unit vector from text tokens and SHA-256 hash."""
        stopwords = {
            "a", "an", "the", "is", "are", "in", "on", "at", "of", "for",
            "to", "and", "or", "can", "i", "you", "it", "where", "what", "do",
            "how", "why", "who", "have", "has", "had", "be", "been", "being"
        }
        words = re.findall(r"\w+", text.lower())

        # 1. Base vector with small deterministic background noise
        seed_bytes = hashlib.sha256(text.encode("utf-8")).digest()
        seed_int = int.from_bytes(seed_bytes[:8], "big")
        rng = random.Random(seed_int)
        vector = [rng.gauss(0, 0.001) for _ in range(self.dimension)]

        # 2. Extract words, apply root stemming, and project tokens into vector dimensions
        for w in words:
            is_stop = w in stopwords
            weight = 0.05 if is_stop else 3.0
            stems = [w]
            if w.endswith("ing") and len(w) > 5:
                stems.append(w[:-3])
            elif w.endswith("ed") and len(w) > 4:
                stems.append(w[:-2])
            elif w.endswith("s") and len(w) > 3:
                stems.append(w[:-1])
            if len(w) >= 4:
                stems.append(w[:4])

            for stem in set(stems):
                for salt in (b"_1", b"_2", b"_3"):
                    h = int.from_bytes(hashlib.md5(stem.encode("utf-8") + salt).digest()[:4], "big")
                    idx = h % self.dimension
                    vector[idx] += weight

        normalized = self.normalize_l2(vector)
        self.validate_dimension(normalized)
        return normalized

    async def embed_query(self, text: str) -> List[float]:
        """Embed a single query string."""
        return self._generate_vector(text)

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Batch embed a list of documents."""
        return [self._generate_vector(t) for t in texts]
