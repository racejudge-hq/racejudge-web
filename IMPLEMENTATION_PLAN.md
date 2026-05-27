# RACEJUDGE — Phase-Wise Implementation Plan

> **The Stewards' Precedent Engine**
> *Every F1 incident, every decision, every precedent — searchable, comparable, and explainable.*

---

## Overview

| Attribute | Detail |
|---|---|
| Total Duration | 24 weeks |
| Stack | Python 3.12+ · Next.js 14 · PostgreSQL 16 + pgvector · FastAPI · Prefect 3 · Celery/Redis · Cloudflare R2 |
| Hosting | Fly.io (multi-region) · Neon Postgres · Modal (GPU) · Cloudflare R2 |
| Auth / Billing | Clerk · Stripe |
| Target Launch | European GP weekend (Week 24) |

---

## Pre-Work: First 72 Hours (Before Any Code)

These three actions run in parallel before development begins. Do them in order.

### Action 1 — Claim the Brand (Hours 0–4)
- [ ] Register `racejudge.com` (+ `.io`, `.app` variants as fallbacks)
- [ ] Reserve `@racejudge` on X/Twitter, Threads, GitHub, Reddit, LinkedIn
- [ ] Create private GitHub organisation `racejudge-hq` with two repos: `racejudge-web` and `racejudge-pipeline`
- [ ] Register a backup name in case of FIA trademark objection

### Action 2 — Seed the Retriever (Hours 4–24)
- [ ] Download 50–100 FIA decision PDFs from fia.com/documents (2024–2025 season)
- [ ] Hand-label 300 incident pairs as **similar** or **dissimilar** using the FIA's own infraction categories as the taxonomy
- [ ] Store as `similarity_pairs.jsonl` — each line: `{"anchor_id": "...", "positive_id": "...", "negative_id": "...", "label": "similar|dissimilar"}`
- [ ] This is the single highest-ROI 20 hours in the entire project (feeds BGE-M3 fine-tuning in Phase 4)

### Action 3 — Recruit Design Partners (Hours 24–72)
- [ ] Identify and cold-email 5 F1 journalists: The Race, Autosport, RacingNews365, PlanetF1, RaceFans
- [ ] Offer a private preview in exchange for design feedback
- [ ] Lead pitch with: GPDA transparency push + 84%-too-harsh Zandvoort reader verdict + first successful Right of Review (Sainz/Zandvoort 2025)

---

## Phase 1 — Foundation (Weeks 1–3)

**Objective:** Infrastructure scaffolding + raw PDF ingestion pipeline running end-to-end.

### Infrastructure Provisioning
- [ ] Provision **Neon Postgres** (primary region: LHR, read replica: IAD), enable `pgvector` and `TimescaleDB` extensions
- [ ] Create **Cloudflare R2** bucket: `racejudge-raw` (PDFs), `racejudge-audio` (radio clips), `racejudge-telemetry` (cached snapshots)
- [ ] Provision **Redis** instance (Upstash or self-hosted) for Celery broker + result backend
- [ ] Set up **Prefect Cloud** workspace with three work pools: `pdf-ingest`, `ml-train`, `live-session`
- [ ] Scaffold monorepo structure:

```
racejudge/
├── apps/
│   ├── web/          # Next.js 14
│   └── api/          # FastAPI
├── packages/
│   ├── pipeline/     # Prefect DAGs + Celery tasks
│   ├── ml/           # Model training code
│   └── db/           # Alembic migrations + schema
├── infra/            # Terraform (Fly.io, Neon, R2)
└── scripts/          # One-off data ops
```

- [ ] GitHub Actions CI: lint (ruff + eslint), type-check (mypy + tsc), test (pytest + vitest) on every PR
- [ ] Terraform Cloud workspace — apply base infra (Fly apps, DNS, R2 buckets, Neon project)

### FIA PDF Scraper (open-source component, MIT)
- [ ] Build `pipeline/scrapers/fia_scraper.py`:
  - Target: `fia.com/documents` filtered by category `Formula 1`
  - Parse document listing with **BeautifulSoup 4**
  - Respect `robots.txt` — rate-limit to **1 request / 5 seconds**
  - Download PDF, compute **SHA-256 hash**
  - Check `documents.sha256_hash` in Postgres — skip if already ingested
  - Upload raw PDF to R2 key: `pdfs/{season}/{round}/{doc_number}.pdf`
  - Insert row into `documents` table with `r2_key`, `pdf_url`, `published_at`
