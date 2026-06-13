"""
User identity verification for user-scoped endpoints (API keys, billing).

Three identity sources, in order:
  1. RACEJUDGE API key  — `Authorization: Bearer rj_live_*`, already validated
     by RateLimitMiddleware which stores the record on request.state.api_key.
  2. Clerk session JWT  — `Authorization: Bearer <jwt>`, verified against the
     Clerk instance JWKS (CLERK_JWKS_URL) and issuer (CLERK_ISSUER).
  3. Dev fallback       — outside production, when Clerk is not configured,
     the caller-supplied user_id is trusted so local dev and tests work.

In production a missing/invalid token is always a 401 (fail closed), and a
verified identity that does not match the requested user_id is a 403.
"""

from __future__ import annotations

import logging
import os

from fastapi import HTTPException, Request

log = logging.getLogger(__name__)

_jwks_client = None  # lazy singleton; PyJWKClient caches keys internally


def _clerk_configured() -> bool:
    return bool(os.environ.get("CLERK_JWKS_URL"))


def _is_production() -> bool:
    return os.environ.get("ENVIRONMENT", "development") == "production"


def _verify_clerk_jwt(token: str) -> str | None:
    """Verify a Clerk session JWT and return its `sub` (user_id), or None."""
    global _jwks_client
    jwks_url = os.environ.get("CLERK_JWKS_URL")
    if not jwks_url:
        return None
    try:
        import jwt
        from jwt import PyJWKClient

        if _jwks_client is None:
            _jwks_client = PyJWKClient(jwks_url, cache_keys=True)
        signing_key = _jwks_client.get_signing_key_from_jwt(token)
        issuer = os.environ.get("CLERK_ISSUER")
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=issuer if issuer else None,
            options={"verify_aud": False},
            leeway=10,
        )
        return claims.get("sub")
    except ImportError:
        log.error("CLERK_JWKS_URL set but PyJWT not installed — pip install 'PyJWT[crypto]'")
        return None
    except Exception as exc:
        log.info("Clerk JWT verification failed: %s", exc)
        return None


def get_verified_user_id(request: Request) -> str | None:
    """
    Return the authenticated user_id for this request, or None when running
    in dev fallback mode. Raises 401 in production when unauthenticated.
    """
    # 1. API key already validated by RateLimitMiddleware
    key_record = getattr(request.state, "api_key", None)
    if key_record and key_record.get("user_id"):
        return key_record["user_id"]

    # 2. Clerk session JWT
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        if token and not token.startswith("rj_"):
            user_id = _verify_clerk_jwt(token)
            if user_id:
                return user_id
            if _is_production() or _clerk_configured():
                raise HTTPException(status_code=401, detail="Invalid or expired session token.")

    # 3. No credentials supplied
    if _is_production():
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Send a Clerk session token or API key "
                   "as 'Authorization: Bearer <token>'.",
        )
    return None  # dev fallback: caller-supplied user_id is trusted


def ensure_user_match(verified_user_id: str | None, claimed_user_id: str) -> None:
    """403 when an authenticated identity tries to act as a different user."""
    if verified_user_id is not None and verified_user_id != claimed_user_id:
        raise HTTPException(
            status_code=403,
            detail="You are not authorized to act on behalf of this user.",
        )
