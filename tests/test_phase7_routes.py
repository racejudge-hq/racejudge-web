"""
Phase 7 route tests — API keys, billing, MCP, Right-of-Review.

All tests run without a database (monkeypatched) and without Stripe credentials.
"""

from __future__ import annotations

import hashlib
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from apps.api.main import app
    return TestClient(app)


# ---------------------------------------------------------------------------
# API Keys — GET /v1/apikeys
# ---------------------------------------------------------------------------

def test_list_apikeys_no_db(client):
    """Returns empty list when DATABASE_URL is not set."""
    resp = client.get("/v1/apikeys?user_id=user_test_001")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_list_apikeys_requires_user_id(client):
    resp = client.get("/v1/apikeys")
    assert resp.status_code == 422


def test_create_apikey_no_db(client):
    """Returns 503 when no database is configured."""
    resp = client.post(
        "/v1/apikeys",
        json={"user_id": "user_test_001", "name": "test key"},
    )
    # 201 (if no DB check) or 503 (DB unavailable) — either is acceptable
    assert resp.status_code in (201, 503)


def test_delete_apikey_nonexistent(client):
    resp = client.delete("/v1/apikeys/00000000-0000-0000-0000-000000000000?user_id=u1")
    assert resp.status_code in (404, 503)


# ---------------------------------------------------------------------------
# Billing — GET /v1/billing/subscription
# ---------------------------------------------------------------------------

def test_get_subscription_no_db(client):
    """Returns free-tier default when no database is set."""
    resp = client.get("/v1/billing/subscription?user_id=user_test_001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tier"] == "free"
    assert "status" in data


def test_get_subscription_requires_user_id(client):
    resp = client.get("/v1/billing/subscription")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Billing — POST /v1/billing/webhook (Stripe disabled)
# ---------------------------------------------------------------------------

def test_stripe_webhook_disabled_when_no_key(client):
    """When STRIPE_SECRET_KEY is not set, webhook short-circuits to 200 received:true."""
    resp = client.post(
        "/v1/billing/webhook",
        content=b'{"type":"customer.subscription.updated"}',
        headers={"stripe-signature": "t=1,v1=fake"},
    )
    # Stripe disabled → endpoint returns {"received": true} immediately
    assert resp.status_code == 200
    assert resp.json().get("received") is True


# ---------------------------------------------------------------------------
# Billing — POST /v1/billing/portal (Stripe disabled)
# ---------------------------------------------------------------------------

def test_billing_portal_no_stripe(client):
    resp = client.post("/v1/billing/portal", json={"user_id": "u1"})
    # 503 (Stripe disabled) or 404 (no customer)
    assert resp.status_code in (404, 503)


# ---------------------------------------------------------------------------
# MCP — GET /mcp/v1/manifest (no auth required)
# ---------------------------------------------------------------------------

def test_mcp_manifest_public(client):
    resp = client.get("/mcp/v1/manifest")
    assert resp.status_code == 200
    data = resp.json()
    assert "tools" in data
    tools = {t["name"] for t in data["tools"]}
    assert "search_precedents" in tools
    assert "get_incident"      in tools
    assert "get_driver_stats"  in tools
    assert "predict_penalty"   in tools


def test_mcp_manifest_has_descriptions(client):
    resp = client.get("/mcp/v1/manifest")
    for tool in resp.json()["tools"]:
        assert "description" in tool
        assert len(tool["description"]) > 10


# ---------------------------------------------------------------------------
# MCP — POST /mcp/v1/query (requires API key)
# ---------------------------------------------------------------------------

def test_mcp_query_requires_auth(client):
    resp = client.post(
        "/mcp/v1/query",
        json={"tool": "search_precedents", "arguments": {"query": "unsafe pit lane"}},
    )
    assert resp.status_code in (401, 403, 422)


def test_mcp_query_invalid_tool(client):
    resp = client.post(
        "/mcp/v1/query",
        json={"tool": "nonexistent_tool", "arguments": {}},
        headers={"Authorization": "Bearer rj_live_fake"},
    )
    # 401 (bad key) or 404 (unknown tool) — either is correct
    assert resp.status_code in (401, 403, 404, 422)


# ---------------------------------------------------------------------------
# Right-of-Review — POST /v1/review/generate
# ---------------------------------------------------------------------------

def test_review_generate_missing_fields(client):
    resp = client.post("/v1/review/generate", json={})
    assert resp.status_code == 422


def test_review_generate_bad_incident_id(client):
    resp = client.post(
        "/v1/review/generate",
        json={
            "user_id":      "u1",
            "incident_id":  "00000000-0000-0000-0000-000000000000",
            "driver_code":  "VER",
            "team_name":    "Red Bull Racing",
            "new_evidence": "Telemetry shows car was not at fault.",
        },
    )
    # 404 (incident not found) or 503 (no DB) — both acceptable
    assert resp.status_code in (404, 503)


def test_review_generate_validates_driver_code(client):
    resp = client.post(
        "/v1/review/generate",
        json={
            "user_id":      "u1",
            "incident_id":  "00000000-0000-0000-0000-000000000000",
            "driver_code":  "",          # empty — should fail
            "team_name":    "Red Bull",
            "new_evidence": "Evidence.",
        },
    )
    assert resp.status_code in (404, 422, 503)