- [ ] Run **back-fill**: all 2024–2025 decision PDFs as raw text via `pdfplumber`
- [ ] Prefect scheduled flow: every 15 min during live session windows, nightly otherwise

### Core Database Schema (Migrations 001–003)

```sql
-- Migration 001: events + sessions
CREATE TABLE events (
  event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  season   SMALLINT NOT NULL,
  round    SMALLINT NOT NULL,
  circuit_key  TEXT NOT NULL,
  circuit_name TEXT NOT NULL,
  country      TEXT NOT NULL,
  date_start   DATE NOT NULL,
  date_end     DATE NOT NULL,
  UNIQUE(season, round)
);

CREATE TABLE sessions (
  session_key  INTEGER PRIMARY KEY,
  event_id     UUID REFERENCES events(event_id),
  session_type TEXT NOT NULL,  -- FP1/FP2/FP3/Q/SQ/R/SR
  date_start   TIMESTAMPTZ,
  date_end     TIMESTAMPTZ
);

-- Migration 002: documents
CREATE TABLE documents (
  doc_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_key    INTEGER REFERENCES sessions(session_key),
  doc_number     TEXT,
  title          TEXT NOT NULL,
  published_at   TIMESTAMPTZ NOT NULL,
  pdf_url        TEXT NOT NULL,
  r2_key         TEXT NOT NULL,
  raw_text       TEXT,
  sha256_hash    BYTEA NOT NULL UNIQUE,
  parser_version TEXT NOT NULL,
  parsed_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Migration 003: full-text search index
CREATE INDEX idx_documents_fts ON documents
  USING GIN(to_tsvector('english', coalesce(title,'') || ' ' || coalesce(raw_text,'')));
```

### Celery Task Queue Setup
- [ ] Workers: `parse_pdf`, `extract_text_pdfplumber`, `ocr_fallback_tesseract`
- [ ] Redis queues: `high` (live session), `default` (nightly), `bulk` (back-fill)
- [ ] Dead-letter queue with Sentry error reporting

### Phase 1 Milestone
> **100% of 2024–25 decision PDFs ingested as raw text.** Scraper runs reliably, deduplication working, raw text stored in `documents.raw_text`.

---

## Phase 2 — Structured Extraction (Weeks 4–7)

**Objective:** Parse raw PDF text into structured incident records; build the core `incidents` table.

### Annotation Campaign
- [ ] Hand-annotate **300 decision PDFs** in Label Studio (self-hosted) with fields:
  - `drivers[]` — name, car number, team
  - `session` — FP/Q/Race
  - `lap` — integer
  - `corner` — free text (e.g. "Turn 4", "Chicane")
  - `article_cited[]` — e.g. `["48.1", "Appendix L Ch.4"]`
  - `infraction_category` — from 2025 FIA Penalty Guidelines taxonomy
  - `penalty_type` — NFA / REP / 5s / 10s / DT / GRID / DSQ
  - `penalty_seconds` — integer
  - `penalty_points` — integer
  - `reasoning_text` — full stewards' reasoning paragraph(s)
- [ ] Active-learning loop: model predicts → human corrects → retrain (target: 5 cycles)

### Parser Pipeline (3-layer fallback chain)

```
Layer 1: pdfplumber text extraction  →  regex-based field extractor
Layer 2: Tesseract 5 OCR             →  regex on OCR output  (scanned PDFs)
Layer 3: LayoutLMv3 fine-tune        →  structured JSON extraction (complex layouts)

Use highest-confidence result across all three layers.
```

- [ ] `pipeline/parsers/pdfplumber_extractor.py` — regex patterns for standard FIA decision layout
- [ ] `pipeline/parsers/tesseract_fallback.py` — Tesseract 5 OCR, triggered when pdfplumber yields < 100 chars
- [ ] `pipeline/parsers/layoutlm_extractor.py` — LayoutLMv3 fine-tuned on 300-doc annotated set (Modal A10G GPU, ~4h training)
- [ ] Target metric: **>90% F1-score** on driver/lap/article/penalty extraction over held-out 2025 GP decisions

### Incidents Schema (Migration 004)

