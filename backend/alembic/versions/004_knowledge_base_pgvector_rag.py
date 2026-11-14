"""add knowledge base pgvector rag, document status, conversation memory tracking, and retrieval logs

Revision ID: 004_knowledge_base_pgvector_rag
Revises: 003_ai_agent_sessions_and_usage
Create Date: 2026-11-14 19:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "004_knowledge_base_pgvector_rag"
down_revision: Union[str, None] = "003_ai_agent_sessions_and_usage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # 1. Alter knowledge_bases
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "embedding_model",
            sa.String(length=100),
            nullable=False,
            server_default=sa.text("'text-embedding-3-small'"),
        ),
    )
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "vector_dimension",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1536"),
        ),
    )
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "created_by_id",
            postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # 2. Alter knowledge_documents
    op.add_column(
        "knowledge_documents",
        sa.Column(
            "file_size_bytes",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column(
            "source_hash",
            sa.String(length=64),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_knowledge_documents_source_hash",
        "knowledge_documents",
        ["source_hash"],
        unique=False,
    )
    op.add_column(
        "knowledge_documents",
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column(
            "error_message",
            sa.Text(),
            nullable=True,
        ),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # 3. Alter knowledge_chunks
    op.add_column(
        "knowledge_chunks",
        sa.Column(
            "chunk_metadata",
            postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON(),
            nullable=True,
        ),
    )

    # 4. Alter conversation_memory
    op.add_column(
        "conversation_memory",
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_conversation_memory_conv_id",
        "conversation_memory",
        ["conversation_id"],
        unique=False,
    )
    op.add_column(
        "conversation_memory",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "conversation_memory",
        sa.Column(
            "source_message_id",
            postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36),
            sa.ForeignKey("whatsapp_messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "conversation_memory",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # 5. Create ai_retrieval_logs
    op.create_table(
        "ai_retrieval_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()") if is_postgres else None,
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36),
            sa.ForeignKey("ai_agent_sessions.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column(
            "knowledge_base_id",
            postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36),
            sa.ForeignKey("knowledge_bases.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("chunks_retrieved", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "similarity_scores",
            postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON(),
            nullable=True,
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # 6. Alter ai_agents
    op.add_column(
        "ai_agents",
        sa.Column(
            "knowledge_base_id",
            postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36),
            sa.ForeignKey("knowledge_bases.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "ai_agents",
        sa.Column(
            "rag_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "ai_agents",
        sa.Column(
            "rag_similarity_threshold",
            sa.Numeric(precision=3, scale=2),
            nullable=False,
            server_default=sa.text("0.70"),
        ),
    )
    op.add_column(
        "ai_agents",
        sa.Column(
            "rag_top_k",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("3"),
        ),
    )

    # 7. Add pgvector HNSW indexes on PostgreSQL if pgvector is available
    if is_postgres:
        op.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_extension WHERE extname = 'vector'
                ) THEN
                    CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_embedding_hnsw 
                    ON knowledge_chunks 
                    USING hnsw (embedding vector_cosine_ops)
                    WITH (m = 16, ef_construction = 64);

                    CREATE INDEX IF NOT EXISTS idx_conversation_memory_embedding_hnsw 
                    ON conversation_memory 
                    USING hnsw (embedding vector_cosine_ops)
                    WITH (m = 16, ef_construction = 64);
                END IF;
            END $$;
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute("DROP INDEX IF EXISTS idx_knowledge_chunks_embedding_hnsw;")
        op.execute("DROP INDEX IF EXISTS idx_conversation_memory_embedding_hnsw;")

    op.drop_column("ai_agents", "rag_top_k")
    op.drop_column("ai_agents", "rag_similarity_threshold")
    op.drop_column("ai_agents", "rag_enabled")
    op.drop_column("ai_agents", "knowledge_base_id")

    op.drop_table("ai_retrieval_logs")

    op.drop_column("conversation_memory", "updated_at")
    op.drop_column("conversation_memory", "source_message_id")
    op.drop_column("conversation_memory", "is_active")
    op.drop_index("idx_conversation_memory_conv_id", table_name="conversation_memory")
    op.drop_column("conversation_memory", "conversation_id")

    op.drop_column("knowledge_chunks", "chunk_metadata")

    op.drop_column("knowledge_documents", "updated_at")
    op.drop_column("knowledge_documents", "error_message")
    op.drop_column("knowledge_documents", "status")
    op.drop_column("knowledge_documents", "version")
    op.drop_index("idx_knowledge_documents_source_hash", table_name="knowledge_documents")
    op.drop_column("knowledge_documents", "source_hash")
    op.drop_column("knowledge_documents", "file_size_bytes")

    op.drop_column("knowledge_bases", "created_by_id")
    op.drop_column("knowledge_bases", "vector_dimension")
    op.drop_column("knowledge_bases", "embedding_model")
