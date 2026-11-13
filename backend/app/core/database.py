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

from app.core.config import settings


# Declarative Base for all SQLAlchemy models
class Base(DeclarativeBase):
    pass


# Async Engine & Session (for FastAPI and Async Workers)
async_engine = create_async_engine(
    settings.async_database_url,
    echo=(settings.ENVIRONMENT == "development" and settings.LOG_LEVEL == "DEBUG"),
    future=True,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


# Sync Engine & Session (for Alembic migrations and sync scripts)
sync_engine = create_engine(
    settings.sync_database_url,
    echo=False,
    future=True,
    pool_pre_ping=True,
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
