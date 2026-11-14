"""Pydantic schemas for Knowledge Bases, Documents, Retrieval, and Conversation Memory.

Single Organization Edition: Physio One Clinic.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
import uuid
from pydantic import BaseModel, Field


# ------------------------------------------------------------------------------
# Knowledge Base Schemas
# ------------------------------------------------------------------------------
class KnowledgeBaseResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    embedding_model: str
    vector_dimension: int
    is_active: bool
    created_by_id: Optional[uuid.UUID] = None
    document_count: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: Optional[str] = None
    embedding_model: str = Field(default="text-embedding-3-small", max_length=100)
    vector_dimension: int = Field(default=1536)


class KnowledgeBaseUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    description: Optional[str] = None
    is_active: Optional[bool] = None


# ------------------------------------------------------------------------------
# Document Schemas
# ------------------------------------------------------------------------------
class KnowledgeDocumentResponse(BaseModel):
    id: uuid.UUID
    knowledge_base_id: uuid.UUID
    title: str
    file_type: str
    file_url: str
    file_size_bytes: int
    source_hash: Optional[str] = None
    chunk_count: int
    version: int
    status: str  # pending, processing, ready, failed, archived
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class KnowledgeChunkResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    chunk_text: str
    chunk_metadata: Optional[Dict[str, Any]] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ------------------------------------------------------------------------------
# Semantic Retrieval & Search Schemas
# ------------------------------------------------------------------------------
class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    knowledge_base_id: Optional[uuid.UUID] = None
    top_k: int = Field(default=3, ge=1, le=10)
    similarity_threshold: float = Field(default=0.30, ge=0.0, le=1.0)


class KnowledgeSnippetResponse(BaseModel):
    chunk_id: str
    document_id: str
    document_title: str
    document_version: int
    knowledge_base_id: str
    knowledge_base_name: str
    chunk_index: int
    chunk_text: str
    similarity_score: float
    metadata: Dict[str, Any] = {}


class KnowledgeSearchResponse(BaseModel):
    query: str
    count: int
    snippets: List[KnowledgeSnippetResponse]
    latency_ms: int = 0


# ------------------------------------------------------------------------------
# Patient Memory Schemas
# ------------------------------------------------------------------------------
class ConversationMemoryCreate(BaseModel):
    contact_id: uuid.UUID
    content: str = Field(min_length=2, max_length=2000)
    memory_type: str = Field(default="preference", max_length=50)
    conversation_id: Optional[uuid.UUID] = None
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)


class ConversationMemoryResponse(BaseModel):
    id: uuid.UUID
    contact_id: uuid.UUID
    conversation_id: Optional[uuid.UUID] = None
    memory_type: str
    content: str
    confidence_score: float
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
