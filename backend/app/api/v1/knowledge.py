"""Knowledge Base, Ingestion, Semantic Retrieval, and Patient Memory API Endpoints.

Single Organization Edition: Physio One Clinic.
RBAC:
- View KB, Documents: require_role(Owner, Admin, Operator, Viewer)
- Ingest, Reprocess, Archive, Delete KB/Documents: require_role(Owner, Admin)
- Search & Test Retrieval: require_role(Owner, Admin, Operator)
- Patient Memory read/write/delete: require_role(Owner, Admin, Operator)
"""
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_role, get_current_user
from app.core.rbac import ROLE_OWNER, ROLE_ADMIN, ROLE_OPERATOR, ROLE_VIEWER
from app.models.user import User
from app.schemas.knowledge import (
    KnowledgeBaseResponse,
    KnowledgeBaseCreate,
    KnowledgeBaseUpdate,
    KnowledgeDocumentResponse,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    KnowledgeSnippetResponse,
    ConversationMemoryCreate,
    ConversationMemoryResponse,
)
from app.services.knowledge_service import KnowledgeService
from app.services.retrieval_service import RetrievalService
from app.services.memory_service import MemoryService
from app.services.document_processor import DocumentProcessingError

router = APIRouter(prefix="/knowledge", tags=["Knowledge Base & RAG"])


# ------------------------------------------------------------------------------
# Knowledge Bases
# ------------------------------------------------------------------------------
@router.get("/bases", response_model=List[KnowledgeBaseResponse])
async def list_knowledge_bases(
    active_only: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN, ROLE_OPERATOR, ROLE_VIEWER)),
):
    """List all knowledge base collections."""
    kbs = await KnowledgeService.list_knowledge_bases(db, active_only=active_only)
    return [
        KnowledgeBaseResponse(
            id=kb.id,
            name=kb.name,
            description=kb.description,
            embedding_model=kb.embedding_model,
            vector_dimension=kb.vector_dimension,
            is_active=kb.is_active,
            created_by_id=kb.created_by_id,
            document_count=len(kb.documents) if kb.documents else 0,
            created_at=kb.created_at,
            updated_at=kb.updated_at,
        )
        for kb in kbs
    ]


@router.post("/bases", response_model=KnowledgeBaseResponse, status_code=status.HTTP_201_CREATED)
async def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN)),
):
    """Create a new knowledge base collection."""
    try:
        kb = await KnowledgeService.create_knowledge_base(
            db=db,
            name=payload.name,
            description=payload.description,
            embedding_model=payload.embedding_model,
            vector_dimension=payload.vector_dimension,
            created_by_id=user.id,
        )
        return KnowledgeBaseResponse(
            id=kb.id,
            name=kb.name,
            description=kb.description,
            embedding_model=kb.embedding_model,
            vector_dimension=kb.vector_dimension,
            is_active=kb.is_active,
            created_by_id=kb.created_by_id,
            document_count=0,
            created_at=kb.created_at,
            updated_at=kb.updated_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/bases/{kb_id}", response_model=KnowledgeBaseResponse)
async def get_knowledge_base(
    kb_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN, ROLE_OPERATOR, ROLE_VIEWER)),
):
    """Get single knowledge base details."""
    kb = await KnowledgeService.get_knowledge_base(db, kb_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found.")
    return KnowledgeBaseResponse(
        id=kb.id,
        name=kb.name,
        description=kb.description,
        embedding_model=kb.embedding_model,
        vector_dimension=kb.vector_dimension,
        is_active=kb.is_active,
        created_by_id=kb.created_by_id,
        document_count=len(kb.documents) if kb.documents else 0,
        created_at=kb.created_at,
        updated_at=kb.updated_at,
    )


@router.patch("/bases/{kb_id}", response_model=KnowledgeBaseResponse)
async def update_knowledge_base(
    kb_id: uuid.UUID,
    payload: KnowledgeBaseUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN)),
):
    """Update knowledge base details."""
    try:
        kb = await KnowledgeService.update_knowledge_base(
            db=db,
            kb_id=kb_id,
            name=payload.name,
            description=payload.description,
            is_active=payload.is_active,
        )
        if not kb:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found.")
        return KnowledgeBaseResponse(
            id=kb.id,
            name=kb.name,
            description=kb.description,
            embedding_model=kb.embedding_model,
            vector_dimension=kb.vector_dimension,
            is_active=kb.is_active,
            created_by_id=kb.created_by_id,
            document_count=len(kb.documents) if kb.documents else 0,
            created_at=kb.created_at,
            updated_at=kb.updated_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/bases/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge_base(
    kb_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN)),
):
    """Delete knowledge base and all child documents."""
    success = await KnowledgeService.delete_knowledge_base(db, kb_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found.")


# ------------------------------------------------------------------------------
# Documents & Ingestion
# ------------------------------------------------------------------------------
@router.get("/documents", response_model=List[KnowledgeDocumentResponse])
async def list_documents(
    knowledge_base_id: Optional[uuid.UUID] = Query(default=None),
    status_filter: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN, ROLE_OPERATOR, ROLE_VIEWER)),
):
    """List documents with optional filtering by knowledge base or status."""
    docs = await KnowledgeService.list_documents(db, knowledge_base_id=knowledge_base_id, status=status_filter)
    return [KnowledgeDocumentResponse.model_validate(d) for d in docs]