```sql
CREATE TABLE incidents (
  incident_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  doc_id             UUID REFERENCES documents(doc_id),
  drivers            JSONB NOT NULL,  -- [{number, code, name, team}]
  session_key        INTEGER REFERENCES sessions(session_key),
  lap                SMALLINT,
  corner             TEXT,
  article_cited      TEXT[],
  infraction_category TEXT,
  penalty_type       TEXT,  -- NFA/REP/5s/10s/DT/GRID/DSQ
  penalty_seconds    SMALLINT,
  penalty_points     SMALLINT DEFAULT 0,
  grid_positions     SMALLINT,
  contact            BOOLEAN,
  position_change    SMALLINT,
  reasoning_text     TEXT NOT NULL,
  embedding          vector(1024),  -- BGE-M3, populated in Phase 4
  created_at         TIMESTAMPTZ DEFAULT NOW(),
  updated_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_incidents_penalty_type ON incidents(penalty_type);
CREATE INDEX idx_incidents_season ON incidents((drivers->0->>'team'), created_at);
CREATE INDEX idx_incidents_article ON incidents USING GIN(article_cited);
```

### Guidelines Ingestion
- [ ] Parse **2025 FIA Penalty Guidelines** (14 May 2025, ~100 infraction types) into `guidelines` table
- [ ] Parse **Driving Standards Guidelines v4.1** (20 Feb 2025) into `guidelines` table
- [ ] Article-level granularity: each article is one row with `article_number`, `article_text`, `recommended_penalty`, `effective_date`

```sql
CREATE TABLE guidelines (
  article_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_name      TEXT NOT NULL,
  section            TEXT,
  article_number     TEXT NOT NULL,
  article_text       TEXT NOT NULL,
  recommended_penalty TEXT,
  effective_date     DATE NOT NULL
);
```

### Entity Resolution
- [ ] `pipeline/resolvers/driver_resolver.py` — map extracted names/numbers to canonical driver records (handle abbreviations, name variants, nationality prefixes)
- [ ] `pipeline/resolvers/article_resolver.py` — map article citations to `guidelines.article_id`
- [ ] Seed `drivers`, `teams`, `constructors` reference tables from Jolpica-F1 / FastF1

### Back-fill Extraction
- [ ] Run structured extraction over all 2024–25 PDFs ingested in Phase 1
- [ ] Begin 2018–2023 back-fill (est. ~2,870 decisions across 6 seasons)

### Phase 2 Milestone
> **>90% F1-score on field extraction.** All 2024–25 incidents in the `incidents` table with structured fields. Guidelines loaded.

---

## Phase 3 — Multimodal Linking (Weeks 8–10)

**Objective:** For every parsed incident, automatically attach race_control messages, team radio clips, telemetry slices, and weather context.

### Race Control Linker
- [ ] Build `pipeline/linkers/race_control_linker.py`:
  - Fetch all `race_control` messages from OpenF1 for each session
  - Join to `incidents` by: `session_key` + `driver_number` + timestamp window ±30s
  - Fuzzy match on message keywords ("UNDER INVESTIGATION", "PENALTY", driver number)
  - Populate `race_control_messages` table with `incident_id` FK

```sql
CREATE TABLE race_control_messages (
  rc_id         BIGSERIAL PRIMARY KEY,
  session_key   INTEGER REFERENCES sessions(session_key),
  date          TIMESTAMPTZ NOT NULL,
  category      TEXT,  -- Flag/SafetyCar/Investigation/Decision
  flag          TEXT,
  scope         TEXT,
  driver_number SMALLINT,
  message       TEXT NOT NULL,
  incident_id   UUID REFERENCES incidents(incident_id)
);
CREATE INDEX idx_rc_session_date ON race_control_messages(session_key, date);
```

### Team Radio Fetcher & ASR Pipeline

**Model 2: F1-Domain ASR**
- Architecture: `faster-whisper` Large-V3 with LoRA adapters
- Training data: `MikCil/f1-team-radio` HF dataset + manually augmented F1 vocabulary
- F1 vocabulary additions: driver surnames, "box box", "blue flag", "undercut", "delta", circuit corner names
- Target: **WER < 12%** on F1 radio test set
- Inference: INT8 quantised for back-fill; FP16 for live sessions

- [ ] `pipeline/audio/radio_fetcher.py` — fetch 3 nearest team_radio mp3 clips within ±60s of incident timestamp from OpenF1
- [ ] Cache mp3s to R2: `audio/{session_key}/{driver}/{clip_id}.mp3`
- [ ] `pipeline/audio/asr_worker.py` — Celery task: run Faster-Whisper, store transcript in `team_radio_clips.transcript`
- [ ] `pipeline/audio/diarisation.py` — pyannote.audio v3: label each turn as `driver`/`engineer`/`other`

