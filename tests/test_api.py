"""
Tests for the FastAPI endpoints — no database required.
Uses TestClient with a monkeypatched JSONL loader.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

SAMPLE_RECORDS = [
    {
        "doc_id": "abc123def456abc1",
        "title": "Decision - Car 44 - 5s time penalty",
        "pdf_url": "https://www.fia.com/system/files/example.pdf",
        "r2_key": "pdfs/2024/example.pdf",
        "sha256_hash": "abc123def456abc1" * 4,
        "raw_text": "The stewards investigated the matter.",
        "season": 2024,
        "published_at": "2024-06-01",
        "parser_version": "v1.0-pdfplumber",
        "parsed_at": "2024-06-01T12:00:00+00:00",
        "char_count": 38,
        "needs_ocr": False,
    },
    {
        "doc_id": "def456abc123def4",
        "title": "Infringement - Car 1 - Pit lane speeding",
        "pdf_url": "https://www.fia.com/system/files/example2.pdf",
        "r2_key": "pdfs/2024/example2.pdf",
        "sha256_hash": "def456abc123def4" * 4,
        "raw_text": "Car 1 exceeded the pit lane speed limit.",
        "season": 2024,
        "published_at": "2024-07-01",
        "parser_version": "v1.0-pdfplumber",
        "parsed_at": "2024-07-01T12:00:00+00:00",
        "char_count": 41,
        "needs_ocr": False,
    },
    {
        "doc_id": "fff111aaa222fff1",
        "title": "Decision - Car 16 - Reprimand",
        "pdf_url": "https://www.fia.com/system/files/example3.pdf",
        "r2_key": "pdfs/2023/example3.pdf",
        "sha256_hash": "fff111aaa222fff1" * 4,
        "raw_text": "Car 16 received a reprimand.",
        "season": 2023,
        "published_at": "2023-05-01",
        "parser_version": "v1.0-pdfplumber",
        "parsed_at": "2023-05-01T12:00:00+00:00",
        "char_count": 28,
        "needs_ocr": False,
    },
]


@pytest.fixture
def client(monkeypatch):
    from apps.api.routers import decisions as dec_module
    # The new router uses _load_decisions_jsonl (renamed from _load_decisions)
    monkeypatch.setattr(dec_module, "_load_decisions_jsonl", lambda: SAMPLE_RECORDS)

    from apps.api.main import app
    return TestClient(app)


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "ts" in data


# ---------------------------------------------------------------------------
# GET /v1/decisions
# ---------------------------------------------------------------------------

def test_list_decisions_returns_all(client):
    resp = client.get("/v1/decisions")
    assert resp.status_code == 200
    assert len(resp.json()) == 3


def test_list_decisions_filter_by_season(client):
    resp = client.get("/v1/decisions?season=2024")
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 2
    assert all(r["season"] == 2024 for r in results)


def test_list_decisions_filter_by_season_no_results(client):
    resp = client.get("/v1/decisions?season=2018")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_decisions_search(client):
    resp = client.get("/v1/decisions?q=reprimand")
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 1
    assert "Reprimand" in results[0]["title"]


def test_list_decisions_search_case_insensitive(client):
    resp = client.get("/v1/decisions?q=SPEEDING")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_list_decisions_limit(client):
    resp = client.get("/v1/decisions?limit=1")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_list_decisions_offset(client):
    resp1 = client.get("/v1/decisions?limit=1&offset=0")
    resp2 = client.get("/v1/decisions?limit=1&offset=1")
    doc_ids = [resp1.json()[0]["doc_id"], resp2.json()[0]["doc_id"]]
    assert doc_ids[0] != doc_ids[1]


def test_list_decisions_response_shape(client):
    rec = client.get("/v1/decisions").json()[0]
    assert "doc_id" in rec
    assert "title" in rec
    assert "season" in rec
    assert "raw_text" not in rec  # list endpoint excludes raw text


# ---------------------------------------------------------------------------
# GET /v1/decisions/{doc_id}
# ---------------------------------------------------------------------------

def test_get_decision_found(client):
    resp = client.get("/v1/decisions/abc123def456abc1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["doc_id"] == "abc123def456abc1"
    assert "raw_text" in data  # detail endpoint includes raw text


def test_get_decision_not_found(client):
    resp = client.get("/v1/decisions/nonexistent000000")
    assert resp.status_code == 404


def test_get_decision_includes_sha256(client):
    resp = client.get("/v1/decisions/abc123def456abc1")
    assert "sha256_hash" in resp.json()


def test_consistency_route_is_not_shadowed_by_incident_id():
    """
    /incidents/consistency is a literal path declared alongside
    /incidents/{incident_id}. Starlette matches in declaration order, so if the
    parameterised route is declared first the literal one is swallowed —
    incident_id becomes "consistency" and the endpoint 404s/500s. This broke the
    /consistency page in production. Assert route ordering, not just the handler.
    """
    import re as _re

    from apps.api.main import app

    seen: list[tuple[str, str]] = []
    for route in app.routes:
        path = getattr(route, "path", None)
        if not path:
            continue
        for method in sorted(getattr(route, "methods", None) or []):
            if method in ("HEAD", "OPTIONS"):
                continue
            for prev_method, prev_path in seen:
                if prev_method != method or "{" not in prev_path or "{" in path:
                    continue
                pattern = "^" + _re.sub(r"\{[^}]+\}", "[^/]+", prev_path) + "$"
                assert not _re.match(pattern, path), (
                    f"{method} {path} is shadowed by the earlier route {prev_path}; "
                    f"declare the literal path first"
                )
            seen.append((method, path))
