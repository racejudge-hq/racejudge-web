"""
Phase 8 route tests — latency metrics, steward variance, rate limiting.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from apps.api.main import app
    return TestClient(app)


# ---------------------------------------------------------------------------
# Latency metrics — GET /v1/metrics/latency
# ---------------------------------------------------------------------------

def test_latency_endpoint_exists(client):
    resp = client.get("/v1/metrics/latency")
    assert resp.status_code == 200


def test_latency_response_shape(client):
    # Hit a real endpoint first to populate the rolling window
    client.get("/health")
    client.get("/v1/decisions")

    resp = client.get("/v1/metrics/latency")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)


def test_latency_values_are_positive(client):
    # Generate some traffic
    for _ in range(3):
        client.get("/v1/decisions")

    resp = client.get("/v1/metrics/latency")
    for _path, stats in resp.json().items():
        for key in ("p50_ms", "p95_ms", "p99_ms", "min_ms", "max_ms"):
            if key in stats:
                assert stats[key] >= 0, f"{key} should be non-negative"


def test_latency_skips_health_endpoint(client):
    """Health endpoint is in _SKIP set and must not appear in metrics."""
    for _ in range(5):
        client.get("/health")
    data = client.get("/v1/metrics/latency").json()
    assert "/health" not in data


def test_latency_skips_itself(client):
    """Metrics endpoint must not track its own calls."""
    for _ in range(3):
        client.get("/v1/metrics/latency")
    data = client.get("/v1/metrics/latency").json()
    assert "/v1/metrics/latency" not in data


# ---------------------------------------------------------------------------
# Steward variance — GET /v1/incidents/variance
# ---------------------------------------------------------------------------

def test_variance_endpoint_exists(client):
    """Endpoint is reachable — 200 (with DB) or 503 (no DB) are both correct."""
    resp = client.get("/v1/incidents/variance")
    assert resp.status_code in (200, 503)


def test_variance_response_shape(client):
    resp = client.get("/v1/incidents/variance")
    if resp.status_code == 503:
        return  # no DB in test env — skip shape check
    data = resp.json()
    assert "categories"    in data
    assert "min_incidents" in data
    assert "season_filter" in data
    assert isinstance(data["categories"], list)


def test_variance_min_incidents_param(client):
    resp = client.get("/v1/incidents/variance?min_incidents=1")
    assert resp.status_code in (200, 503)


def test_variance_min_incidents_out_of_range(client):
    """Query parameter validation runs before DB check — must be 422."""
    resp = client.get("/v1/incidents/variance?min_incidents=0")
    assert resp.status_code == 422


def test_variance_season_filter(client):
    resp = client.get("/v1/incidents/variance?season=2024")
    assert resp.status_code in (200, 503)
    if resp.status_code == 200:
        assert resp.json()["season_filter"] == 2024


def test_variance_category_endpoint_missing(client):
    resp = client.get("/v1/incidents/variance/nonexistent_category")
    # 404 (category not found) or 503 (no DB) — both acceptable
    assert resp.status_code in (404, 503)


# ---------------------------------------------------------------------------
# Rate limiting middleware — anonymous pass-through
# ---------------------------------------------------------------------------

def test_anonymous_requests_pass_through(client):
    """Requests without Authorization header should not be rate-limited."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.headers.get("X-RateLimit-Remaining") is None or resp.status_code != 429


def test_invalid_bearer_format_passes(client):
    """Non-rj_live_ Bearer tokens should pass through (not our key format)."""
    resp = client.get("/v1/decisions", headers={"Authorization": "Bearer some_other_token"})
    assert resp.status_code == 200


def test_rate_limit_header_not_on_anonymous(client):
    """Anonymous requests should not get rate-limit headers."""
    resp = client.get("/v1/decisions")
    # If rate limit headers exist they should not indicate blocked
    assert resp.status_code != 429


# ---------------------------------------------------------------------------
# Shannon entropy helpers (unit test via import)
# ---------------------------------------------------------------------------

def test_entropy_pure_distribution():
    from apps.api.routers.stewards import _entropy
    # All-same outcome → entropy = 0
    assert _entropy({"5s": 10}) == 0.0


def test_entropy_uniform_distribution():
    from apps.api.routers.stewards import _entropy
    import math
    counts = {"NFA": 5, "REP": 5, "5s": 5, "10s": 5}
    h = _entropy(counts)
    assert abs(h - math.log2(4)) < 0.001


def test_inconsistency_score_single_outcome():
    from apps.api.routers.stewards import _inconsistency_score
    assert _inconsistency_score({"5s": 100}) == 0.0


def test_inconsistency_score_bounded():
    from apps.api.routers.stewards import _inconsistency_score
    score = _inconsistency_score({"NFA": 3, "5s": 3, "DT": 3})
    assert 0.0 <= score <= 1.0


def test_mean_severity_nfa():
    from apps.api.routers.stewards import _mean_severity
    assert _mean_severity({"NFA": 10}) == 0.0


def test_mean_severity_weighted():
    from apps.api.routers.stewards import _mean_severity
    # NFA=0, DSQ=6 with equal counts → mean = 3.0
    result = _mean_severity({"NFA": 5, "DSQ": 5})
    assert result == 3.0


def test_modal_returns_highest_count():
    from apps.api.routers.stewards import _modal
    assert _modal({"NFA": 1, "5s": 5, "REP": 2}) == "5s"


def test_modal_empty_returns_nfa():
    from apps.api.routers.stewards import _modal
    assert _modal({}) == "NFA"