```sql
CREATE TABLE team_radio_clips (
  clip_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_key    INTEGER REFERENCES sessions(session_key),
  driver_number  SMALLINT NOT NULL,
  date           TIMESTAMPTZ NOT NULL,
  recording_url  TEXT NOT NULL,
  r2_key         TEXT,
  transcript     TEXT,
  speaker_label  TEXT,        -- 'driver'/'engineer'/'other'
  sentiment_score REAL,       -- populated in Phase 5
  urgency_score   REAL,       -- populated in Phase 5
  incident_id    UUID REFERENCES incidents(incident_id)
);
```

### Telemetry Slicer

- [ ] `pipeline/telemetry/fastf1_slicer.py`:
  - Use FastF1 cache for 2018–present (FastF1 / Jolpica-F1 for pre-2023 back-fill)
  - Extract lap-level features (speed, throttle, brake, gear, DRS) for all involved drivers
  - Pre-compute aggregate features: max speed differential, braking point delta, overlap duration
  - Store in `lap_features` TimescaleDB hypertable

```sql
-- TimescaleDB hypertable
CREATE TABLE lap_features (
  session_key    INTEGER NOT NULL,
  driver_number  SMALLINT NOT NULL,
  lap_number     SMALLINT NOT NULL,
  lap_time_ms    INTEGER,
  sector_1_ms    INTEGER,
  sector_2_ms    INTEGER,
  sector_3_ms    INTEGER,
  compound       TEXT,
  tyre_age       SMALLINT,
  is_pit_outlap  BOOLEAN,
  max_speed      REAL,
  incident_id    UUID REFERENCES incidents(incident_id),
  PRIMARY KEY (session_key, driver_number, lap_number)
);
SELECT create_hypertable('lap_features', 'session_key', chunk_time_interval => 100);
```

### Weather Context
- [ ] Attach OpenF1 `weather` endpoint data (air_temp, track_temp, humidity, rainfall) at incident timestamp to `incidents` as a JSONB `weather_context` column (Migration 005)

### Video References
- [ ] Store F1TV/FOM-published clip embed URLs in `incidents.video_refs` (JSONB array) — **never host unlicensed video**
- [ ] Document DMCA takedown procedure in `LEGAL.md`

### Phase 3 Milestone
> **Every 2024–25 incident has ≥1 linked race_control message and ≥1 transcribed radio clip (where available from OpenF1).** Graceful degradation for missing audio ("No radio available").

---

## Phase 4 — Precedent Retrieval (Weeks 11–14)

**Objective:** Ship semantic + full-text hybrid precedent search with Recall@10 ≥ 0.80.

### Model 3: Sentence Embedder

- Architecture: **BGE-M3** (BAAI), 1024-dimensional embeddings
- Fine-tuning: Triplet loss on (anchor, positive, negative) triples using the 500 hand-labelled pairs from Pre-Work Action 2
- Training: Modal A10G, ~2h
- Indexing: `pgvector` HNSW (`m=16`, `ef_construction=200`, `ef_search=80`)

```sql
-- Migration 006: embedding index
CREATE INDEX idx_incidents_embedding
  ON incidents USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 200);
```

### Hybrid Retrieval (RRF)
- [ ] `api/retrieval/semantic_search.py` — pgvector ANN query returning top-100 candidates
- [ ] `api/retrieval/bm25_search.py` — PostgreSQL tsvector BM25 full-text search
- [ ] `api/retrieval/rrf.py` — Reciprocal Rank Fusion merging both result sets: `score = Σ 1/(k + rank_i)` where `k=60`
- [ ] Target: **Recall@10 ≥ 0.80** on held-out 500-pair test set

### Precedent Links Table

```sql
CREATE TABLE precedent_links (
  incident_id         UUID REFERENCES incidents(incident_id),
  similar_incident_id UUID REFERENCES incidents(incident_id),
  similarity_score    REAL NOT NULL,
  link_type           TEXT,  -- 'semantic'/'article'/'manual'
  PRIMARY KEY (incident_id, similar_incident_id)
);
```

- [ ] Nightly Prefect job: recompute top-20 precedent links for all incidents added in the past 24h; update `precedent_links`

### Structured Filters
Build filter support on `GET /v1/incidents` and `POST /v1/precedents/search`:
- `driver` — driver code (e.g. `VER`, `HAM`)
- `team` — constructor name
- `season_range` — `[2022, 2025]`
- `article` — e.g. `"48.1"`
- `penalty_type` — `NFA|REP|5s|10s|DT|GRID|DSQ`
- `contact` — `true|false`
- `lap_phase` — `first_lap|race|qualifying`
- `corner_type` — `hairpin|chicane|high_speed`
- `has_radio` — `true|false`

