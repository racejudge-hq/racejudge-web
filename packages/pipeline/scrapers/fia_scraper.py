"""
FIA Stewards Decision PDF Scraper
MIT License — open-source component of RACEJUDGE

Scrapes fia.com/documents for Formula 1 stewards' decision PDFs,
deduplicates by SHA-256 hash, extracts raw text via pdfplumber,
and saves structured JSONL records for annotation.

The FIA document listing page uses a three-tier faceted filter
(season → championship → event) driven by Drupal's facet API.
This scraper uses Playwright to render the season+F1 filter page,
discovers every GP event URL from the event dropdown, then
visits each event page to collect PDFs.

Pass --no-playwright to scrape only the most-recently-published
documents without a headless browser (useful for CI or quick checks).

Usage:
    python -m packages.pipeline.scrapers.fia_scraper --season 2025
    python -m packages.pipeline.scrapers.fia_scraper --backfill
    python -m packages.pipeline.scrapers.fia_scraper --season 2025 --no-playwright
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import logging
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pdfplumber
import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data"
RAW_PDF_DIR = DATA_DIR / "raw_pdfs"
PARSED_DIR = DATA_DIR / "parsed"
DEDUP_DB = DATA_DIR / "ingested_hashes.json"

RAW_PDF_DIR.mkdir(parents=True, exist_ok=True)
PARSED_DIR.mkdir(parents=True, exist_ok=True)

REQUEST_DELAY = 5.0      # seconds between PDF downloads
PAGE_LOAD_TIMEOUT = 60_000   # ms — Playwright page.goto timeout
PDF_LINK_TIMEOUT  = 15_000   # ms — time to wait for PDF anchors to appear

FIA_BASE     = "https://www.fia.com"
FIA_DOCS_URL = "https://www.fia.com/documents/championships/fia-formula-one-world-championship-14"

# The FIA faceted filter always uses the most-recent season's node as the
# "base" championship page.  Season sub-filters sit under it.
FIA_BASE_NODE  = "season-2025-2071"
FIA_F1_SUFFIX  = "championships/fia-formula-one-world-championship-14"

# Season facet node IDs discovered from the FIA filter dropdown.
# Key = F1 *calendar* year.  Add new seasons here each January.
SEASON_FILTER_NODES: dict[int, str] = {
    2026: "season-2026-2072",
    2025: "season-2025-2071",
    2024: "season-2024-2043",
    2023: "season-2023-2042",
    2022: "season-2022-2005",
    2021: "season-2021-1108",
    2020: "season-2020-1059",
    2019: "season-2019-971",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; RaceJudge-Scraper/1.0; "
        "+https://github.com/racejudge-hq/racejudge-scraper)"
    ),
    "Accept": "text/html,application/xhtml+xml",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Deduplication store (local JSON file, replaced by Postgres in Phase 1)
# ---------------------------------------------------------------------------

def _load_hash_db() -> set[str]:
    if DEDUP_DB.exists():
        return set(json.loads(DEDUP_DB.read_text()))
    return set()


def _save_hash_db(hashes: set[str]) -> None:
    DEDUP_DB.write_text(json.dumps(sorted(hashes), indent=2))


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _get(url: str, *, stream: bool = False) -> requests.Response:
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30, stream=stream)
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            if attempt == 2:
                raise
            log.warning("Retrying %s after error: %s", url, exc)
            time.sleep(REQUEST_DELAY * (attempt + 1))
    raise RuntimeError("unreachable")


def _polite_get(url: str, *, stream: bool = False) -> requests.Response:
    time.sleep(REQUEST_DELAY)
    return _get(url, stream=stream)


# ---------------------------------------------------------------------------
# SHA-256 hash
# ---------------------------------------------------------------------------

def sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Title cleaning
# ---------------------------------------------------------------------------

_PUBLISHED_ON_RE = re.compile(r"Published\s+on\s*\d.*$", re.IGNORECASE)
_BARE_PERCENT_RE = re.compile(r"%(?![0-9A-Fa-f]{2})")


def _clean_title(title: str) -> str:
    """Strip 'Published on...' suffix that FIA appends to link text."""
    return _PUBLISHED_ON_RE.sub("", title).strip(" \t\n-–")


def _slugify(title: str) -> str:
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)
    return safe.strip().replace(" ", "_")[:80]


def _storage_name(title: str, file_hash: str) -> str:
    """Build the on-disk / R2 filename for a document.

    Titles are nowhere near unique. The FIA reissues the same one all season —
    "PU elements used per driver up to now" alone covers 23 distinct documents
    in 2023 — so a title-derived name makes every reissue overwrite the last.
    That is exactly what happened: 254 of 1,606 local PDFs were not the
    decision they were recorded against, across 72 colliding names.

    The hash prefix is the doc_id, so the name is unique whenever the bytes
    differ and identical whenever they do not — a re-download of the same
    document is idempotent rather than a second copy.
    """
    return f"{_slugify(title)}-{file_hash[:16]}.pdf"


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def _season_filter_url(season: int) -> str:
    """Return the season+F1 combined filter URL for a given calendar year."""
    node = SEASON_FILTER_NODES.get(season)
    if not node:
        raise ValueError(
            f"No FIA season node configured for {season}. Add it to SEASON_FILTER_NODES."
        )
    # Pattern: /docs/.../BASE_NODE/season/SEASON_NODE/championships/F1
    return f"{FIA_DOCS_URL}/{FIA_BASE_NODE}/season/{node}/{FIA_F1_SUFFIX}"


# ---------------------------------------------------------------------------
# HTML parsing helpers
# ---------------------------------------------------------------------------

def _season_from_url(pdf_url: str) -> int | None:
    """Read the championship year off the FIA's own filename.

    The FIA names every decision PDF `<year>_<event>_-_<type>_-_<subject>.pdf`,
    so the document states its own season. Trusting the `--season` flag instead
    is what mis-filed the 2026 Canadian GP: that event appears on the 2025
    filter page, so all 43 of its documents were stamped 2025. The year in the
    filename is the document's own claim and beats the page we found it on.

    Returns None when the filename carries no plausible year, leaving the
    caller's requested season as the fallback.
    """
    m = re.search(r"/(\d{4})_[a-z]", pdf_url.lower())
    if not m:
        return None
    year = int(m.group(1))
    return year if 2015 <= year <= 2030 else None


def _parse_decision_links(soup: BeautifulSoup, season: int) -> list[dict]:
    """Extract stewards' decision PDF links from a rendered FIA page."""
    docs: list[dict] = []
    for a in soup.find_all("a", href=True):
        href: str = a["href"]  # type: ignore[assignment,arg-type,union-attr,operator,return-value]
        if not href.lower().endswith(".pdf"):
            continue
        title = _clean_title(a.get_text(strip=True) or a.get("title", ""))  # type: ignore[assignment,arg-type,union-attr,operator,return-value]
        title_lower = title.lower()
        if not any(
            kw in title_lower
            for kw in ("steward", "decision", "penalty", "reprimand",
                       "infringement", "competitor", "driver", "disqualif")
        ):
            continue
        full_url = href if href.startswith("http") else FIA_BASE + href
        docs.append({
            "title": title,
            "pdf_url": full_url,
            "published_at": _extract_date_near_link(a),
            "season": _season_from_url(full_url) or season,
        })
    return docs


