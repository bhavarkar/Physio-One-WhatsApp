"""Database Connection and Session Management

Configures SQLAlchemy 2.0 async and sync engines and sessionmakers.
"""
from typing import AsyncGenerator
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB, UUID
from pgvector.sqlalchemy import Vector

from app.core.config import settings


# SQLite type compilations for PostgreSQL types during local development / testing
@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


@compiles(UUID, "sqlite")
def compile_uuid_sqlite(type_, compiler, **kw):
    return "CHAR(36)"


@compiles(Vector, "sqlite")
def compile_vector_sqlite(type_, compiler, **kw):
    return "TEXT"


# Declarative Base for all SQLAlchemy models
class Base(DeclarativeBase):
    pass


# Async Engine & Session (for FastAPI and Async Workers)
is_async_sqlite = settings.async_database_url.startswith("sqlite")
async_engine_kwargs = {
    "echo": (settings.ENVIRONMENT == "development" and settings.LOG_LEVEL == "DEBUG"),
    "future": True,
}
if not is_async_sqlite:
    async_engine_kwargs.update({
        "pool_pre_ping": True,
        "pool_size": 10,
        "max_overflow": 20,
    })

async_engine = create_async_engine(
    settings.async_database_url,
    **async_engine_kwargs,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


# Sync Engine & Session (for Alembic migrations and sync scripts)
is_sync_sqlite = settings.sync_database_url.startswith("sqlite")
sync_engine_kwargs = {
    "echo": False,
    "future": True,
}
if not is_sync_sqlite:
    sync_engine_kwargs["pool_pre_ping"] = True

sync_engine = create_engine(
    settings.sync_database_url,
    **sync_engine_kwargs,
)

SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for yielding an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