### Precedent Search UI
- [ ] `/search` page in Next.js: semantic query input + structured filter sidebar + incident result cards
- [ ] Each card shows: drivers, session, lap, penalty type, similarity score, link to full `/incidents/:id`
- [ ] Server-rendered with ISR for SEO

### Phase 4 Milestone
> **Recall@10 ≥ 0.80 on held-out test set.** Semantic search live and returning results for natural-language queries like "10-second penalties for forcing a car off track on corner exit since 2022."

---

## Phase 5 — Penalty Prediction (Weeks 15–18)

**Objective:** Train, calibrate, and ship the penalty classifier and explainability layer.

### Model 4: Penalty Severity Classifier

**Architecture: Stacked Ensemble**

| Layer | Model | Input |
|---|---|---|
| A | XGBoost (tabular) | article_cited, lap_phase, contact, position_change, corner_type, weather, tyre_compound, speed_diff, session_type |
| B | Llama-3-8B-Instruct + LoRA | incident free-text reasoning |
| Meta | Stacked logistic regression + Platt calibration | Layer A + B outputs |

- Time-based train/val/test split: **train 2018–2023 · validate 2024 · test 2025** (never random-split)
- Output: probability distribution over 7 classes: `NFA | REP | 5s | 10s | DT | GRID | DSQ` + expected penalty-point delta (0–3)
- Target: **Macro-F1 ≥ 0.65** · **ECE < 0.05**

Training steps:
- [ ] Extract tabular feature matrix from `incidents` for all 2018–2023 records
- [ ] Train XGBoost with 5-fold time-series cross-validation
- [ ] Fine-tune Llama-3-8B-Instruct LoRA on `(reasoning_text, penalty_type)` pairs (Modal A100, ~6h)
- [ ] Build stacked meta-learner with Platt calibration
- [ ] Evaluate: reliability diagram, confusion matrix, ECE per class
- [ ] **Gate: do not ship publicly if ECE ≥ 0.05**

### Model 5: Team Radio Sentiment Classifier

- Architecture: DistilBERT fine-tuned on transcribed team radio
- Output: `sentiment_score` (-1.0 to +1.0), `urgency_score` (0.0 to 1.0)
- Backfill `team_radio_clips.sentiment_score` + `urgency_score`
- Used as feature input to Model 4 (Layer A)

### Model 6: Reasoning Explainer (RAG)

- Architecture: Llama-3.1-70B-Instruct hosted on Modal/Together.ai
- Context window: retrieved guideline articles + top-3 precedent incident texts
- Output: human-readable reasoning chain with cited article numbers
- Guard-rail: output `"Insufficient precedent data for confident prediction"` when confidence < threshold
- Cost control: cache RAG outputs in Redis (TTL 24h) — regenerate only for novel incident descriptions

### Predictions Log

```sql
CREATE TABLE predictions_log (
  prediction_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  query_text     TEXT NOT NULL,
  query_features JSONB,
  top_k_incidents UUID[],
  predicted_dist JSONB NOT NULL,  -- {NFA:0.1, REP:0.2, ...}
  ground_truth   TEXT,            -- filled post-hoc for calibration
  model_version  TEXT NOT NULL,
  latency_ms     INTEGER,
  created_at     TIMESTAMPTZ DEFAULT NOW()
);
```

### Prediction UI
- [ ] `/predict` page: free-text incident description input
- [ ] Real-time probability distribution bar chart (Plotly)
- [ ] Top-3 precedent citations with similarity scores
- [ ] Relevant guideline article text
- [ ] Prominent disclaimer: "For informational and educational purposes only. Not intended for gambling."
- [ ] Never show point predictions — always probability distributions

### Phase 5 Milestone
> **Macro-F1 ≥ 0.65 over 7-class taxonomy; ECE < 0.05.** Classifier is calibrated and prediction UI is live.

---

## Phase 6 — UX & Live Mode (Weeks 19–21)

**Objective:** Build the complete public website with real-time investigation capabilities.

### Full Next.js 14 Application

All pages use **App Router**, **React Server Components** for data, **TanStack Query** for client-side cache.

| Route | Page | Notes |
|---|---|---|
| `/` | Home | Hero, live penalty-points ticker, search bar, recent decisions feed |
| `/search` | Precedent Search | Semantic query + filter sidebar + result cards with similarity scores |
| `/incidents/:id` | Incident Detail | Decision text, radio player, telemetry chart, video embed, precedent sidebar, guideline cross-ref |
| `/predict` | Penalty Predictor | Free-text input → probability chart → precedent citations |
| `/consistency` | Consistency Heat-Maps | Penalty severity by article / season / steward chair / circuit |
| `/drivers/:code` | Driver Profile | Penalty-point ledger, incident history, ban-risk projection chart |
| `/guidelines` | Rulebook Browser | Article-level browsing, usage stats, linked decisions |
| `/live` | Live Mode | Real-time investigation feed, auto-updating cards with precedent push |
| `/api` | API Docs | Auto-generated from OpenAPI spec, key management, usage dashboard |

