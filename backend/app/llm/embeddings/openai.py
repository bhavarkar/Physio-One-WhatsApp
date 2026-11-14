"""OpenAI Embeddings Provider.

Single Organization Edition: Physio One Clinic.
Embeds text via OpenAI API (text-embedding-3-small, text-embedding-3-large, text-embedding-ada-002).
"""
from typing import List, Optional
import httpx

from app.llm.embeddings.base import BaseEmbeddingProvider, EmbeddingError
from app.llm.errors import LLMAuthenticationError, LLMRateLimitError, LLMTimeoutError


class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    """OpenAI API embeddings adapter with batch processing and error normalization."""

    def __init__(
        self,
        api_key: str,
        model_name: str = "text-embedding-3-small",
        dimension: int = 1536,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 30.0,
    ):
        super().__init__(model_name=model_name, dimension=dimension)
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def _get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def _call_api(self, input_data: List[str]) -> List[List[float]]:
        url = f"{self.base_url}/embeddings"
        payload = {
            "model": self.model_name,
            "input": input_data,
            "dimensions": self.dimension,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.post(url, headers=self._get_headers(), json=payload)

            if resp.status_code == 401:
                raise LLMAuthenticationError("Invalid or missing OpenAI API key for embeddings.")
            elif resp.status_code == 429:
                raise LLMRateLimitError("OpenAI embeddings rate limit exceeded.")
            elif resp.status_code >= 500:
                raise EmbeddingError(f"OpenAI service error: HTTP {resp.status_code}")
            elif resp.status_code != 200:
                raise EmbeddingError(f"OpenAI embeddings call failed with status {resp.status_code}: {resp.text}")

            data = resp.json()
            embeddings_data = data.get("data", [])
            # Sort by index to preserve input order
            embeddings_data.sort(key=lambda x: x.get("index", 0))

            results = []
            for item in embeddings_data:
                vec = item.get("embedding", [])
                self.validate_dimension(vec)
                results.append(self.normalize_l2(vec))

            return results

        except httpx.TimeoutException as e:
            raise LLMTimeoutError(f"OpenAI embeddings request timed out: {e}") from e
        except (LLMAuthenticationError, LLMRateLimitError, LLMTimeoutError, EmbeddingError):
            raise
        except Exception as e:
            raise EmbeddingError(f"Unexpected error in OpenAI embedding generation: {e}") from e

    async def embed_query(self, text: str) -> List[float]:
        results = await self._call_api([text])
        return results[0]

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        # Process in batches of 100 to avoid payload size limits
        batch_size = 100
        all_embeddings: List[List[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            batch_results = await self._call_api(batch)
            all_embeddings.extend(batch_results)
        return all_embeddings
