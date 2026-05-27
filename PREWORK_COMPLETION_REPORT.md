# Pre-Work Completion Report
**Date:** 27 May 2026  
**Status:** Pre-Work ~80% complete — all code deliverables done, manual brand tasks and annotation target pending

---

## What Is Fully Done

### Code & Pipeline

| Deliverable | Status | Notes |
|---|---|---|
| `fia_scraper.py` | ✅ Complete | Fully working, MIT-licensed, rate-limited (5s/req) |
| Root path bug fixed | ✅ Fixed | Was `parents[4]` (wrote to `~/Documents/data/`), now `parents[3]` |
| Python 3.14 datetime fix | ✅ Fixed | `datetime.utcnow()` → `datetime.now(timezone.utc)` |
| `_clean_title()` wired in | ✅ Fixed | Strips `Published on25.05.26 02:46CET` suffix from FIA link text |
| Existing 43 records re-cleaned | ✅ Done | All titles in `decisions.jsonl` retroactively cleaned |
| `tests/test_scraper.py` | ✅ Done | 15 unit tests, 15/15 passing (SHA-256, clean_title, slugify, season_url, hash DB) |
| `.env.example` | ✅ Done | All phases documented: DB, R2, Redis, OpenAI, Clerk, Stripe, Fly.io |
| `scripts/annotate_pairs.py` | ✅ Done | Interactive triplet annotation CLI, `--show-progress` flag |
| `scripts/outreach/journalist_pitch.md` | ✅ Done | Two email templates (data angle + GPDA angle), follow-up template |
| `IMPLEMENTATION_PLAN.md` | ✅ Done | 33KB, full 24-week phase plan with SQL schema, API spec, ML targets |
| `requirements.txt` | ✅ Done | Phase 1 active; Phases 2–6 commented out for staged activation |
| `pyproject.toml` | ✅ Done | hatchling, ruff, mypy, pytest config |
| `.github/workflows/ci.yml` | ✅ Done | Lint + mypy + pytest on push |
| `README.md` | ✅ Done | Quickstart, architecture, pricing table |
| `LEGAL.md` | ✅ Done | Media rights policy, DMCA procedure |
| `BRAND_CHECKLIST.md` | ✅ Done | Manual checklist: domains, socials, GitHub org, email |
| `.gitignore` | ✅ Done | PDFs, audio, weights, .env, .next all excluded |
| `.venv` + deps installed | ✅ Done | Python 3.14.0, all Phase 1 packages installed |

### Data Scraped

| Item | Count | Notes |
|---|---|---|
| PDFs downloaded | 43 | All from 2026 Canadian GP weekend |
| JSONL records | 43 | `data/parsed/decisions.jsonl` |
| Needs OCR | 0 | All documents have a text layer — pdfplumber extraction clean |
| Avg char count | 1,699 | Per document |
| SHA-256 dedup store | 43 hashes | `data/ingested_hashes.json` |

---

## Known Limitation: Historical Season Scraping

**Problem:** The FIA document listing page uses JavaScript to filter documents by season. Our BeautifulSoup scraper parses server-rendered HTML, which always returns the same latest-race documents regardless of which `season-XXXX-YYYY` node ID is requested.

**Effect:** Running `--season 2024` returned the identical 43 Canadian GP documents (all rejected as SHA-256 duplicates). We currently have only **1 GP weekend** of data.

**Impact on annotation:** The annotation tool requires 300 labelled pairs. With 43 documents from a single race weekend, most incidents are too similar to each other to get meaningful dissimilar pairs. This blocks the annotation target.

**Fix needed (see "What You Must Do → Historical data" below).**

---

## What Is Left — You Must Do

### 1. Register Brand (1–2 hours) — `BRAND_CHECKLIST.md`

```
Step 1:  Go to namecheap.com or cloudflare.com/registrar
         Search: racejudge.com — register if available (~$10/yr)
         Also grab racejudge.io and racejudge.app as backups

Step 2:  Go to cloudflare.com → add the domain → point nameservers
         (Cloudflare sends you 2 NS addresses, enter them at Namecheap)

Step 3:  In Cloudflare → Email → Email Routing
         Add three catch-all routes:
           hello@racejudge.com  →  maruteymani31@gmail.com
           legal@racejudge.com  →  maruteymani31@gmail.com
           press@racejudge.com  →  maruteymani31@gmail.com

Step 4:  Enable DNSSEC (Cloudflare → DNS → DNSSEC → Enable, one click)
```

### 2. Reserve Social Handles (30 min) — silent, don't announce yet

```
X / Twitter:   twitter.com/signup → username: racejudge
               Bio: "Every F1 stewards' decision, searchable. Coming soon."
Threads:       Same bio, same handle
Reddit:        reddit.com/register → u/racejudge
LinkedIn:      Create company page "RACEJUDGE"
Bluesky:       bsky.app/signup → @racejudge.bsky.social
```

### 3. Create GitHub Organisation (15 min)