### Design System
- Dark-mode-first (F1 aesthetic) with light-mode toggle — `next-themes`
- Tailwind CSS + shadcn/ui component library
- Plotly.js for interactive charts (penalty distributions, telemetry overlays)
- D3.js for custom consistency heat-maps
- Mapbox GL JS for circuit corner overlay (incident density per corner)
- Mobile-responsive: **tested on iOS Safari 17 + Android Chrome 125**
- WCAG 2.1 AA accessibility compliance minimum

### Live Mode (WebSocket)

Architecture: FastAPI WebSocket + Redis Pub/Sub

```
OpenF1 poller (15s interval during live session)
    │
    ├─ Detects "UNDER INVESTIGATION" race_control message
    │
    ├─ Queries precedent retriever for top-5 similar incidents (< 1s via Redis cache)
    │
    ├─ Runs penalty predictor (< 2s via cached XGBoost + quantised Llama)
    │
    └─ Publishes to Redis channel `live:investigations`
         │
         └─ WebSocket server fans out to all subscribers
              │
              └─ Browser push notification via Web Push API
```

- **p95 end-to-end latency target: < 5 seconds** from race_control message to user notification
- Fallback: SSE (Server-Sent Events) for environments that block WebSocket
- Mobile push via Web Push API (VAPID keys, no native app required at launch)

### Consistency Heat-Maps
- Penalty severity distribution by `infraction_category` (x-axis) × `season` (y-axis)
- Group-by: steward panel chair, circuit, session type
- Automatic outlier detection: flag decisions >2 standard deviations from historical mean for that infraction type
- Drill-down: click any cell → list of individual incidents in that bucket

### Driver Penalty Points Cockpit
- Rolling 12-month penalty-point ledger per driver
- Expiration timeline (visual bar showing when each point expires)
- Race-ban risk projection: Poisson model on historical incident rate → P(reaching 12 points by end of season)
- Push alert when any driver crosses 8 points

### Performance Optimisations
- [ ] Precompute embeddings nightly (never on-demand)
- [ ] Cache top-k precedent lists per incident in Redis (TTL 24h)
- [ ] Edge-cache PDF text snippets in Cloudflare KV (sub-50ms retrieval)
- [ ] pgvector HNSW pre-warm on app startup
- [ ] Next.js ISR for historical decision pages (rebuild on edit only)
- [ ] PgBouncer connection pooling

### Phase 6 Milestone
> **p95 end-to-end "new investigation → precedent push" latency < 5 seconds.** All pages live. Mobile-responsive. Dark/light mode working.

---

## Phase 7 — API, MCP Server & Billing (Weeks 22–23)

**Objective:** Monetisation infrastructure, public API, and LLM agent integration.

### REST API (FastAPI)

