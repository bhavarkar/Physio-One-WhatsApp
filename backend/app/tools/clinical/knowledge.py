"""Clinic Knowledge Retrieval Tool for AI Agents.

Single Organization Edition: Physio One Clinic.
Read-only semantic retrieval tool for authorized clinic policies, hours, treatments, and FAQs.
Integrates with pgvector RetrievalService and enforces agent permission boundaries.
"""
import uuid
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.tools.base import BaseTool, ToolExecutionContext
from app.services.retrieval_service import RetrievalService


class SearchClinicKnowledgeTool(BaseTool):
    """Read-only tool searching approved clinic documents and FAQs."""

    name = "search_clinic_knowledge"
    description = (
        "Search approved Physio One clinic knowledge base for clinic services, treatments, "
        "operating hours, cancellation policies, doctor specializations, and frequently asked questions."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language query describing the clinical or administrative information needed.",
            },
            "knowledge_base_id": {
                "type": "string",
                "description": "Optional UUID of the specific knowledge base collection to search.",
            },
            "top_k": {
                "type": "integer",
                "description": "Maximum number of snippet results to retrieve (1-10, default 3).",
                "minimum": 1,
                "maximum": 10,
            },
        },
        "required": ["query"],
    }
    requires_permission = "knowledge:read"
    is_mutation = False
    is_idempotent = True
    timeout_seconds = 10.0

    async def execute(
        self,
        arguments: Dict[str, Any],
        context: ToolExecutionContext,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """Execute semantic similarity query over approved knowledge chunks."""
        query = arguments.get("query", "").strip()
        if not query:
            return {
                "success": False,
                "error": "Parameter 'query' cannot be empty.",
            }

        kb_id_str = arguments.get("knowledge_base_id")
        kb_uuid: Optional[uuid.UUID] = None
        if kb_id_str:
            try:
                kb_uuid = uuid.UUID(kb_id_str)
            except ValueError:
                return {
                    "success": False,
                    "error": f"Invalid knowledge_base_id format: '{kb_id_str}'. Must be a valid UUID.",
                }

        top_k = min(max(int(arguments.get("top_k", 3)), 1), 10)
        similarity_threshold = float(arguments.get("similarity_threshold", 0.20))
        session_uuid: Optional[uuid.UUID] = None
        if context.session_id:
            session_uuid = context.session_id if isinstance(context.session_id, uuid.UUID) else uuid.UUID(str(context.session_id))

        chunks = await RetrievalService.search_chunks(
            db=db,
            query=query,
            knowledge_base_id=kb_uuid,
            top_k=top_k,
            similarity_threshold=similarity_threshold,
            session_id=session_uuid,
        )

        if not chunks:
            return {
                "success": True,
                "found": False,
                "insufficient_context": True,
                "message": "No relevant clinic documentation or approved FAQs found for this query.",
                "snippets": [],
            }

        snippets = [
            {
                "document_title": c["document_title"],
                "document_version": c["document_version"],
                "chunk_index": c["chunk_index"],
                "similarity_score": c["similarity_score"],
                "content": c["chunk_text"],
            }
            for c in chunks
        ]

        return {
            "success": True,
            "found": True,
            "insufficient_context": False,
            "query": query,
            "count": len(snippets),
            "snippets": snippets,
        }