# The date element on the FIA listing page, in the two shapes it comes in:
# "Published on08.10.23 20:58CET" and a bare "07.12.25 15:59". Both are the
# same clock in different markup -- measured against the incidents whose UTC
# time is known, the two shapes have the same publication lag and neither
# produces a document published before the incident it describes.
_PUBLISHED_RE = re.compile(
    r"(?P<d>\d{2})\.(?P<m>\d{2})\.(?P<y>\d{2})\s+(?P<H>\d{2}):(?P<M>\d{2})"
)

# The page says "CET" on every row, in July as well as January. It means Paris
# local time, not a fixed UTC+1: read as fixed, summer publication lag inflates
# from 132 to 192 minutes against a winter figure of 114 that neither reading
# changes -- almost exactly the hour a missed DST change would add. See
# migration 0022.
_FIA_TZ = ZoneInfo("Europe/Paris")


def parse_published_at(raw: str | None) -> datetime | None:
    """Turn the FIA listing page's date string into an aware UTC datetime.

    Returns None for anything that does not carry a full date and time, so a
    row whose element held something unexpected stays NULL rather than being
    given a plausible-looking wrong instant. The raw string is kept alongside
    in `decisions.published_at`; this is derived from it, not a replacement.
    """
    if not raw:
        return None
    m = _PUBLISHED_RE.search(raw)
    if not m:
        return None
    try:
        local = datetime(
            2000 + int(m.group("y")), int(m.group("m")), int(m.group("d")),
            int(m.group("H")), int(m.group("M")), tzinfo=_FIA_TZ,
        )
    except ValueError:
        return None  # 31.02, hour 25 -- a misread element, not a date
    return local.astimezone(UTC)


def _extract_date_near_link(a_tag) -> str | None:
    for parent in a_tag.parents:
        date_el = parent.find(class_=lambda c: c and "date" in c.lower())
        if date_el:
            return date_el.get_text(strip=True)
        time_el = parent.find("time")
        if time_el:
            return time_el.get("datetime") or time_el.get_text(strip=True)
        if parent.name in ("body", "html"):
            break
    return None