Full OpenAPI 3.1 spec auto-generated. All endpoints versioned under `/v1/`.

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/v1/incidents` | Optional | List incidents with cursor-based pagination + all structured filters |
| GET | `/v1/incidents/:id` | Optional | Full multimodal incident record |
| POST | `/v1/precedents/search` | Required | Hybrid semantic + BM25 search, returns top-k with scores |
| POST | `/v1/penalty/predict` | Pro+ | Calibrated probability distribution + top-3 precedents + cited articles |
| GET | `/v1/consistency/heatmap` | Optional | Aggregate penalty distributions for visualisation |
| GET | `/v1/drivers/:code/penalty_points` | Optional | Rolling 12-month ledger + ban-risk projection |
| GET | `/v1/guidelines` | Optional | Browse guidelines with usage statistics |
| GET | `/v1/guidelines/:article/decisions` | Optional | All decisions citing this article |
| GET | `/v1/documents` | Optional | Raw FIA documents with full-text search |
| GET | `/v1/events/:season` | Optional | Season calendar with incident counts |
| WS | `/v1/live` | Pro+ | Real-time investigation push |

**Rate limits (token-bucket per API key):**

| Tier | API Calls/day | Search/day | Live Mode |
|---|---|---|---|
| Free | 100 | 10 | No |
| Pro ($29/mo) | 10,000 | Unlimited | Yes |
| Team ($499/mo) | Unlimited | Unlimited | Yes |
| Enterprise | Custom | Custom | Yes |

### MCP Server

```
GET /mcp/v1/manifest  →  MCP tool manifest
POST /mcp/v1/query    →  Grounded Q&A over F1 stewarding data
```

- Enables Claude / ChatGPT / other LLM agents to ask: "Did Norris get penalised at Austin 2024?" and receive a structured, cited answer
- Returns: answer text + incident records + guideline citations + confidence
- Rate-limited under the same API key tiers

### Auth & Billing
- [ ] **Clerk** integration: social logins (Google, GitHub), email/password, API key management
- [ ] **Stripe** integration: Free / Pro / Team / Enterprise subscription tiers
- [ ] Webhook: Stripe `customer.subscription.updated` → update `subscriptions` table → update API key rate limits
- [ ] API key management dashboard on `/api` page (create, revoke, view usage)

### Right-of-Review Builder (Team tier feature)
- [ ] Auto-identify evidence missing at original decision time (compare `team_radio_clips` + `lap_features` availability vs. decision `published_at`)
- [ ] Surface contradictory precedents: similar incidents with different outcomes
- [ ] Exportable PDF evidence pack: guideline articles + linked precedents + missing-evidence summary
- [ ] In-app annotation tool for Team subscribers to add private notes to incidents

### Steward Panel Variance Detector
- [ ] `steward_panels` table: panel chair + members per event
- [ ] Chi-squared / Fisher exact tests on penalty-type distributions per panel chair
- [ ] Surface on `/consistency` page as "variance analysis" (never as individual steward criticism)

```sql
CREATE TABLE steward_panels (
  panel_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id       UUID REFERENCES events(event_id),
  chair          TEXT NOT NULL,
  members        TEXT[] NOT NULL,
  driver_steward TEXT
);
```

### Design Partner Feedback Sprint
- [ ] Onboard 3 named F1 journalists as design partners
- [ ] Collect structured feedback via Notion survey: search quality, latency, missing features
- [ ] Iterate on search ranking and UI based on feedback

### Phase 7 Milestone
> **3 external journalists onboarded and providing active feedback.** API live with rate-limited tiers. MCP server working with Claude.

---

## Phase 8 — Launch (Week 24)

**Objective:** Public soft launch at a European GP weekend.

### Pre-Launch Checklist
- [ ] Legal review with media-rights lawyer: FOM audio/video linking policy confirmed
- [ ] DMCA takedown procedure documented and publicly listed in `LEGAL.md`
- [ ] Gambling disclaimer on all prediction pages and API responses
- [ ] Cookie consent banner (decline-by-default) deployed
- [ ] WCAG 2.1 AA accessibility audit passed
- [ ] Load test: k6 simulating 200 concurrent WebSocket subscribers + 50 simultaneous API calls + 10 concurrent PDF parse jobs
- [ ] Sentry, Grafana Cloud, PagerDuty all confirmed alerting
- [ ] BetterStack status page live at `status.racejudge.com`
- [ ] Lighthouse CI score: Performance ≥ 90, Accessibility ≥ 95

### Launch Sequence
- [ ] Deploy to production (`fly deploy --app racejudge-web`) in all three regions (LHR, IAD, GRU)
- [ ] DNS cutover to `racejudge.com`
- [ ] Open-source the FIA PDF scraper component on GitHub under MIT licence (separate repo `racejudge-scraper`)
- [ ] Publish long-form Substack/Medium article: "The F1 Stewarding Consistency Problem" (using RACEJUDGE data to show outlier decisions)
- [ ] Post on r/formula1 — time post to race weekend (maximum audience)
- [ ] Share with design-partner journalists for simultaneous coverage
- [ ] Post on F1 Twitter/X with example query results

### Post-Launch Monitoring (72h)
- [ ] Monitor Sentry error rate (alert if >1% of requests)
- [ ] Monitor Grafana: scrape lag, parse success rate, API p99 latency, WebSocket connections
- [ ] Monitor PagerDuty: respond to any missed-scrape alert within 15 min
- [ ] Collect user feedback via in-app prompt (Typeform embed)

### Phase 8 Milestone
> **Public launch. First external media coverage within 48 hours.**

---

## Post-Launch Roadmap

| Phase | Feature | Timeline | Gate |
|---|---|---|---|
| Phase 2 | F2/F3/Formula E expansion — same FIA decision structure, 3× addressable market | Months 7–9 | 500 WAU + 1 paying subscriber |
| Phase 3 | What-If Counterfactual Engine — "What if Piastri's Brazil 10s had been 5s?" Championship re-simulation | Months 10–12 | Team tier revenue positive |
| Phase 4 | Steward-Assist Plugin — private FIA intranet version surfacing top-5 precedents to stewards in real-time | Year 2 | FIA or team direct outreach |
| Phase 5 | CV Incident Detector — YOLOv10 + ByteTrack on legally-cleared onboard footage | Year 2 | FOM data access agreement |
| Phase 6 | Multilingual Coverage — Spanish, Italian, Japanese incident summaries | Year 2–3 | 10K WAU |

---

## Go/No-Go Gates

| Gate | Timing | Ship | Metric | Below Threshold |
|---|---|---|---|---|
| Stage 1 | End of Week 4 | Decision Index MVP (structured search, no ML) | 500 WAU within 60 days OR 3 named journalists referencing the tool | Pivot to narrower "penalty-points race-ban risk" tracker |
| Stage 2 | End of Week 14 | Multimodal linking + precedent retrieval | Recall@10 ≥ 0.80 AND ≥1 paying journalist or team within 90 days | Sunset prediction work; keep retrieval engine as free transparency utility |
| Stage 3 | End of Week 18 | Penalty prediction (public) | Macro-F1 ≥ 0.65, ECE < 0.05 | Keep classifier as internal beta; do NOT ship publicly if miscalibrated |

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| FOM takedown (video/audio) | Medium | High | Link-only to official clips. Host only OpenF1 public mp3s. DMCA procedure documented. Legal review before launch. |
| FIA changes PDF format | High | Medium | Parser versioning + regex fallback. Monitor document structure weekly. |
| OpenF1 radio coverage drops | High (confirmed) | Medium | Graceful degradation. Shift ML weight to telemetry + race_control text. |
| Miscalibrated predictions published | Medium | High | Stage 3 gate: ECE < 0.05 required. Show distributions only. Prominent disclaimers. |
| Gambling regulatory exposure | Low | High | No betting promotion. Geo-block live prediction in regulated jurisdictions. Disclaimers on all outputs. |
| Competitor ships first | Low | Medium | Emphasise missing axis: live mode, MCP server, multimodal linkage. Open-source scraper as moat-seed. |
| fia.com rate-limiting / blocking | Low | High | 1 req/5s limit. Aggressive caching. Consider reaching out to FIA for official feed. |
| Steward human factors unmeasurable | Certain | Medium | Be candid in UI. Show confidence intervals. Never false certainty. |

---

## Key Technology Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Vector DB | PostgreSQL pgvector (HNSW) | Single DB for structured + vector + time-series at this volume. Migrate to Qdrant if p99 > 200ms at >100K incidents. |
| Embedding model | BGE-M3 (1024-dim) | Multilingual, instruction-tuned. Best-in-class for domain fine-tuning via triplet loss. |
| LLM for classification | Llama-3-8B-Instruct LoRA | Open weights = fine-tunable on (incident_text, penalty) pairs. Smaller than 70B but sufficient for 7-class classification. |
| LLM for RAG | Llama-3.1-70B-Instruct (Modal/Together.ai) | Needed for reasoning quality. Hosted on Modal for pay-per-second burst. Cache outputs in Redis. |
| ASR | Faster-Whisper Large-V3 + LoRA | Best open-weights ASR. LoRA adapters for F1 vocabulary without full retraining. |
| Real-time transport | FastAPI WebSocket + Redis Pub/Sub | Sufficient for <5K concurrent. Migrate to Phoenix/Elixir Channels if fan-out exceeds 5K connections. |
| ETL orchestration | Prefect 3 | Python-native, DAG-first, cloud-managed. Simpler than Airflow for this team size. |
| GPU compute | Modal (pay-per-second) | Scales to zero between sessions. Avoids over-provisioning idle GPU capacity. |
| Object storage | Cloudflare R2 | Zero egress fees. Critical for serving audio/PDF at scale without surprise bills. |

---

## Monitoring Checklist (Post-Launch Steady State)

| Signal | Tool | Alert Threshold |
|---|---|---|
| Missed scrape during live session | PagerDuty | >30 min gap |
| API error rate | Sentry + Grafana | >5% of requests |
| WebSocket connection failures | Grafana | >10% failure rate |
| p99 API latency | Grafana | >500ms |
| PDF parse success rate | Grafana | <95% |
| Embedding computation lag | Grafana | >2h behind ingestion |
| Prediction ECE drift | Internal eval pipeline | ECE > 0.08 triggers re-calibration |

---

*Version 1.0 — May 2026 — Based on RACEJUDGE Project Brief v1.0*
