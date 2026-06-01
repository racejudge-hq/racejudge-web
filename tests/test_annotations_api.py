"""Tests for the /v1/annotations API endpoints."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def tmp_annotations(tmp_path, monkeypatch):
    """Redirect annotation storage to a temp file for each test."""
    ann_file = tmp_path / "annotations.jsonl"
    monkeypatch.setattr(
        "apps.api.routers.annotations.ANNOTATIONS_PATH", ann_file
    )
    return ann_file


# ---------------------------------------------------------------------------
# POST /v1/annotations
# ---------------------------------------------------------------------------

def test_submit_annotation_minimal():
    resp = client.post("/v1/annotations", json={"doc_id": "doc-001"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["doc_id"] == "doc-001"
    assert data["annotator"] == "anonymous"
    assert "annotation_id" in data
    assert "created_at" in data


def test_submit_annotation_full():
    payload = {
        "doc_id": "doc-002",
        "annotator": "tester",
        "infraction_type": "causing a collision",
        "outcome": "5 seconds time penalty",
        "penalty_class": "5s",
        "penalty_points": 2,
        "article_cited": "Art 38.1",
        "notes": "Clear fault",
        "positive_doc_id": "doc-003",
        "negative_doc_id": "doc-004",
    }
    resp = client.post("/v1/annotations", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["annotator"] == "tester"
    assert data["label"]["penalty_class"] == "5s"
    assert data["label"]["positive_doc_id"] == "doc-003"


def test_submit_annotation_creates_file(tmp_annotations):
    client.post("/v1/annotations", json={"doc_id": "doc-001"})
    assert tmp_annotations.exists()
    lines = [line for line in tmp_annotations.read_text().splitlines() if line.strip()]
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["doc_id"] == "doc-001"


# ---------------------------------------------------------------------------
# GET /v1/annotations
# ---------------------------------------------------------------------------

def test_list_annotations_empty():
    resp = client.get("/v1/annotations")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_annotations_returns_records():
    client.post("/v1/annotations", json={"doc_id": "doc-A"})
    client.post("/v1/annotations", json={"doc_id": "doc-B"})
    resp = client.get("/v1/annotations")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_list_annotations_filter_doc_id():
    client.post("/v1/annotations", json={"doc_id": "doc-A"})
    client.post("/v1/annotations", json={"doc_id": "doc-B"})
    resp = client.get("/v1/annotations?doc_id=doc-A")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["doc_id"] == "doc-A"


def test_list_annotations_filter_annotator():
    client.post("/v1/annotations", json={"doc_id": "doc-A", "annotator": "alice"})
    client.post("/v1/annotations", json={"doc_id": "doc-B", "annotator": "bob"})
    resp = client.get("/v1/annotations?annotator=alice")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["annotator"] == "alice"


# ---------------------------------------------------------------------------
# GET /v1/annotations/{annotation_id}
# ---------------------------------------------------------------------------

def test_get_annotation_found():
    resp = client.post("/v1/annotations", json={"doc_id": "doc-X"})
    ann_id = resp.json()["annotation_id"]
    resp2 = client.get(f"/v1/annotations/{ann_id}")
    assert resp2.status_code == 200
    assert resp2.json()["annotation_id"] == ann_id


def test_get_annotation_not_found():
    resp = client.get("/v1/annotations/nonexistent-id")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /v1/annotations/{annotation_id}
# ---------------------------------------------------------------------------

def test_delete_annotation():
    resp = client.post("/v1/annotations", json={"doc_id": "doc-del"})
    ann_id = resp.json()["annotation_id"]

    # Verify it exists
    assert client.get(f"/v1/annotations/{ann_id}").status_code == 200

    # Delete it
    del_resp = client.delete(f"/v1/annotations/{ann_id}")
    assert del_resp.status_code == 204

    # Verify it's gone
    assert client.get(f"/v1/annotations/{ann_id}").status_code == 404


def test_delete_annotation_not_found():
    resp = client.delete("/v1/annotations/nonexistent-id")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /v1/annotations/export/triplets
# ---------------------------------------------------------------------------

def test_export_triplets_empty():
    resp = client.get("/v1/annotations/export/triplets")
    assert resp.status_code == 200
    assert resp.json() == []


def test_export_triplets_only_with_positive():
    client.post("/v1/annotations", json={"doc_id": "doc-A"})  # no positive_doc_id
    client.post("/v1/annotations", json={
        "doc_id": "doc-B",
        "positive_doc_id": "doc-C",
        "negative_doc_id": "doc-D",
    })
    resp = client.get("/v1/annotations/export/triplets")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["anchor_doc_id"] == "doc-B"
    assert data[0]["positive_doc_id"] == "doc-C"
    assert data[0]["negative_doc_id"] == "doc-D"


# ---------------------------------------------------------------------------
# GET /v1/annotations/stats/summary
# ---------------------------------------------------------------------------

def test_annotation_stats_empty():
    resp = client.get("/v1/annotations/stats/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_annotations"] == 0
    assert data["triplet_pairs"] == 0
    assert data["target_pairs"] == 500
    assert data["progress_pct"] == 0.0


def test_annotation_stats_counts():
    for i in range(3):
        client.post("/v1/annotations", json={
            "doc_id": f"doc-{i}",
            "annotator": "alice",
            "positive_doc_id": f"pos-{i}",
        })
    client.post("/v1/annotations", json={"doc_id": "doc-nopair"})

    resp = client.get("/v1/annotations/stats/summary")
    data = resp.json()
    assert data["total_annotations"] == 4
    assert data["triplet_pairs"] == 3
    assert data["by_annotator"]["alice"] == 3
    assert data["by_annotator"]["anonymous"] == 1
