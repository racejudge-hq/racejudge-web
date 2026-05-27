# RACEJUDGE — The Stewards' Precedent Engine

> *Every F1 incident, every decision, every precedent — searchable, comparable, and explainable.*

No public tool exists that makes FIA stewards' decisions searchable, comparable, or linked to evidence. RACEJUDGE fills that gap.

---

## What it does

| Feature | Description |
|---|---|
| **Precedent Search** | Natural-language queries across every FIA decision since 2018 |
| **Penalty Predictor** | Calibrated probability distribution over 7 outcome classes |
| **Multimodal Linking** | Each decision linked to race control messages, team radio, and telemetry |
| **Live Mode** | When "UNDER INVESTIGATION" fires, top-5 precedents pushed to subscribers in <5s |
| **Consistency Heat-Maps** | Statistical outlier detection across steward panels, seasons, circuits |
| **Guideline Browser** | 2025 FIA Penalty Guidelines + Driving Standards fully searchable and cross-linked |
| **Right-of-Review Builder** | Auto-assemble evidence packs for Right-of-Review petitions (Team tier) |

---

## Repository structure

```
racejudge/
├── apps/
│   ├── web/              # Next.js 14 frontend (Phase 6)
│   └── api/              # FastAPI backend (Phase 1+)
├── packages/
│   ├── pipeline/         # Prefect DAGs + Celery workers
│   │   ├── scrapers/     # FIA PDF scraper (this file is MIT open-source)
│   │   ├── parsers/      # pdfplumber + Tesseract + LayoutLMv3
│   │   ├── linkers/      # OpenF1 race_control + radio joiner
│   │   ├── audio/        # Faster-Whisper ASR + pyannote diarisation
│   │   └── telemetry/    # FastF1 slicer
│   ├── ml/               # Model training (BGE-M3, XGBoost, Llama LoRA)
│   └── db/               # Alembic migrations + schema
├── infra/                # Terraform (Fly.io, Neon, R2)
├── scripts/
│   ├── annotate_pairs.py # Incident pair annotation CLI (pre-work Action 2)
│   └── outreach/         # Journalist pitch templates
└── data/                 # Local data (gitignored)
    ├── raw_pdfs/         # Downloaded FIA PDFs
    ├── parsed/           # Extracted JSONL records
    └── annotations/      # Labelled similarity pairs
```

---

## Getting started (Pre-Work / Phase 1)

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Run the FIA scraper

```bash
# Scrape 2025 decisions
python -m packages.pipeline.scrapers.fia_scraper --season 2025

# Full backfill (2018–2025)
python -m packages.pipeline.scrapers.fia_scraper --backfill
```

PDFs are saved to `data/raw_pdfs/{season}/`. Parsed text records go to `data/parsed/decisions.jsonl`.

### 3. Annotate incident pairs (Action 2 pre-work)

```bash
# Start the annotation session
python scripts/annotate_pairs.py

# Check progress
python scripts/annotate_pairs.py --show-progress
```

Target: 300 labelled pairs (150 similar + 150 dissimilar). These are the BGE-M3 fine-tuning training data for Phase 4.

---

## Development phases

| Phase | Weeks | Objective | Key milestone |
|---|---|---|---|
| Pre-Work | 0 | Brand + scraper + annotation seed | 300 labelled pairs |
| 1 | 1–3 | Infrastructure + raw PDF ingestion | 100% 2024–25 PDFs ingested |
| 2 | 4–7 | Structured extraction + incidents table | >90% F1-score on field extraction |
| 3 | 8–10 | Multimodal linking | Every incident linked to race_control + radio |
| 4 | 11–14 | Precedent search (BGE-M3 + RRF) | Recall@10 ≥ 0.80 |
| 5 | 15–18 | Penalty prediction (XGBoost + Llama LoRA) | Macro-F1 ≥ 0.65, ECE < 0.05 |
| 6 | 19–21 | Full Next.js web app + live mode | p95 latency < 5s |
| 7 | 22–23 | API + MCP server + billing | 3 journalists onboarded |
| 8 | 24 | Public launch at European GP | First external coverage within 48h |

Full detail: see [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

---

## Data sources

All data is public:

| Source | What | Coverage |
|---|---|---|
| [fia.com/documents](https://www.fia.com/documents) | Stewards' Decision PDFs | 2018–present |
| [OpenF1 API](https://openf1.org) | race_control, team_radio, laps, telemetry | 2023–present |
| [FastF1](https://github.com/theOehrly/Fast-F1) | Lap timing, telemetry, tyre data | 2018–present |
| FIA Penalty Guidelines (June 2025) | Codified infraction taxonomy | Published June 2025 |
| FIA Driving Standards Guidelines v4.1 | Racing behaviour rules | Published June 2025 |

---

## Open-source component

The FIA PDF scraper (`packages/pipeline/scrapers/fia_scraper.py`) is released under the MIT licence as a standalone tool. It can be used independently to download and parse FIA decision documents for any purpose.

---

## Legal

- FIA decision PDFs are public documents.
- Team radio and onboard video are FOM-licensed. RACEJUDGE links only to officially-published URLs and never hosts unlicensed content.
- Predictions are for informational and educational purposes only. Not intended for gambling.
- See [LEGAL.md](LEGAL.md) for DMCA takedown procedure.

---

## Pricing

| Tier | Price | Includes |
|---|---|---|
| Free | $0 | Basic precedent search (10 queries/day), decision browser, penalty-points tracker |
| Pro | $29/mo | Unlimited search, live mode, penalty predictor, consistency heat-maps, API |
| Team | $499/mo | Everything in Pro + Right-of-Review Builder, private annotations, priority API |
| Enterprise | Custom | White-label, on-premise, FIA/FOM integrations |