def _extract_event_urls(soup: BeautifulSoup) -> list[tuple[str, str]]:
    """
    Parse the event dropdown (facetapi_select_facet_form_2) and return
    a list of (event_name, full_url) pairs.
    """
    sel = soup.find("select", id="facetapi_select_facet_form_2")
    if not sel:
        return []
    events = []
    for opt in sel.find_all("option"):
        val = opt.get("value", "")
        name = opt.get_text(strip=True)
        if val and val != "0":
            full_url = val if val.startswith("http") else FIA_BASE + val  # type: ignore[assignment,arg-type,union-attr,operator,return-value]
            events.append((name, full_url))
    return events  # type: ignore[assignment,arg-type,union-attr,operator,return-value]


# ---------------------------------------------------------------------------
# Playwright-based scraping (full season)
# ---------------------------------------------------------------------------

def _find_decision_links_playwright(season: int) -> list[dict]:
    """
    Use a headless browser to:
      1. Load the season+F1 filter page and discover all GP event URLs.
      2. Visit each event page and collect stewards' decision PDF links.
    """
    from playwright.sync_api import TimeoutError as PWTimeout
    from playwright.sync_api import sync_playwright

    base_url = _season_filter_url(season)
    log.info("[Playwright] Loading season %d filter: %s", season, base_url)

    all_docs: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=HEADERS["User-Agent"],
            java_script_enabled=True,
        )
        page = context.new_page()

        # ── Step 1: load season+F1 page and discover event URLs ──────────────
        page.goto(base_url, wait_until="networkidle", timeout=PAGE_LOAD_TIMEOUT)
        soup = BeautifulSoup(page.content(), "html.parser")
        events = _extract_event_urls(soup)

        if not events:
            log.warning("[Playwright] No event URLs found for season %d; collecting from base page", season)
            docs = _parse_decision_links(soup, season)
            browser.close()
            return docs

        log.info("[Playwright] Season %d: %d events found", season, len(events))

        # ── Step 2: visit each event page ─────────────────────────────────────
        for event_name, event_url in events:
            log.info("[Playwright] Event: %s", event_name)
            try:
                page.goto(event_url, wait_until="networkidle", timeout=PAGE_LOAD_TIMEOUT)
                with contextlib.suppress(PWTimeout):
                    page.wait_for_selector("a[href$='.pdf']", timeout=PDF_LINK_TIMEOUT)
                event_soup = BeautifulSoup(page.content(), "html.parser")
                docs = _parse_decision_links(event_soup, season)
                log.info("  → %d decision documents", len(docs))
                all_docs.extend(docs)
                # Polite delay between event pages (no PDF download yet)
                time.sleep(REQUEST_DELAY)
            except Exception as exc:
                log.error("[Playwright] Failed to load event %s: %s", event_name, exc)

        browser.close()

    log.info("[Playwright] Season %d total: %d decision documents", season, len(all_docs))
    return all_docs


# ---------------------------------------------------------------------------
# Plain HTTP fallback (current race weekend only)
# ---------------------------------------------------------------------------

def _find_decision_links_requests(season: int) -> list[dict]:
    """
    Plain HTTP fallback. Only returns documents from the most-recently-published
    race weekend because the FIA site requires JavaScript for season filtering.
    Useful for quick checks or CI environments without Playwright.
    """
    url = _season_filter_url(season)
    log.info("[requests] Fetching season %d: %s", season, url)
    resp = _polite_get(url)
    soup = BeautifulSoup(resp.text, "html.parser")
    docs = _parse_decision_links(soup, season)
    log.info("[requests] Found %d candidate documents for season %d", len(docs), season)
    return docs


def _find_decision_links(season: int, *, use_playwright: bool = True) -> list[dict]:
    if use_playwright:
        return _find_decision_links_playwright(season)
    return _find_decision_links_requests(season)


# ---------------------------------------------------------------------------
# Download + parse
# ---------------------------------------------------------------------------

def _fix_bare_percent(url: str) -> str:
    """Escape a '%' the FIA left unencoded in its own filename.

    Several decisions are titled "...failing to set a lap time within 107%",
    and the '%' survives into the URL as a literal. A '%' not followed by two
    hex digits is not a valid escape, so the request is rejected with 400
    before it ever reaches the file. Three 2023 decisions were unreachable
    for this reason alone.
    """
    return _BARE_PERCENT_RE.sub("%25", url)


def _download_pdf(pdf_url: str) -> bytes:
    log.info("Downloading: %s", pdf_url)
    resp = _polite_get(_fix_bare_percent(pdf_url), stream=True)
    return resp.content


def _extract_text(pdf_bytes: bytes, pdf_path: Path) -> str:
    try:
        with pdfplumber.open(pdf_path) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        return "\n".join(pages).strip()
    except Exception as exc:
        log.warning("pdfplumber failed on %s: %s", pdf_path.name, exc)
        return ""


