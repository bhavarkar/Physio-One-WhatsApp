"""Tests for Knowledge Base and Ingestion Service."""
import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.memory import KnowledgeBase, KnowledgeDocument, KnowledgeChunk
from app.services.knowledge_service import KnowledgeService


@pytest.mark.asyncio
async def test_knowledge_base_crud(async_session: AsyncSession):
    # 1. Create
    kb = await KnowledgeService.create_knowledge_base(
        db=async_session,
        name="Test Clinic KB",
        description="Test description",
        embedding_model="text-embedding-3-small",
        vector_dimension=1536,
    )
    assert kb.id is not None
    assert kb.name == "Test Clinic KB"
    assert kb.is_active is True

    # 2. Duplicate name rejection
    with pytest.raises(ValueError, match="already exists"):
        await KnowledgeService.create_knowledge_base(
            db=async_session,
            name="Test Clinic KB",
        )

    # 3. List
    kbs = await KnowledgeService.list_knowledge_bases(async_session)
    assert any(k.id == kb.id for k in kbs)

    # 4. Update
    updated = await KnowledgeService.update_knowledge_base(
        db=async_session,
        kb_id=kb.id,
        description="Updated description",
        is_active=False,
    )
    assert updated.description == "Updated description"
    assert updated.is_active is False

    # 5. Delete
    deleted = await KnowledgeService.delete_knowledge_base(async_session, kb.id)
    assert deleted is True
    assert (await KnowledgeService.get_knowledge_base(async_session, kb.id)) is None


@pytest.mark.asyncio
async def test_document_ingestion_and_lifecycle(async_session: AsyncSession):
    # Create KB
    kb = await KnowledgeService.create_knowledge_base(
        db=async_session,
        name=f"Ingestion KB {uuid.uuid4().hex[:6]}",
    )

    doc_content = (
        b"# Physio One Services\n\n"
        b"We provide sports injury rehabilitation, dry needling, and posture correction.\n\n"
        b"Working hours are 09:00 AM to 08:00 PM, Monday through Saturday.\n\n"
        b"The clinic is closed on Sundays."
    )

    # Ingest document
    doc = await KnowledgeService.ingest_document(
        db=async_session,
        knowledge_base_id=kb.id,
        title="Services & Timings",
        filename="services.md",
        content=doc_content,
        chunk_size=120,
        chunk_overlap=20,
    )

    assert doc.status == "ready"
    assert doc.chunk_count > 0
    assert doc.version == 1

    # Verify chunks persisted in database
    chunks_stmt = select(KnowledgeChunk).where(KnowledgeChunk.document_id == doc.id)
    chunks = list((await async_session.execute(chunks_stmt)).scalars().all())
    assert len(chunks) == doc.chunk_count
    for chk in chunks:
        assert chk.embedding is not None
        assert len(chk.embedding) == 1536
        assert chk.chunk_text

    # Duplicate document rejection
    with pytest.raises(ValueError, match="Duplicate document detected"):
        await KnowledgeService.ingest_document(
            db=async_session,
            knowledge_base_id=kb.id,
            title="Duplicate Services",
            filename="services_copy.md",
            content=doc_content,
        )

    # Reprocess document
    reprocessed = await KnowledgeService.reprocess_document(
        db=async_session,
        doc_id=doc.id,
        chunk_size=200,
        chunk_overlap=30,
    )
    assert reprocessed.version == 2
    assert reprocessed.status == "ready"

    # Archive document
    archived = await KnowledgeService.archive_document(async_session, doc.id)
    assert archived.status == "archived"

    # Delete document
    deleted = await KnowledgeService.delete_document(async_session, doc.id)
    assert deleted is True
