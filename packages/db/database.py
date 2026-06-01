"""
Async SQLAlchemy engine, session factory, and base model.

Usage:
    from packages.db.database import get_db, AsyncSessionLocal

    # In FastAPI route:
    async def my_route(db: AsyncSession = Depends(get_db)):
        result = await db.execute(select(Decision))

    # Direct usage:
    async with AsyncSessionLocal() as db:
        result = await db.execute(...)
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Convert postgresql:// → postgresql+asyncpg://
if DATABASE_URL.startswith("postgresql://"):
    ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgres://"):
    ASYNC_DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
else:
    ASYNC_DATABASE_URL = DATABASE_URL

_engine = None
_AsyncSessionLocal = None


def _get_engine():
    global _engine
    if _engine is None and ASYNC_DATABASE_URL:
        _engine = create_async_engine(
            ASYNC_DATABASE_URL,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            echo=False,
        )
    return _engine


def _get_session_factory():
    global _AsyncSessionLocal
    if _AsyncSessionLocal is None:
        engine = _get_engine()
        if engine:
            _AsyncSessionLocal = async_sessionmaker(
                engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
    return _AsyncSessionLocal


AsyncSessionLocal = _get_session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields an async DB session."""
    factory = _get_session_factory()
    if factory is None:
        raise RuntimeError(
            "DATABASE_URL is not set. "
            "Set it in .env or export DATABASE_URL=postgresql://..."
        )
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


class Base(DeclarativeBase):
    pass