@router.post("/documents/upload", response_model=KnowledgeDocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    knowledge_base_id: uuid.UUID = Form(...),
    title: Optional[str] = Form(default=None),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN)),
):
    """Upload and process a clinical knowledge document (PDF, DOCX, TXT, MD)."""
    try:
        content = await file.read()
        filename = file.filename or "uploaded_document.txt"
        clean_title = (title or filename).strip()

        doc = await KnowledgeService.ingest_document(
            db=db,
            knowledge_base_id=knowledge_base_id,
            title=clean_title,
            filename=filename,
            content=content,
        )
        return KnowledgeDocumentResponse.model_validate(doc)
    except (DocumentProcessingError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Ingestion failed: {str(e)}")


@router.get("/documents/{doc_id}", response_model=KnowledgeDocumentResponse)
async def get_document(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN, ROLE_OPERATOR, ROLE_VIEWER)),
):
    """Get single document details and status."""
    docs = await KnowledgeService.list_documents(db)
    matching = next((d for d in docs if d.id == doc_id), None)
    if not matching:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return KnowledgeDocumentResponse.model_validate(matching)


@router.post("/documents/{doc_id}/reprocess", response_model=KnowledgeDocumentResponse)
async def reprocess_document(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN)),
):
    """Reprocess document: re-chunk, re-embed, and update version number."""
    try:
        doc = await KnowledgeService.reprocess_document(db, doc_id)
        return KnowledgeDocumentResponse.model_validate(doc)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/documents/{doc_id}/archive", response_model=KnowledgeDocumentResponse)
async def archive_document(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN)),
):
    """Archive document to exclude its chunks from semantic search."""
    doc = await KnowledgeService.archive_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return KnowledgeDocumentResponse.model_validate(doc)


@router.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN)),
):
    """Delete document, vector chunks, and physical file."""
    success = await KnowledgeService.delete_document(db, doc_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")


# ------------------------------------------------------------------------------
# Semantic Retrieval & Test Console
# ------------------------------------------------------------------------------
@router.post("/search", response_model=KnowledgeSearchResponse)
@router.post("/test-retrieval", response_model=KnowledgeSearchResponse)
async def search_knowledge(
    payload: KnowledgeSearchRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN, ROLE_OPERATOR)),
):
    """Test semantic retrieval over active documents."""
    import time
    start = time.perf_counter()
    chunks = await RetrievalService.search_chunks(
        db=db,
        query=payload.query,
        knowledge_base_id=payload.knowledge_base_id,
        top_k=payload.top_k,
        similarity_threshold=payload.similarity_threshold,
    )
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    snippets = [KnowledgeSnippetResponse(**c) for c in chunks]
    return KnowledgeSearchResponse(
        query=payload.query,
        count=len(snippets),
        snippets=snippets,
        latency_ms=elapsed_ms,
    )


# ------------------------------------------------------------------------------
# Patient Memory (Isolated per contact_id)
# ------------------------------------------------------------------------------
@router.get("/memories/{contact_id}", response_model=List[ConversationMemoryResponse])
async def list_contact_memories(
    contact_id: uuid.UUID,
    active_only: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN, ROLE_OPERATOR)),
):
    """Retrieve isolated memories for a specific patient contact."""
    memories = await MemoryService.list_contact_memories(db, contact_id, active_only=active_only)
    return [ConversationMemoryResponse.model_validate(m) for m in memories]


@router.post("/memories", response_model=ConversationMemoryResponse, status_code=status.HTTP_201_CREATED)
async def create_contact_memory(
    payload: ConversationMemoryCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN, ROLE_OPERATOR)),
):
    """Store a durable patient preference or note."""
    try:
        mem = await MemoryService.store_contact_memory(
            db=db,
            contact_id=payload.contact_id,
            content=payload.content,
            memory_type=payload.memory_type,
            conversation_id=payload.conversation_id,
            confidence_score=payload.confidence_score,
        )
        return ConversationMemoryResponse.model_validate(mem)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact_memory(
    memory_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(ROLE_OWNER, ROLE_ADMIN)),
):
    """Delete a patient memory."""
    success = await MemoryService.delete_contact_memory(db, memory_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory record not found.")
