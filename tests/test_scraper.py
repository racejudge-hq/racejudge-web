"""Unit tests for fia_scraper — no network, no filesystem side-effects."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from packages.pipeline.scrapers.fia_scraper import (
    _clean_title,
    _season_filter_url,
    _slugify,
    sha256_of_bytes,
)


# ---------------------------------------------------------------------------
# sha256_of_bytes
# ---------------------------------------------------------------------------

def test_sha256_known_value():
    data = b"hello"
    expected = hashlib.sha256(b"hello").hexdigest()
    assert sha256_of_bytes(data) == expected


def test_sha256_empty():
    assert sha256_of_bytes(b"") == hashlib.sha256(b"").hexdigest()


def test_sha256_returns_64_hex_chars():
    result = sha256_of_bytes(b"racejudge")
    assert len(result) == 64
    assert all(c in "0123456789abcdef" for c in result)


# ---------------------------------------------------------------------------
# _clean_title
# ---------------------------------------------------------------------------

def test_clean_title_strips_published_on():
    dirty = "Decision - HAM - 5s penalty Published on25.05.26 02:46CET"
    assert _clean_title(dirty) == "Decision - HAM - 5s penalty"


def test_clean_title_no_suffix_unchanged():
    clean = "Decision - Competitor Infringement - Car 44"
    assert _clean_title(clean) == clean


def test_clean_title_strips_trailing_dash():
    dirty = "Stewards Decision - VER Published on01.01.25 12:00CET"
    result = _clean_title(dirty)
    assert not result.endswith("-")
    assert "Published" not in result


def test_clean_title_empty_string():
    assert _clean_title("") == ""


# ---------------------------------------------------------------------------
# _slugify
# ---------------------------------------------------------------------------

def test_slugify_replaces_spaces():
    assert " " not in _slugify("Decision Car 44")


def test_slugify_max_length():
    long_title = "A" * 200
    assert len(_slugify(long_title)) <= 80


def test_slugify_strips_special_chars():
    slug = _slugify("Decision: HAM/VER — Lap 1")
    assert ":" not in slug
    assert "/" not in slug


# ---------------------------------------------------------------------------
# _season_filter_url
# ---------------------------------------------------------------------------

def test_season_url_known_season():
    url = _season_filter_url(2025)
    assert "season-2025-2071" in url
    assert url.startswith("https://www.fia.com")


def test_season_url_unknown_season_raises():
    with pytest.raises(ValueError, match="2030"):
        _season_filter_url(2030)


def test_season_url_all_configured_seasons():
    for year in (2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026):
        url = _season_filter_url(year)
        assert str(year) in url


# ---------------------------------------------------------------------------
# _load_hash_db / _save_hash_db (with tmp dir)
# ---------------------------------------------------------------------------

def test_hash_db_roundtrip(tmp_path, monkeypatch):
    from packages.pipeline.scrapers import fia_scraper

    monkeypatch.setattr(fia_scraper, "DEDUP_DB", tmp_path / "hashes.json")

    hashes = {"abc123", "def456"}
    fia_scraper._save_hash_db(hashes)
    loaded = fia_scraper._load_hash_db()
    assert loaded == hashes


def test_load_hash_db_missing_file(tmp_path, monkeypatch):
    from packages.pipeline.scrapers import fia_scraper

    monkeypatch.setattr(fia_scraper, "DEDUP_DB", tmp_path / "nonexistent.json")
    assert fia_scraper._load_hash_db() == set()
