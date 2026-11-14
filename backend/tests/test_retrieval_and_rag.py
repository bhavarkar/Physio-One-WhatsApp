"""Tests for Semantic Retrieval, RAG Context Staging, and Knowledge Tool."""
import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.knowledge_service import KnowledgeService
from app.services.retrieval_service import RetrievalService
from app.tools.clinical.knowledge import SearchClinicKnowledgeTool
from app.tools.base import ToolExecutionContext


@pytest.mark.asyncio
async def test_semantic_retrieval_and_filtering(async_session: AsyncSession):
    kb = await KnowledgeService.create_knowledge_base(
        db=async_session,
        name=f"Retrieval KB {uuid.uuid4().hex[:6]}",
    )

    doc1_content = (
        b"Physio One Clinic Operating Hours and Policies.\n\n"
        b"The clinic is open from 09:00 AM to 08:00 PM every Monday through Saturday.\n\n"
        b"Physio One is strictly closed on Sundays. No appointments can be booked on Sundays."
    )
    doc1 = await KnowledgeService.ingest_document(
        db=async_session,
        knowledge_base_id=kb.id,
        title="Operating Hours & Sunday Rules",
        filename="hours.txt",
        content=doc1_content,
    )

    doc2_content = (
        b"Physical Therapy Treatment Pricing.\n\n"
        b"Initial physiotherapy assessment costs Rs. 800.\n\n"
        b"Subsequent follow-up sessions are Rs. 600 each."
    )
    doc2 = await KnowledgeService.ingest_document(
        db=async_session,
        knowledge_base_id=kb.id,
        title="Pricing Guide",
        filename="pricing.txt",
        content=doc2_content,
    )

    # 1. Search relevant query
    results = await RetrievalService.search_chunks(
        db=async_session,
        query="Are you open on Sunday?",
        knowledge_base_id=kb.id,
        top_k=2,
        similarity_threshold=0.30,
    )
    assert len(results) > 0
    top_result = results[0]
    assert "Sunday" in top_result["chunk_text"]
    assert top_result["document_title"] == "Operating Hours & Sunday Rules"
    assert top_result["similarity_score"] > 0.30

    # 2. Archive doc1 and verify exclusion
    await KnowledgeService.archive_document(async_session, doc1.id)
    archived_results = await RetrievalService.search_chunks(
        db=async_session,
        query="Are you open on Sunday?",
        knowledge_base_id=kb.id,
        top_k=2,
        similarity_threshold=0.30,
    )
    # Archived doc1 chunks must not be returned
    assert not any(r["document_id"] == str(doc1.id) for r in archived_results)


@pytest.mark.asyncio
async def test_rag_context_builder(async_session: AsyncSession):
    kb = await KnowledgeService.create_knowledge_base(
        db=async_session,
        name=f"RAG Context KB {uuid.uuid4().hex[:6]}",
    )
    doc_content = (
        b"Cervical spondylosis treatment involves isometric neck exercises, "
        b"manual traction, and ergonomic posture adjustments."
    )
    await KnowledgeService.ingest_document(
        db=async_session,
        knowledge_base_id=kb.id,
        title="Neck Pain Protocols",
        filename="neck_pain.txt",
        content=doc_content,
    )

    # Test builder
    rag_ctx = await RetrievalService.build_rag_context(
        db=async_session,
        query="neck exercises for spondylosis",
        knowledge_base_id=kb.id,
        top_k=2,
        similarity_threshold=0.50,
    )
    assert rag_ctx["has_context"] is True
    assert rag_ctx["insufficient_context"] is False
    assert "APPROVED CLINIC KNOWLEDGE BASE CONTEXT" in rag_ctx["context_text"]
    assert "Neck Pain Protocols" in rag_ctx["context_text"]
    assert len(rag_ctx["sources"]) >= 1


@pytest.mark.asyncio
async def test_knowledge_retrieval_tool_execution(async_session: AsyncSession):
    kb = await KnowledgeService.create_knowledge_base(
        db=async_session,
        name=f"Tool KB {uuid.uuid4().hex[:6]}",
    )
    await KnowledgeService.ingest_document(
        db=async_session,
        knowledge_base_id=kb.id,
        title="Parking Information",
        filename="parking.txt",
        content=b"Dedicated clinic parking is available at the rear entrance of Physio One Clinic.",
    )

    tool = SearchClinicKnowledgeTool()
    context = ToolExecutionContext(
        session_id=str(uuid.uuid4()),
        agent_id=uuid.uuid4(),
        caller_permissions=["knowledge:read"],
    )

    # Execute search
    out = await tool.execute(
        arguments={"query": "Where can I park?", "knowledge_base_id": str(kb.id), "top_k": 2},
        context=context,
        db=async_session,
    )
    assert out["success"] is True
    assert out["found"] is True
    assert out["count"] >= 1
    assert any("rear entrance" in s["content"] for s in out["snippets"])
