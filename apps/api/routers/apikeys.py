"""
API key management router — Phase 7.

Endpoints:
  GET    /v1/apikeys           — list all active keys for a user (prefix only)
  POST   /v1/apikeys           — create a new key (returns full key ONCE)
  DELETE /v1/apikeys/{key_id}  — revoke a key

Key format:  rj_live_<48 hex chars>  (56 chars total)
Storage:     SHA-256 hash stored; raw key never persisted
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from apps.api.core.auth import ensure_user_match, get_verified_user_id

log = logging.getLogger(__name__)
router = APIRouter(tags=["apikeys"])

_DB_AVAILABLE = bool(os.environ.get("DATABASE_URL"))

TIER_DAILY_LIMITS = {"free": 100, "pro": 10_000, "team": 100_000}


def _generate_raw_key() -> str:
    return "rj_live_" + secrets.token_hex(24)


def _hash(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def _prefix(raw_key: str) -> str:
    return raw_key[:16]  # "rj_live_" + first 8 hex chars


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class ApiKeyPublic(BaseModel):
    key_id:         str
    key_prefix:     str
    name:           str | None
    tier:           str
    is_active:      bool
    requests_today: int
    requests_total: int
    last_used_at:   str | None
    created_at:     str
    daily_limit:    int


class CreateKeyRequest(BaseModel):
    user_id: str = Field(..., description="Clerk user_id")
    name:    str | None = Field(None, max_length=80, description="Human label for this key")
    tier:    str = Field("free", pattern="^(free|pro|team)$")


class CreateKeyResponse(BaseModel):
    key:        str = Field(..., description="Full API key — shown ONCE, never retrievable again")
    key_id:     str
    key_prefix: str
    tier:       str


class RevokeResponse(BaseModel):
    key_id:  str
    revoked: bool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_user_tier(user_id: str) -> str:
    """Return the billing tier for a user from the subscriptions table."""
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        return "free"
    try:
        from sqlalchemy import text

        from packages.db.database import _get_session_factory

        factory = _get_session_factory()
        if factory is None:
            return "free"
        async with factory() as session:
            row = (await session.execute(
                text("SELECT tier FROM subscriptions WHERE user_id=:uid AND status='active'"),
                {"uid": user_id},
            )).fetchone()
            return row[0] if row else "free"
    except Exception as exc:
        log.warning("Tier lookup failed for %s: %s", user_id, exc)
        return "free"


def _row_to_public(row: Any) -> dict[str, Any]:
    return {
        "key_id":         row[0],
        "key_prefix":     row[1],
        "name":           row[2],
        "tier":           row[3],
        "is_active":      row[4],
        "requests_today": row[5],
        "requests_total": row[6],
        "last_used_at":   row[7].isoformat() if row[7] else None,
        "created_at":     row[8].isoformat() if row[8] else "",
        "daily_limit":    TIER_DAILY_LIMITS.get(row[3], 100),
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/apikeys", response_model=list[ApiKeyPublic])
async def list_keys(
    user_id: str = Query(...),
    verified_user: str | None = Depends(get_verified_user_id),
) -> list[dict[str, Any]]:
    """Return all active (non-revoked) API keys for the given user."""
    ensure_user_match(verified_user, user_id)
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        return []
    try:
        from sqlalchemy import text

        from packages.db.database import _get_session_factory

        factory = _get_session_factory()
        if factory is None:
            return []
        async with factory() as session:
            rows = (await session.execute(
                text("""
                    SELECT key_id::text, key_prefix, name, tier, is_active,
                           requests_today, requests_total, last_used_at, created_at
                    FROM api_keys
                    WHERE user_id = :uid AND revoked_at IS NULL
                    ORDER BY created_at DESC
                """),
                {"uid": user_id},
            )).fetchall()
        return [_row_to_public(r) for r in rows]
    except Exception as exc:
        log.error("list_keys error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/apikeys", response_model=CreateKeyResponse, status_code=201)
async def create_key(
    body: CreateKeyRequest,
    verified_user: str | None = Depends(get_verified_user_id),
) -> dict[str, Any]:
    """
    Generate a new API key for the user.

    The tier is resolved from the user's active subscription; the `tier` field
    in the request body is accepted for convenience but may be overridden.
    The full key is returned exactly once and cannot be retrieved again.
    """
    ensure_user_match(verified_user, body.user_id)
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise HTTPException(status_code=503, detail="Database not configured.")

    # Resolve tier from subscription (don't trust client-supplied tier for billing)
    tier = await _get_user_tier(body.user_id)

    raw_key = _generate_raw_key()
    key_hash = _hash(raw_key)
    key_prefix = _prefix(raw_key)

    try:
        from sqlalchemy import text

        from packages.db.database import _get_session_factory

        factory = _get_session_factory()
        if factory is None:
            raise HTTPException(status_code=503, detail="Database unavailable.")
        async with factory() as session:
            row = (await session.execute(
                text("""
                    INSERT INTO api_keys (user_id, key_hash, key_prefix, name, tier)
                    VALUES (:uid, :hash, :prefix, :name, :tier)
                    RETURNING key_id::text
                """),
                {
                    "uid":    body.user_id,
                    "hash":   key_hash,
                    "prefix": key_prefix,
                    "name":   body.name,
                    "tier":   tier,
                },
            )).fetchone()
            await session.commit()
            key_id = row[0]

        log.info("API key created: user=%s prefix=%s tier=%s", body.user_id, key_prefix, tier)
        return {
            "key":        raw_key,
            "key_id":     key_id,
            "key_prefix": key_prefix,
            "tier":       tier,
        }
    except Exception as exc:
        log.error("create_key error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/apikeys/{key_id}", response_model=RevokeResponse)
async def revoke_key(
    key_id: str,
    user_id: str = Query(..., description="Must match the key's owner"),
    verified_user: str | None = Depends(get_verified_user_id),
) -> dict[str, Any]:
    """Revoke an API key. Only the owning user can revoke their own keys."""
    ensure_user_match(verified_user, user_id)
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise HTTPException(status_code=503, detail="Database not configured.")
    try:
        from sqlalchemy import text

        from packages.db.database import _get_session_factory

        factory = _get_session_factory()
        if factory is None:
            raise HTTPException(status_code=503, detail="Database unavailable.")
        async with factory() as session:
            result = await session.execute(
                text("""
                    UPDATE api_keys
                    SET is_active = FALSE, revoked_at = NOW()
                    WHERE key_id = :kid::uuid AND user_id = :uid AND revoked_at IS NULL
                    RETURNING key_id::text
                """),
                {"kid": key_id, "uid": user_id},
            )
            row = result.fetchone()
            await session.commit()

        if row is None:
            raise HTTPException(status_code=404, detail="Key not found or already revoked.")

        log.info("API key revoked: key_id=%s user=%s", key_id, user_id)
        return {"key_id": key_id, "revoked": True}
    except HTTPException:
        raise
    except Exception as exc:
        log.error("revoke_key error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