# ---------------------------------------------------------------------------
# Main ingestion
# ---------------------------------------------------------------------------

def ingest_season(
    season: int,
    ingested_hashes: set[str],
    *,
    use_playwright: bool = True,
) -> list[dict]:
    """
    Download and parse all new decision PDFs for a season.
    Returns a list of parsed document records (appended to PARSED_DIR/decisions.jsonl).
    """
    records: list[dict] = []
    RAW_PDF_DIR.mkdir(exist_ok=True)

    docs = _find_decision_links(season, use_playwright=use_playwright)
    if not docs:
        log.warning("No documents found for season %d.", season)
        return records

    # Deduplicate by URL within this batch to avoid re-downloading same PDF
    # discovered on multiple event pages
    seen_urls: set[str] = set()

    for doc in docs:
        pdf_url = doc["pdf_url"]
        if pdf_url in seen_urls:
            continue
        seen_urls.add(pdf_url)

        try:
            pdf_bytes = _download_pdf(pdf_url)
        except Exception as exc:
            log.error("Failed to download %s: %s", pdf_url, exc)
            continue

        file_hash = sha256_of_bytes(pdf_bytes)
        if file_hash in ingested_hashes:
            log.debug("Skipping already-ingested: %s", doc["title"])
            continue

        # File the document under the season it states, not the season whose
        # filter page surfaced it — the two differ whenever the FIA lists a new
        # year's event on the outgoing year's page.
        doc_season = doc.get("season") or season
        season_dir = RAW_PDF_DIR / str(doc_season)
        season_dir.mkdir(exist_ok=True)

        filename = _storage_name(doc["title"], file_hash)
        pdf_path = season_dir / filename
        pdf_path.write_bytes(pdf_bytes)
        log.info("Saved: %s", pdf_path.name)

        raw_text = _extract_text(pdf_bytes, pdf_path)
        if len(raw_text) < 50:
            log.warning(
                "Very short text (%d chars) from %s — may need OCR fallback",
                len(raw_text), pdf_path.name,
            )

        record = {
            "doc_id": file_hash[:16],
            "title": _clean_title(doc["title"]),
            "pdf_url": pdf_url,
            "r2_key": f"pdfs/{doc_season}/{filename}",
            "sha256_hash": file_hash,
            "raw_text": raw_text,
            "season": doc_season,
            "published_at": doc.get("published_at"),
            "published_at_utc": parse_published_at(doc.get("published_at")),
            "parser_version": "v1.1-pdfplumber",
            "parsed_at": datetime.now(UTC).isoformat(),
            "char_count": len(raw_text),
            "needs_ocr": len(raw_text) < 50,
        }

        ingested_hashes.add(file_hash)
        records.append(record)

    return records


def run(seasons: list[int], *, use_playwright: bool = True) -> None:
    """Entry point: scrape and parse all given seasons."""
    ingested_hashes = _load_hash_db()
    log.info("Loaded %d already-ingested hashes", len(ingested_hashes))

    all_records: list[dict] = []
    for season in sorted(seasons):
        log.info("=== Season %d ===", season)
        records = ingest_season(season, ingested_hashes, use_playwright=use_playwright)
        all_records.extend(records)
        log.info("Season %d: %d new documents ingested", season, len(records))

    if all_records:
        outfile = PARSED_DIR / "decisions.jsonl"
        with outfile.open("a", encoding="utf-8") as f:
            for rec in all_records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        log.info("Wrote %d new records to %s", len(all_records), outfile)

    _save_hash_db(ingested_hashes)
    log.info("Done. Total ingested: %d", len(ingested_hashes))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape FIA Formula 1 stewards' decision PDFs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full season via Playwright (iterates all GP events)
  python -m packages.pipeline.scrapers.fia_scraper --season 2024

  # Backfill all available seasons (2019–2026)
  python -m packages.pipeline.scrapers.fia_scraper --backfill

  # Current race weekend only, no Playwright
  python -m packages.pipeline.scrapers.fia_scraper --season 2026 --no-playwright
        """,
    )
    parser.add_argument(
        "--season", type=int, action="append", dest="seasons", metavar="YEAR",
        help="Season year to scrape (repeatable)",
    )
    parser.add_argument(
        "--backfill", action="store_true",
        help="Scrape all configured seasons",
    )
    parser.add_argument(
        "--no-playwright", action="store_true",
        help="Skip Playwright; use plain HTTP (current race weekend only)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    if args.backfill:
        seasons = sorted(SEASON_FILTER_NODES.keys())
    elif args.seasons:
        seasons = args.seasons
    else:
        seasons = [datetime.now(UTC).year]
        print(f"No season specified — defaulting to current year ({seasons[0]})")

    run(seasons, use_playwright=not args.no_playwright)
