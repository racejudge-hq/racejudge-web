"""
Rate-limiting middleware — Phase 7.

Validates `Authorization: Bearer rj_live_*` API keys and enforces per-tier
daily request quotas.  Gracefully degrades:
  - Redis unavailable → in-memory LRU counter (resets on restart)
  - DATABASE_URL unset → no-op (all requests pass through)

Tier daily limits:
  free   →    100 requests / day
  pro    →  10 000 requests / day
  team   → 100 000 requests / day

Requests without an API key are allowed through for backward compatibility
(existing public endpoints remain open).  New gated routes (MCP, Review)
add their own `require_tier` dependency on top.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

log = logging.getLogger(__name__)

TIER_DAILY_LIMITS: dict[str, int] = {
    "free":  100,
    "pro":   10_000,
    "team":  100_000,
}

# Paths that bypass rate limiting entirely
_SKIP_PREFIXES = ("/health", "/docs", "/openapi.json", "/redoc")
_SKIP_EXACT = {"/v1/billing/webhook"}

# In-memory fallback: {redis_key: (count, day_str)}
_mem_counters: dict[str, tuple[int, str]] = defaultdict(lambda: (0, ""))
_mem_key_cache: dict[str, dict[str, Any]] = {}  # key_hash → record


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


async def _lookup_key_db(key_hash: str) -> dict[str, Any] | None:
    """Look up an API key by hash in Postgres. Returns None if not found/revoked."""
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        return None
    try:
        from packages.db.database import _get_session_factory
        factory = _get_session_factory()
        if factory is None:
            return None
        async with factory() as session:
            from sqlalchemy import text
            result = await session.execute(
                text("""
                    SELECT key_id::text, user_id, key_prefix, tier, is_active
                    FROM api_keys
                    WHERE key_hash = :h AND is_active = TRUE AND revoked_at IS NULL
                """),
                {"h": key_hash},
            )
            row = result.fetchone()
            if row is None:
                return None
            return {
                "key_id":     row[0],
                "user_id":    row[1],
                "key_prefix": row[2],
                "tier":       row[3],
                "is_active":  row[4],
            }
    except Exception as exc:
        log.warning("API key DB lookup failed: %s", exc)
        return None


async def _get_redis():
    """Return a Redis client, or None if unavailable."""
    try:
        import redis.asyncio as aioredis  # type: ignore[import]
        url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        client = aioredis.from_url(url, socket_connect_timeout=1, socket_timeout=1)
        await client.ping()
        return client
    except Exception:
        return None


async def _check_and_increment(key_prefix: str, tier: str) -> tuple[int, int]:
    """
    Increment today's counter for `key_prefix`.
    Returns (current_count, daily_limit).
    """
    limit = TIER_DAILY_LIMITS.get(tier, TIER_DAILY_LIMITS["free"])
    today = _today()
    redis_key = f"rl:{key_prefix}:{today}"

    redis = await _get_redis()
    if redis is not None:
        try:
            pipe = redis.pipeline()
            pipe.incr(redis_key)
            pipe.expire(redis_key, 86400)
            results = await pipe.execute()
            count = int(results[0])
            await redis.aclose()
            return count, limit
        except Exception as exc:
            log.warning("Redis rate-limit increment failed: %s", exc)

    # In-memory fallback
    prev_count, prev_day = _mem_counters[redis_key]
    count = 1 if prev_day != today else prev_count + 1
    _mem_counters[redis_key] = (count, today)
    return count, limit


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Soft-auth middleware: validates Bearer API keys and enforces daily quotas.
    Requests without a key are passed through with no state set.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Fast-pass for excluded paths
        if any(path.startswith(p) for p in _SKIP_PREFIXES) or path in _SKIP_EXACT:
            return await call_next(request)

        auth = request.headers.get("authorization", "")
        if not (auth.lower().startswith("bearer ") and "rj_" in auth.lower()):
            # No API key supplied — anonymous pass-through
            request.state.api_key = None
            request.state.user_tier = "free"
            return await call_next(request)

        raw_key = auth[7:].strip()  # strip "Bearer "
        key_hash = _hash_key(raw_key)

        # Cache lookup to avoid repeated DB hits
        record = _mem_key_cache.get(key_hash)
        if record is None:
            record = await _lookup_key_db(key_hash)
            if record is None:
                return JSONResponse(
                    {"detail": "Invalid or revoked API key."},
                    status_code=401,
                )
            # TTL cache: evict after 5 min by storing fetch time
            record["_cached_at"] = time.monotonic()
            _mem_key_cache[key_hash] = record
        else:
            # Refresh cache after 5 minutes
            if time.monotonic() - record.get("_cached_at", 0) > 300:
                fresh = await _lookup_key_db(key_hash)
                if fresh is None:
                    _mem_key_cache.pop(key_hash, None)
                    return JSONResponse(
                        {"detail": "Invalid or revoked API key."},
                        status_code=401,
                    )
                fresh["_cached_at"] = time.monotonic()
                _mem_key_cache[key_hash] = fresh
                record = fresh

        count, limit = await _check_and_increment(record["key_prefix"], record["tier"])

        if count > limit:
            return JSONResponse(
                {
                    "detail": (
                        f"Daily rate limit exceeded ({limit} requests/day for "
                        f"{record['tier']} tier). Resets at midnight UTC."
                    ),
                    "tier":          record["tier"],
                    "limit":         limit,
                    "requests_today": count,
                },
                status_code=429,
                headers={"Retry-After": "86400"},
            )

        request.state.api_key   = record
        request.state.user_tier = record["tier"]
        return await call_next(request)
