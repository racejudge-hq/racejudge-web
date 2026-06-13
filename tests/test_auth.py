"""
Tests for user identity verification (apps/api/core/auth.py).

Covers the three modes:
  - dev fallback (no Clerk config, non-production) → caller user_id trusted
  - production without credentials → 401 fail-closed
  - verified identity mismatch → 403
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from apps.api.core.auth import ensure_user_match


@pytest.fixture
def client():
    from apps.api.main import app
    return TestClient(app)


# ---------------------------------------------------------------------------
# ensure_user_match
# ---------------------------------------------------------------------------

def test_match_passes():
    ensure_user_match("user_a", "user_a")


def test_dev_fallback_passes():
    """verified=None (dev mode) trusts the claimed user_id."""
    ensure_user_match(None, "user_a")


def test_mismatch_raises_403():
    with pytest.raises(HTTPException) as exc:
        ensure_user_match("user_a", "user_b")
    assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# Endpoint behaviour: dev mode (default test environment)
# ---------------------------------------------------------------------------

def test_apikeys_dev_mode_allows_unauthenticated(client):
    resp = client.get("/v1/apikeys?user_id=user_test_001")
    assert resp.status_code == 200


def test_subscription_dev_mode_allows_unauthenticated(client):
    resp = client.get("/v1/billing/subscription?user_id=user_test_001")
    assert resp.status_code == 200
    assert resp.json()["tier"] == "free"


# ---------------------------------------------------------------------------
# Endpoint behaviour: production fails closed
# ---------------------------------------------------------------------------

def test_apikeys_production_requires_auth(client, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    resp = client.get("/v1/apikeys?user_id=user_test_001")
    assert resp.status_code == 401


def test_subscription_production_requires_auth(client, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    resp = client.get("/v1/billing/subscription?user_id=user_test_001")
    assert resp.status_code == 401


def test_portal_production_requires_auth(client, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    resp = client.post(
        "/v1/billing/portal",
        json={"user_id": "user_test_001", "return_url": "http://localhost:3000/api"},
    )
    assert resp.status_code == 401


def test_create_key_production_requires_auth(client, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    resp = client.post(
        "/v1/apikeys",
        json={"user_id": "user_test_001", "name": "x"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Invalid JWT with Clerk configured → 401 even outside production
# ---------------------------------------------------------------------------

def test_garbage_jwt_rejected_when_clerk_configured(client, monkeypatch):
    monkeypatch.setenv("CLERK_JWKS_URL", "https://example.invalid/.well-known/jwks.json")
    resp = client.get(
        "/v1/apikeys?user_id=user_test_001",
        headers={"Authorization": "Bearer not.a.jwt"},
    )
    assert resp.status_code == 401