```
Step 1:  github.com/organizations/new → name: racejudge-hq

Step 2:  Create PRIVATE repo: racejudge-web
         git remote add origin https://github.com/racejudge-hq/racejudge-web
         git push -u origin main

Step 3:  Create PUBLIC repo: racejudge-scraper (MIT licence)
         This is the goodwill seed — open-source the scraper to attract
         contributors and get backlinks from the F1 data community.
         Push only packages/pipeline/scrapers/fia_scraper.py + tests/test_scraper.py
```

### 4. Get Historical FIA Data (critical for annotation target)

The scraper cannot get historical data via the season-node URL approach because FIA uses JavaScript filtering. Two options — **Option A is easiest:**

**Option A: Use FIA's direct PDF directory**
```bash
# Each GP has documents at a predictable path like:
# https://www.fia.com/documents/championships/fia-formula-one-world-championship-14
# Manual approach: visit the FIA page in your browser for each season,
# right-click → "Save As" the HTML, then run:
python -m packages.pipeline.scrapers.fia_scraper --from-html 2024.html --season 2024
# (Claude will add --from-html support once you confirm you want this approach)
```

**Option B: Playwright/Selenium headless browser**
```bash
pip install playwright
playwright install chromium
# This lets the scraper execute the FIA page's JavaScript and get real season data
# Claude can implement this — takes ~1 hour of work
```

**Recommended:** Confirm Option B and Claude will implement it. This is the cleanest fix and works for all future seasons automatically.

### 5. Annotate 300 Incident Pairs (1–2 hours, do AFTER getting historical data)

Once you have data from 3+ GP weekends (target: ~150+ documents), run:

```bash
source .venv/bin/activate
python scripts/annotate_pairs.py
```

The tool shows you two decisions side-by-side and asks: are these **similar** (same type of infringement) or **dissimilar**?

- Press `s` → similar
- Press `d` → dissimilar  
- Press `q` → quit and save progress
- Press `p` → skip this pair

Target: **150 similar + 150 dissimilar = 300 total.** This is the training data for the BGE-M3 fine-tuning in Phase 4.

Check progress anytime:
```bash
python scripts/annotate_pairs.py --show-progress
```

### 6. Send Journalist Outreach (Week 1 — do during a race weekend)

Templates are ready in `scripts/outreach/journalist_pitch.md`. Send during a GP weekend when stewarding is in the news cycle.

Target outlets (in priority order):
1. The Race — `scott.mitchell@the-race.com`
2. Autosport — `matteo.bressani@autosport.com`  
3. RacingNews365
4. PlanetF1
5. RaceFans

Use Version A (data angle) for The Race and Autosport. Version B (GPDA angle) if you have a team radio quote to anchor it.

---

## What Is Left — Claude Must Do

### Fix Historical Season Scraping (blocked on your decision above)

If you confirm **Option B (Playwright)**, Claude will:
1. Add `playwright` to `requirements.txt` (Phase 1 section)
2. Rewrite `_find_decision_links()` to use a headless browser for the season listing page
3. Keep the rest of the pipeline identical
4. Re-run `--backfill` to ingest 2018–2025

This unlocks all historical data in one run (~2–3 hours of scraping at 5s/req across ~8 seasons).

---

## File Tree After Pre-Work

```
racejudge/
├── .env.example                          ← ✅ new — all phases documented
├── .gitignore                            ← ✅
├── .github/workflows/ci.yml             ← ✅
├── BRAND_CHECKLIST.md                   ← ✅
├── IMPLEMENTATION_PLAN.md               ← ✅ 33KB full plan
├── LEGAL.md                             ← ✅
├── PREWORK_COMPLETION_REPORT.md         ← ✅ this file
├── README.md                            ← ✅
├── pyproject.toml                       ← ✅
├── requirements.txt                     ← ✅ Phase 1 active
├── packages/
│   └── pipeline/
│       └── scrapers/
│           └── fia_scraper.py           ← ✅ fixed + clean_title wired
├── scripts/
│   ├── annotate_pairs.py                ← ✅
│   └── outreach/
│       └── journalist_pitch.md         ← ✅
├── tests/
│   ├── __init__.py                      ← ✅ new
│   └── test_scraper.py                  ← ✅ new — 15/15 passing
└── data/                                ← gitignored
    ├── raw_pdfs/2025/                   ← 43 PDFs
    ├── parsed/decisions.jsonl           ← 43 records, titles cleaned
    └── ingested_hashes.json             ← 43 SHA-256 hashes
```

---

## Pre-Work Go / No-Go

| Gate | Requirement | Status |
|---|---|---|
| Scraper runs without error | ✅ | 43 docs from live fia.com |
| No OCR fallbacks triggered | ✅ | All text-layer PDFs |
| Tests passing | ✅ | 15/15 |
| `decisions.jsonl` clean (no dirty titles) | ✅ | All 43 retroactively cleaned |
| Brand handles reserved | ⏳ | Waiting on you |
| GitHub org created | ⏳ | Waiting on you |
| Annotation pairs: 300 | ⏳ | Blocked on historical data |
| Historical data ingested | ⏳ | Needs Playwright fix decision |

**To unblock everything**: confirm the Playwright approach for historical scraping or let Claude know if you prefer the manual HTML approach. Once that's resolved, 2–3 hours of automated scraping gets all data, then annotation can begin.


