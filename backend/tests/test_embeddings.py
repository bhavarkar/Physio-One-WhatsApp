"""Tests for Embedding Provider Abstraction and Deterministic Implementation."""
import math
import pytest
from unittest.mock import patch, MagicMock

from app.llm.embeddings.base import (
    BaseEmbeddingProvider,
    EmbeddingDimensionMismatchError,
    EmbeddingError,
)
from app.llm.embeddings.deterministic import DeterministicEmbeddingProvider
from app.llm.embeddings.openai import OpenAIEmbeddingProvider
from app.llm.embeddings import get_embedding_provider
from app.llm.errors import LLMAuthenticationError, LLMRateLimitError, LLMTimeoutError


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    return sum(a * b for a, b in zip(v1, v2))


@pytest.mark.asyncio
async def test_deterministic_embedding_properties():
    provider = DeterministicEmbeddingProvider(dimension=1536)
    
    text1 = "Physio One clinic hours are Monday to Saturday 9 AM to 8 PM."
    text2 = "Physio One clinic hours are Monday to Saturday 9 AM to 8 PM."
    text3 = "Spinal rehabilitation and physiotherapy exercises for lower back pain."

    v1 = await provider.embed_query(text1)
    v2 = await provider.embed_query(text2)
    v3 = await provider.embed_query(text3)

    assert len(v1) == 1536
    assert len(v2) == 1536
    assert len(v3) == 1536

    # Verify unit vector norm
    norm1 = math.sqrt(sum(x * x for x in v1))
    assert math.isclose(norm1, 1.0, rel_tol=1e-5)

    # Identical texts yield identical vectors (similarity = 1.0)
    sim_identical = cosine_similarity(v1, v2)
    assert math.isclose(sim_identical, 1.0, rel_tol=1e-5)

    # Different texts yield distinct vectors
    sim_diff = cosine_similarity(v1, v3)
    assert sim_diff < 0.99


@pytest.mark.asyncio
async def test_batch_embedding():
    provider = DeterministicEmbeddingProvider(dimension=1536)
    texts = [
        "First document text.",
        "Second document text.",
        "Third document text.",
    ]
    batch_vectors = await provider.embed_documents(texts)
    assert len(batch_vectors) == 3
    for vec in batch_vectors:
        assert len(vec) == 1536
        assert math.isclose(math.sqrt(sum(x * x for x in vec)), 1.0, rel_tol=1e-5)


@pytest.mark.asyncio
async def test_dimension_mismatch_error():
    provider = DeterministicEmbeddingProvider(dimension=1536)
    with pytest.raises(EmbeddingDimensionMismatchError):
        provider.validate_dimension([0.1] * 512)


@pytest.mark.asyncio
async def test_openai_embedding_success():
    provider = OpenAIEmbeddingProvider(api_key="sk-test-key", dimension=1536)

    dummy_response = {
        "data": [
            {"index": 0, "embedding": [0.01] * 1536}
        ]
    }

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = dummy_response
        mock_post.return_value = mock_resp

        vec = await provider.embed_query("Hello clinic")
        assert len(vec) == 1536
        assert math.isclose(math.sqrt(sum(x * x for x in vec)), 1.0, rel_tol=1e-5)


@pytest.mark.asyncio
async def test_openai_embedding_error_normalization():
    provider = OpenAIEmbeddingProvider(api_key="sk-test-key", dimension=1536)

    with patch("httpx.AsyncClient.post") as mock_post:
        # Test 401
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"
        mock_post.return_value = mock_resp
        with pytest.raises(LLMAuthenticationError):
            await provider.embed_query("Test")

        # Test 429
        mock_resp.status_code = 429
        mock_resp.text = "Rate limit"
        with pytest.raises(LLMRateLimitError):
            await provider.embed_query("Test")


def test_factory_fallback():
    provider = get_embedding_provider(provider_type="unknown")
    assert isinstance(provider, DeterministicEmbeddingProvider)


def test_production_guardrail_rejects_mock_embeddings(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(EmbeddingError) as exc_info:
        get_embedding_provider(provider_type="deterministic")
    assert "strictly disallowed in production" in str(exc_info.value)
