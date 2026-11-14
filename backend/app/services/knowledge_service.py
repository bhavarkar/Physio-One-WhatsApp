"""Knowledge Base and Document Management Service.

Single Organization Edition: Physio One Clinic.
Orchestrates document ingestion, validation, vectorization, reprocessing, and lifecycle management.
"""
import os
import uuid
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload

from app.models.memory import KnowledgeBase, KnowledgeDocument, KnowledgeChunk
from app.services.document_processor import DocumentProcessor, DocumentProcessingError
from app.llm.embeddings import get_embedding_provider


class KnowledgeService:
    """Service for managing clinic knowledge bases, documents, and vector chunking."""

    STORAGE_DIR = os.getenv("KNOWLEDGE_STORAGE_PATH", "./storage/knowledge")

    @classmethod
    def _ensure_storage_dir(cls, kb_id: uuid.UUID) -> str:
        """Create sanitized storage directory for a knowledge base."""
        target_dir = os.path.abspath(os.path.join(cls.STORAGE_DIR, str(kb_id)))
        os.makedirs(target_dir, exist_ok=True)
        return target_dir

    @classmethod
    async def create_knowledge_base(
        cls,
        db: AsyncSession,
        name: str,
        description: Optional[str] = None,
        embedding_model: str = "text-embedding-3-small",
        vector_dimension: int = 1536,
        created_by_id: Optional[uuid.UUID] = None,
    ) -> KnowledgeBase:
        """Create a new knowledge base container."""
        # Check uniqueness of name
        existing = await db.execute(select(KnowledgeBase).where(KnowledgeBase.name == name.strip()))
        if existing.scalar_one_or_none():
            raise ValueError(f"Knowledge base with name '{name}' already exists.")

        kb = KnowledgeBase(
            name=name.strip(),
            description=description.strip() if description else None,
            embedding_model=embedding_model,
            vector_dimension=vector_dimension,
            created_by_id=created_by_id,
            is_active=True,
        )
        db.add(kb)
        await db.commit()
        return await cls.get_knowledge_base(db, kb.id)

    @classmethod
    async def list_knowledge_bases(cls, db: AsyncSession, active_only: bool = False) -> List[KnowledgeBase]:
        """List knowledge bases with document counts."""
        stmt = select(KnowledgeBase).options(selectinload(KnowledgeBase.documents))
        if active_only:
            stmt = stmt.where(KnowledgeBase.is_active == True)
        stmt = stmt.order_by(KnowledgeBase.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    async def get_knowledge_base(cls, db: AsyncSession, kb_id: uuid.UUID) -> Optional[KnowledgeBase]:
        """Get knowledge base with related documents."""
        stmt = select(KnowledgeBase).where(KnowledgeBase.id == kb_id).options(selectinload(KnowledgeBase.documents))
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @classmethod
    async def update_knowledge_base(
        cls,
        db: AsyncSession,
        kb_id: uuid.UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[KnowledgeBase]:
        """Update knowledge base details."""
        kb = await db.get(KnowledgeBase, kb_id)
        if not kb:
            return None

        if name is not None:
            clean_name = name.strip()
            # Check for conflict
            conflict = await db.execute(
                select(KnowledgeBase).where(and_(KnowledgeBase.name == clean_name, KnowledgeBase.id != kb_id))
            )
            if conflict.scalar_one_or_none():
                raise ValueError(f"Knowledge base with name '{clean_name}' already exists.")
            kb.name = clean_name

        if description is not None:
            kb.description = description.strip() if description else None

        if is_active is not None:
            kb.is_active = is_active

        await db.commit()
        return await cls.get_knowledge_base(db, kb_id)

    @classmethod
    async def delete_knowledge_base(cls, db: AsyncSession, kb_id: uuid.UUID) -> bool:
        """Delete knowledge base, cascade chunks, and remove stored files."""
        kb = await db.get(KnowledgeBase, kb_id)
        if not kb:
            return False

        await db.delete(kb)
        await db.commit()
        return True

    @classmethod
    async def ingest_document(
        cls,
        db: AsyncSession,
        knowledge_base_id: uuid.UUID,
        title: str,
        filename: str,
        content: bytes,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> KnowledgeDocument:
        """Process, validate, vectorize, and persist a knowledge document."""
        kb = await db.get(KnowledgeBase, knowledge_base_id)
        if not kb:
            raise ValueError(f"Knowledge base '{knowledge_base_id}' not found.")

        # 1. Validate file content and size
        ext, source_hash = DocumentProcessor.validate_file(filename, content)

        # Check for duplicate document in the same knowledge base
        dup_stmt = select(KnowledgeDocument).where(
            and_(
                KnowledgeDocument.knowledge_base_id == knowledge_base_id,
                KnowledgeDocument.source_hash == source_hash,
                KnowledgeDocument.status != "archived",
            )
        )
        existing_dup = (await db.execute(dup_stmt)).scalar_one_or_none()
        if existing_dup:
            raise ValueError(
                f"Duplicate document detected: '{existing_dup.title}' already uploaded with identical content."
            )

        # 2. Save physical file securely (path traversal prevention)
        storage_dir = cls._ensure_storage_dir(knowledge_base_id)
        doc_uuid = uuid.uuid4()
        safe_filename = f"{doc_uuid}_{os.path.basename(filename)}"
        file_path = os.path.join(storage_dir, safe_filename)
        with open(file_path, "wb") as f:
            f.write(content)

        # 3. Create document record in "processing" state
        clean_title = title.strip() or os.path.splitext(os.path.basename(filename))[0]
        doc = KnowledgeDocument(
            id=doc_uuid,
            knowledge_base_id=knowledge_base_id,
            title=clean_title,
            file_type=ext,
            file_url=file_path,
            file_size_bytes=len(content),
            source_hash=source_hash,
            version=1,
            status="processing",
            chunk_count=0,
            error_message=None,
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)

        try:
            # 4. Extract and normalize text
            raw_text = DocumentProcessor.extract_text(ext, content)
            normalized_text = DocumentProcessor.normalize_text(raw_text)

            # 5. Chunk text
            raw_chunks = DocumentProcessor.chunk_text(
                normalized_text, chunk_size=chunk_size, chunk_overlap=chunk_overlap
            )
            if not raw_chunks:
                raise DocumentProcessingError("No extractable textual content found in document.")

            chunk_texts = [c["text"] for c in raw_chunks]

            # 6. Generate embeddings
            embed_provider = get_embedding_provider(
                model_name=kb.embedding_model, dimension=kb.vector_dimension
            )
            embeddings = await embed_provider.embed_documents(chunk_texts)

            # 7. Persist chunks
            for c_info, emb in zip(raw_chunks, embeddings):
                chunk_rec = KnowledgeChunk(
                    document_id=doc.id,
                    chunk_index=c_info["chunk_index"],
                    chunk_text=c_info["text"],
                    chunk_metadata={
                        "char_count": c_info["char_count"],
                        "word_count": c_info["word_count"],
                        "doc_title": clean_title,
                        "kb_id": str(knowledge_base_id),
                    },
                    embedding=emb,
                )
                db.add(chunk_rec)

            doc.chunk_count = len(raw_chunks)
            doc.status = "ready"
            await db.commit()
            await db.refresh(doc)
            return doc

        except Exception as e:
            # Mark failed status on error
            doc.status = "failed"
            doc.error_message = str(e)
            await db.commit()
            await db.refresh(doc)
            raise

    @classmethod
    async def reprocess_document(
        cls,
        db: AsyncSession,
        doc_id: uuid.UUID,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> KnowledgeDocument:
        """Reprocess an existing document: clear existing chunks, re-extract, and re-embed."""
        stmt = select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id).options(
            selectinload(KnowledgeDocument.chunks), selectinload(KnowledgeDocument.knowledge_base)
        )
        doc = (await db.execute(stmt)).scalar_one_or_none()
        if not doc:
            raise ValueError(f"Document '{doc_id}' not found.")

        if not os.path.exists(doc.file_url):
            raise ValueError(f"Physical file at '{doc.file_url}' is missing.")

        with open(doc.file_url, "rb") as f:
            content = f.read()

        # Remove existing chunks
        for chk in doc.chunks:
            await db.delete(chk)

        doc.status = "processing"
        doc.error_message = None
        doc.version += 1
        await db.commit()

        try:
            raw_text = DocumentProcessor.extract_text(doc.file_type, content)
            normalized_text = DocumentProcessor.normalize_text(raw_text)
            raw_chunks = DocumentProcessor.chunk_text(
                normalized_text, chunk_size=chunk_size, chunk_overlap=chunk_overlap
            )
            if not raw_chunks:
                raise DocumentProcessingError("No extractable text found.")

            chunk_texts = [c["text"] for c in raw_chunks]
            kb = doc.knowledge_base
            embed_provider = get_embedding_provider(
                model_name=kb.embedding_model, dimension=kb.vector_dimension
            )
            embeddings = await embed_provider.embed_documents(chunk_texts)

            for c_info, emb in zip(raw_chunks, embeddings):
                chunk_rec = KnowledgeChunk(
                    document_id=doc.id,
                    chunk_index=c_info["chunk_index"],
                    chunk_text=c_info["text"],
                    chunk_metadata={
                        "char_count": c_info["char_count"],
                        "word_count": c_info["word_count"],
                        "doc_title": doc.title,
                        "kb_id": str(kb.id),
                    },
                    embedding=emb,
                )
                db.add(chunk_rec)

            doc.chunk_count = len(raw_chunks)
            doc.status = "ready"
            await db.commit()
            await db.refresh(doc)
            return doc

        except Exception as e:
            doc.status = "failed"
            doc.error_message = str(e)
            await db.commit()
            await db.refresh(doc)
            raise

    @classmethod
    async def archive_document(cls, db: AsyncSession, doc_id: uuid.UUID) -> Optional[KnowledgeDocument]:
        """Archive a document so its chunks are excluded from retrieval."""
        doc = await db.get(KnowledgeDocument, doc_id)
        if not doc:
            return None
        doc.status = "archived"
        await db.commit()
        await db.refresh(doc)
        return doc

    @classmethod
    async def delete_document(cls, db: AsyncSession, doc_id: uuid.UUID) -> bool:
        """Permanently delete a document, its chunks, and the stored file."""
        doc = await db.get(KnowledgeDocument, doc_id)
        if not doc:
            return False

        file_url = doc.file_url
        await db.delete(doc)
        await db.commit()

        if file_url and os.path.exists(file_url):
            try:
                os.remove(file_url)
            except OSError:
                pass

        return True

    @classmethod
    async def list_documents(
        cls,
        db: AsyncSession,
        knowledge_base_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
    ) -> List[KnowledgeDocument]:
        """List documents filtered by knowledge base or status."""
        stmt = select(KnowledgeDocument)
        if knowledge_base_id:
            stmt = stmt.where(KnowledgeDocument.knowledge_base_id == knowledge_base_id)
        if status:
            stmt = stmt.where(KnowledgeDocument.status == status)
        stmt = stmt.order_by(KnowledgeDocument.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())
