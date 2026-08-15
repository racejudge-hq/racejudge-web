"""Unit tests for fia_scraper — no network, no filesystem side-effects."""

from __future__ import annotations

import hashlib

import pytest

from packages.pipeline.scrapers.fia_scraper import (
    _clean_title,
    _fix_bare_percent,
    _parse_decision_links,
    _season_filter_url,
    _season_from_url,
    _slugify,
    _storage_name,
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


# ---------------------------------------------------------------------------
# _season_from_url — a document states its own season
# ---------------------------------------------------------------------------

FIA_FILES = "https://www.fia.com/system/files/decision-document"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        # The real URL that exposed the bug: this document was filed as 2025.
        (f"{FIA_FILES}/2026_canadian_grand_prix_-_decision_-_race_"
         "reconnaissance_laps_sc2_-_sc1_.pdf", 2026),
        (f"{FIA_FILES}/2025_canadian_grand_prix_-_infringement_-_car_27.pdf", 2025),
        (f"{FIA_FILES}/2019_british_grand_prix_-_decision_-_car_5.pdf", 2019),
        # No year in the filename — caller's season stands.
        (f"{FIA_FILES}/doc_12_-_decision_-_car_44.pdf", None),
        # Implausible years are not seasons.
        (f"{FIA_FILES}/1998_some_grand_prix_-_decision.pdf", None),
        (f"{FIA_FILES}/2099_some_grand_prix_-_decision.pdf", None),
        # A four-digit run that is not a year prefix must not be read as one.
        (f"{FIA_FILES}/car_2026_decision.pdf", None),
    ],
)
def test_season_from_url(url, expected):
    assert _season_from_url(url) == expected


def test_document_year_overrides_the_page_it_was_found_on():
    """The 2026 Canadian GP is listed on the 2025 filter page.

    Scraping season 2025 must still file those documents as 2026, which is the
    regression that mis-seasoned 43 rows.
    """
    from bs4 import BeautifulSoup

    html = (
        f'<a href="{FIA_FILES}/2026_canadian_grand_prix_-_decision_-_car_27.pdf">'
        "Doc 99 - Infringement - Car 27</a>"
        f'<a href="{FIA_FILES}/2025_canadian_grand_prix_-_decision_-_car_16.pdf">'
        "Doc 12 - Infringement - Car 16</a>"
    )
    docs = _parse_decision_links(BeautifulSoup(html, "html.parser"), 2025)

    assert [d["season"] for d in docs] == [2026, 2025]


def test_season_falls_back_to_the_requested_year_when_url_is_silent():
    from bs4 import BeautifulSoup

    html = f'<a href="{FIA_FILES}/doc_5_-_decision_-_car_1.pdf">Doc 5 - Decision</a>'
    docs = _parse_decision_links(BeautifulSoup(html, "html.parser"), 2024)

    assert [d["season"] for d in docs] == [2024]


# ---------------------------------------------------------------------------
# _storage_name — the filename must not collide
# ---------------------------------------------------------------------------

# The FIA reissues this title at every event of the season; 23 distinct 2023
# documents share it. Under a title-only filename each download overwrote the
# last, and 254 of 1,606 local PDFs ended up being some other decision.
_REISSUED = "PU elements used per driver up to now"


def test_same_title_different_bytes_gets_different_names():
    a = _storage_name(_REISSUED, "a" * 64)
    b = _storage_name(_REISSUED, "b" * 64)
    assert a != b
    assert a.endswith(".pdf") and b.endswith(".pdf")


def test_same_document_gets_the_same_name_twice():
    # Re-scraping must overwrite the identical file, not accumulate copies.
    h = hashlib.sha256(b"pdf bytes").hexdigest()
    assert _storage_name("Decision - Car 4", h) == _storage_name("Decision - Car 4", h)


def test_storage_name_carries_the_doc_id():
    h = hashlib.sha256(b"pdf bytes").hexdigest()
    assert h[:16] in _storage_name("Decision - Car 4", h)


def test_storage_name_has_no_path_separators():
    name = _storage_name("Decision / Car 4 - 30% throttle", "c" * 64)
    assert "/" not in name and "\\" not in name


# ---------------------------------------------------------------------------
# _fix_bare_percent
# ---------------------------------------------------------------------------

def test_bare_percent_is_escaped():
    # "...within 107%.pdf" — a '%' with no hex digits after it is not a valid
    # escape and the FIA's own server answers 400.
    url = "https://www.fia.com/f/2023%20Japanese%20-%20within%20107%.pdf"
    assert _fix_bare_percent(url) == (
        "https://www.fia.com/f/2023%20Japanese%20-%20within%20107%25.pdf")


def test_valid_escapes_are_left_alone():
    url = "https://www.fia.com/f/2024%20Chinese%20Grand%20Prix.pdf"
    assert _fix_bare_percent(url) == url


def test_an_already_escaped_percent_is_not_double_escaped():
    url = "https://www.fia.com/f/within%20107%25.pdf"
    assert _fix_bare_percent(url) == url
