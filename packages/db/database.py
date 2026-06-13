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
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.environ.get("DATABASE_URL", "")

_SSL_REQUIRED_MODES = {"require", "verify-ca", "verify-full"}


def _normalize_async_url(url: str) -> tuple[str, dict[str, Any]]:
    """
    Convert a libpq-style URL (as issued by Neon/Heroku/etc.) into an
    asyncpg-compatible SQLAlchemy URL.

    asyncpg rejects libpq query parameters like `sslmode` and
    `channel_binding`, so they are stripped here and `sslmode=require`
    is translated into asyncpg's `ssl=True` connect argument.
    """
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)

    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    sslmode = query.pop("sslmode", "")
    query.pop("channel_binding", None)

    connect_args: dict[str, Any] = {}
    if sslmode.lower() in _SSL_REQUIRED_MODES:
        connect_args["ssl"] = True

    return urlunsplit(parts._replace(query=urlencode(query))), connect_args


ASYNC_DATABASE_URL, _CONNECT_ARGS = (
    _normalize_async_url(DATABASE_URL) if DATABASE_URL else ("", {})
)

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
            connect_args=_CONNECT_ARGS,
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
