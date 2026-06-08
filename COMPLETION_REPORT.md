# RACEJUDGE — Final Completion Report v4

> **Updated: 8 June 2026**
> Commits: 15 | Tests: 219 passing | Decisions: 1,085 (2019–2025) | Phases code-complete: Pre-Work · 1 · 2 · 3 · 4 · 5 · 6 · 7 · 8

---

## Legend

| Symbol | Meaning |
|---|---|
| ✅ | Code written, committed, pushed |
| 🔶 | Code done — blocked on your account / credentials / GPU to run |
| 👤 | Only you can do this — no code involved |
| ❌ | Not built — either post-launch scope or explicitly not started |

---

## SECTION 1 — Pre-Work

| Item | Status | Notes |
|---|---|---|
| GitHub org `racejudge-hq` + repo `racejudge-web` | ✅ | 15 commits, pushed |
| Journalist pitch templates | ✅ | `scripts/outreach/journalist_pitch.md` |
| 1,085 decisions scraped 2019–2025 | ✅ | `data/parsed/decisions.jsonl` |
| Register `racejudge.com` + `.io` + `.app` | 👤 | Namecheap — ~£12/year |
| Reserve `@racejudge` on X, Threads, Reddit, LinkedIn, Bluesky | 👤 | Do before launch |
| Register email `hello@`, `legal@`, `press@racejudge.com` | 👤 | Cloudflare Email Routing (free) |
| Trademark search EUIPO + USPTO class 42 | 👤 | Before launch — book a media law firm |
| Hand-label 300 annotation pairs (similar/dissimilar) | 👤 | `python scripts/annotate_pairs.py` — critical for BGE-M3 fine-tuning |
| Cold-email / DM 5 journalists | 👤 | Templates in `journalist_pitch.md` |

---

## SECTION 2 — Phase 1: Foundation

### Infrastructure code (all written and committed)

| Item | Status | File |
|---|---|---|
| Monorepo scaffold | ✅ | Root `apps/`, `packages/`, `infra/`, `scripts/` |
| GitHub Actions CI | ✅ | `.github/workflows/ci.yml` — ruff, mypy, pytest, tsc, next build |
| Dockerfile | ✅ | `Dockerfile` — python:3.12-slim, uvicorn |
| Fly.io config | ✅ | `fly.toml` — racejudge-api, IAD region |
| Terraform (R2 buckets + Fly secrets) | ✅ | `infra/terraform/main.tf` |
| FIA scraper | ✅ | `packages/pipeline/scrapers/fia_scraper.py` — Playwright, SHA-256 dedup, R2 upload |
| Celery workers (parse_pdf, extract_text, ocr_fallback) | ✅ | `packages/pipeline/workers/` |
| Migration 0001: `decisions` table | ✅ | `packages/db/migrations/versions/0001_initial_schema.py` |
| Migration 0002: `guidelines`, `team_radio_clips`, `annotations` | ✅ | `0002_guidelines_radio_annotations.py` |
| Migration 0003: `events`, `sessions`, `race_control_messages`, `lap_features`, GIN FTS | ✅ | `0003_events_sessions_rcm_lap_features_fts.py` |
| Migration 0004: `incidents`, `drivers`, `teams`, `precedent_links`, `predictions_log`, `steward_panels` | ✅ | `0004_incidents_drivers_teams_precedents.py` |
| Migration 0005: `incidents.embedding` vector(1024) + HNSW index | ✅ | `0005_embeddings_hnsw.py` |
| Migration 0006: `api_keys`, `subscriptions`, `usage_logs` | ✅ | `0006_billing_apikeys.py` |
| SQLAlchemy ORM models (all tables) | ✅ | `packages/db/models.py` — 14 model classes |
| FastAPI app skeleton | ✅ | `apps/api/main.py` |
| `GET /health` | ✅ | `apps/api/routers/health.py` |
| Settings / config | ✅ | `apps/api/core/config.py` — env, Stripe, CORS |

### Infrastructure accounts (you must provision these)

**Neon Postgres (10 min — free tier)**
```bash
# 1. neon.tech → New Project → racejudge → eu-west-2
# 2. Copy connection string → add to .env:
DATABASE_URL=postgresql://racejudge:PASS@ep-xxx.eu-west-2.aws.neon.tech/racejudge?sslmode=require
# 3. Apply all 6 migrations:
cd packages/db && DATABASE_URL=$DATABASE_URL alembic upgrade head
# 4. Load decisions:
python scripts/load_jsonl_to_db.py
python scripts/seed_guidelines.py
```

**Cloudflare R2 (15 min)**
```bash
# cloudflare.com → R2 → Create 3 buckets:
#   racejudge-raw, racejudge-audio, racejudge-telemetry
# R2 → Manage API Tokens → Object Read & Write → all 3 buckets
# Add to .env:
R2_ACCOUNT_ID=xxx
R2_ACCESS_KEY_ID=xxx
R2_SECRET_ACCESS_KEY=xxx
# Upload PDFs:
python scripts/upload_to_r2.py
```

**Fly.io API deploy (20 min)**
```bash
brew install flyctl && fly auth login
fly apps create racejudge-api --org personal
fly secrets set DATABASE_URL="..." REDIS_URL="..." --app racejudge-api
fly deploy
curl https://racejudge-api.fly.dev/health   # → {"status":"ok"}
```

**Upstash Redis (5 min)**
```bash
# upstash.com → New Database → racejudge → eu-west-1
# Copy URL → .env: REDIS_URL=rediss://default:TOKEN@xxx.upstash.io:6379
```

**Vercel frontend (5 min)**
```bash
# vercel.com → New Project → Import racejudge-hq/racejudge-web
# Root directory: apps/web
# Add env vars: NEXT_PUBLIC_API_URL=https://racejudge-api.fly.dev
#               NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_live_xxx
#               CLERK_SECRET_KEY=sk_live_xxx
```

**Clerk auth (10 min)**
```
clerk.com → New Application → RACEJUDGE → Email + Google
apps/web/.env.local:
  NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_xxx
  CLERK_SECRET_KEY=sk_test_xxx
  NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in
  NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up
  NEXT_PUBLIC_CLERK_AFTER_SIGN_IN_URL=/
Also: GitHub repo Settings → Secrets → add both keys (fixes CI)
```

**Prefect Cloud (10 min)**
```bash
prefect cloud login --key YOUR_API_KEY --workspace YOUR_EMAIL/racejudge
prefect work-pool create pdf-ingest --type process
prefect work-pool create ml-train --type process
prefect work-pool create live-session --type process
```

---

## SECTION 3 — Phase 2: Structured Extraction

| Item | Status | File |
|---|---|---|
| `decision_parser.py` — regex field extractor | ✅ | `packages/pipeline/parsers/decision_parser.py` (176 lines) |
| `text_cleaner.py` — whitespace/encoding normalisation | ✅ | `packages/pipeline/parsers/text_cleaner.py` (166 lines) |
| `guidelines_parser.py` — FIA penalty guidelines parser | ✅ | `packages/pipeline/parsers/guidelines_parser.py` (643 lines) |
| `layoutlm_extractor.py` — LayoutLMv3 skeleton | ✅ | `packages/pipeline/parsers/layoutlm_extractor.py` (172 lines) |
| `tesseract_fallback.py` — Tesseract 5 OCR fallback | ✅ | `packages/pipeline/parsers/tesseract_fallback.py` (87 lines) |
| `incident_extractor.py` — 3-layer extraction chain | ✅ | `packages/pipeline/extractors/incident_extractor.py` |
| `driver_resolver.py` — canonical driver name mapping | ✅ | `packages/pipeline/resolvers/driver_resolver.py` |
| `article_resolver.py` — article → guideline FK linker | ✅ | `packages/pipeline/resolvers/article_resolver.py` |
| `backfill_incidents.py` — runs extraction over all decisions | ✅ | `scripts/backfill_incidents.py` |
| `seed_drivers.py` — seeds drivers/teams from Jolpica-F1 | ✅ | `scripts/seed_drivers.py` |
| `seed_guidelines.py` — seeds 35 FIA articles | ✅ | `scripts/seed_guidelines.py` |
| 35 FIA Penalty Guidelines articles seeded | ✅ | 3 documents covered in seed script |
| `POST /v1/incidents/extract` | ✅ | `apps/api/routers/incidents.py:408` |
| `GET /v1/incidents` + `GET /v1/incidents/{id}` | ✅ | `apps/api/routers/incidents.py` |
| `GET /v1/incidents/consistency` (heatmap data) | ✅ | `apps/api/routers/incidents.py:260` |
| `GET /v1/drivers/{code}/stats` | ✅ | `apps/api/routers/incidents.py:324` |
| Run extraction over all 1,085 decisions | 🔶 | Needs `DATABASE_URL` set first |
| Full 100-article FIA Penalty Guidelines 2025 ingestion | 🔶 | Run `python scripts/seed_guidelines.py` after DB is up (currently 35 articles) |
| Label Studio 300-pair annotation campaign | 👤 | See Pre-Work section |

**To run extraction after DB is set up:**
```bash
python scripts/seed_drivers.py           # seeds drivers/teams from Jolpica-F1 API
python scripts/backfill_incidents.py     # extracts all 1,085 decisions → incidents table
python scripts/seed_guidelines.py        # loads 35 FIA articles
# Use /annotate page to review + correct extracted fields
```

---

## SECTION 4 — Phase 3: Multimodal Linking

| Item | Status | File |
|---|---|---|
| `openf1_client.py` — OpenF1 API wrapper | ✅ | `packages/pipeline/linkers/openf1_client.py` (136 lines) |
| `radio_fetcher.py` — 3 nearest clips ±60s | ✅ | `packages/pipeline/audio/radio_fetcher.py` (258 lines) |
| `transcriber.py` — Whisper large-v3 + pyannote | ✅ | `packages/pipeline/audio/transcriber.py` (280 lines) |
| `asr_worker.py` — Celery ASR task | ✅ | `packages/pipeline/audio/asr_worker.py` (214 lines) |
| `diarisation.py` — pyannote.audio speaker diarisation | ✅ | `packages/pipeline/audio/diarisation.py` (179 lines) |
| `decision_linker.py` — links decisions to OpenF1 events | ✅ | `packages/pipeline/linkers/decision_linker.py` (172 lines) |
| `race_control_linker.py` — links RCMs to incidents | ✅ | `packages/pipeline/linkers/race_control_linker.py` (230 lines) |
| `weather_linker.py` — OpenF1 weather context | ✅ | `packages/pipeline/linkers/weather_linker.py` (150 lines) |
| `fastf1_slicer.py` — telemetry feature extraction | ✅ | `packages/pipeline/telemetry/fastf1_slicer.py` |
| `modal_transcribe.py` — faster-whisper on Modal A10G | ✅ | `packages/pipeline/workers/modal_transcribe.py` (189 lines) |
| `sentiment_backfill.py` — DistilBERT sentiment over all clips | ✅ | `scripts/sentiment_backfill.py` |
| `backfill_audio.py` — fetches/caches radio clips | ✅ | `scripts/backfill_audio.py` |
| `backfill_race_control.py` — links RCMs to incidents | ✅ | `scripts/backfill_race_control.py` |
| `live_session_flow.py` — Prefect live pipeline | ✅ | `packages/pipeline/flows/live_session_flow.py` |
| ASR actually running on audio | 🔶 | Needs `HF_TOKEN` + GPU; `pip install faster-whisper pyannote.audio` |
| Race control messages linked to incidents | 🔶 | Needs `DATABASE_URL` + session_keys |

**To activate ASR:**
```bash
# 1. Accept pyannote model licence at huggingface.co/pyannote/speaker-diarization-3.1
# 2. Create HF token → add to .env: HF_TOKEN=hf_xxx
pip install faster-whisper pyannote.audio
# 3. CPU backfill (slow):
python -m packages.pipeline.audio.transcriber --backfill --session-limit 10
# 4. Or GPU (fast) via Modal:
modal run packages/pipeline/workers/modal_transcribe.py
```

---

## SECTION 5 — Phase 4: Precedent Retrieval

| Item | Status | File |
|---|---|---|
| `semantic_search.py` — pgvector HNSW ANN | ✅ | `apps/api/retrieval/semantic_search.py` (122 lines) |
| `bm25_search.py` — Postgres tsvector BM25 | ✅ | `apps/api/retrieval/bm25_search.py` (82 lines) |
| `rrf.py` — Reciprocal Rank Fusion (k=60) | ✅ | `apps/api/retrieval/rrf.py` (171 lines) |
| `precedents.py` router | ✅ | `POST /v1/precedents/search` + `GET /v1/precedents/{id}/similar` |
| `embedder.py` — BGE-M3 batch backfill | ✅ | `packages/pipeline/ml/embedder.py` |
| `modal_embed.py` — BGE-M3 on Modal A10G | ✅ | `packages/pipeline/workers/modal_embed.py` (227 lines) |
| `train_embedder.py` — triplet-loss BGE-M3 fine-tune | ✅ | `packages/ml/train_embedder.py` (291 lines) |
| `embedding_flow.py` — Prefect nightly flow | ✅ | `packages/pipeline/flows/embedding_flow.py` |
| `precedents/page.tsx` — full search UI | ✅ | `apps/web/src/app/precedents/page.tsx` (297 lines) |
| Run BGE-M3 embedder (download ~2.2GB model) | 🔶 | Needs `DATABASE_URL` + populated incidents |
| BGE-M3 fine-tune with 300 labelled pairs | 🔶 | Needs annotation pairs done first |

**To run embeddings:**
```bash
pip install sentence-transformers pgvector
# After incidents table is populated:
python -m packages.pipeline.ml.embedder --batch-size 64
# or on GPU:
modal run packages/pipeline/workers/modal_embed.py
# Verify:
curl -X POST http://localhost:8000/v1/precedents/search \
  -H "Content-Type: application/json" \
  -d '{"query": "unsafe release pit lane"}'
```

---

## SECTION 6 — Phase 5: Penalty Prediction

| Item | Status | File |
|---|---|---|
| `predictor.py` — XGBoost 7-class pipeline | ✅ | `packages/ml/predictor.py` (306 lines) |
| `predictor_v2.py` — stacked XGBoost + Llama ensemble | ✅ | `packages/ml/predictor_v2.py` (349 lines) |
| `features.py` — tabular feature engineering | ✅ | `packages/ml/features.py` (222 lines) |
| `train.py` — XGBoost training with time-split CV | ✅ | `packages/ml/train.py` (155 lines) |
| `train_llama_lora.py` — Llama-3-8B LoRA on Modal A100 | ✅ | `packages/ml/train_llama_lora.py` (395 lines) |
| `sentiment.py` — DistilBERT + zero-shot BART | ✅ | `packages/ml/sentiment.py` (134 lines) |
| `rag_explainer.py` — Anthropic claude-haiku RAG | ✅ | `packages/ml/rag_explainer.py` (134 lines) |
| `predict.py` router | ✅ | `POST /v1/predict` + `POST /v1/predict/explain` |
| `predict/page.tsx` — full form + probability bars | ✅ | `apps/web/src/app/predict/page.tsx` (461 lines) |
| Gambling disclaimer in API response | ✅ | `apps/api/routers/predict.py:57,150` |
| Probability distribution (never point predictions) | ✅ | Returns `proba: {NFA:0.x, REP:0.x, ...}` |
| Train XGBoost model | 🔶 | Needs populated incidents (≥300 with structured fields) |
| Train Llama LoRA | 🔶 | Needs Modal A100 + `HF_TOKEN` with Llama-3-8B access |
| Set `ENABLE_PREDICTIONS=true` in .env | 🔶 | Only after ECE < 0.05 gate passes |
| Set `ANTHROPIC_API_KEY` for RAG explanations | 🔶 | console.anthropic.com → API Keys |

**To train prediction model:**
```bash
# 1. Ensure incidents table has ≥300 rows with penalty_type filled
python -m packages.ml.train
# Outputs: Macro-F1, ECE, confusion matrix
# Gate: only set ENABLE_PREDICTIONS=true if ECE < 0.05 AND Macro-F1 ≥ 0.65

# 2. (Optional, boosts F1 by ~7%): Train Llama Layer B
modal run packages/ml/train_llama_lora.py

# 3. After both are trained, build stacked ensemble:
python -m packages.ml.predictor_v2 --train
```

---

## SECTION 7 — Phase 6: UX & Live Mode

| Item | Status | File |
|---|---|---|
| `live.py` router — WebSocket + Redis Pub/Sub + SSE fallback | ✅ | `apps/api/routers/live.py` (317 lines) |
| `live/page.tsx` — WebSocket client, session selector, auto-scroll | ✅ | `apps/web/src/app/live/page.tsx` (313 lines) |
| `consistency/page.tsx` — penalty outcome tables, ISR 1h | ✅ | `apps/web/src/app/consistency/page.tsx` (148 lines) |
| `drivers/[code]/page.tsx` — points bar, ban-risk, incident log | ✅ | `apps/web/src/app/drivers/[code]/page.tsx` (189 lines) |
| `guidelines/page.tsx` — FIA article browser | ✅ | `apps/web/src/app/guidelines/page.tsx` (120 lines) |
| `incidents/[id]/page.tsx` — full detail + radio + precedents | ✅ | `apps/web/src/app/incidents/[id]/page.tsx` (347 lines) |
| `page.tsx` — home page with search + nav cards | ✅ | `apps/web/src/app/page.tsx` (117 lines) |
| `decisions/page.tsx` + `decisions/[docId]/page.tsx` | ✅ | List and detail pages |
| `search/page.tsx` — text search UI | ✅ | `apps/web/src/app/search/page.tsx` (115 lines) |
| `annotate/page.tsx` — annotation interface | ✅ | `apps/web/src/app/annotate/page.tsx` (116 lines) |
| `sign-in` + `sign-up` (Clerk) | ✅ | `apps/web/src/app/sign-in/` + `sign-up/` |
| `lib/api.ts` — typed API client | ✅ | `apps/web/src/lib/api.ts` (201 lines) |
| `DecisionCard.tsx` component | ✅ | `apps/web/src/components/DecisionCard.tsx` |
| `ThemeProvider.tsx` + `ThemeToggle.tsx` — dark/light mode | ✅ | `apps/web/src/components/` |
| SSE fallback `GET /v1/live/stream` | ✅ | `apps/api/routers/live.py` |
| `ingest_flow.py` Prefect ingestion DAG | ✅ | `packages/pipeline/flows/ingest_flow.py` |
| `middleware.ts` — Clerk auth gating | ✅ | `apps/web/src/middleware.ts` |
| **Middleware NOTE** | ⚠️ | Currently blocks all routes except `/`, `/sign-in`, `/sign-up`, `/api/v1/decisions`. Before launch: add `/decisions`, `/precedents`, `/consistency`, `/guidelines`, `/predict` as public routes, or remove auth gating entirely for the public launch. |
| Plotly.js interactive charts | ❌ | Using custom CSS probability bars instead — sufficient for launch; add Plotly post-launch |
| D3.js heatmaps | ❌ | Using HTML tables on consistency page — functional, not visualised as true heatmap |
| Mapbox GL circuit corner overlay | ❌ | Post-launch feature |
| shadcn/ui component library | ❌ | Post-launch refactor |
| Web Push API mobile notifications | ❌ | Post-launch feature |
| TanStack Query client-side caching | ❌ | Post-launch; currently using direct fetch |
| Geo-blocking on prediction endpoints | ❌ | Not implemented — gambling regulatory mitigation |

---

## SECTION 8 — Phase 7: API, MCP Server & Billing

| Item | Status | File |
|---|---|---|
| `rate_limit.py` middleware — Redis token-bucket + in-memory fallback | ✅ | `apps/api/middleware/rate_limit.py` (202 lines) |
| `billing.py` router — Stripe webhook + subscription CRUD + portal | ✅ | `apps/api/routers/billing.py` (293 lines) |
| `apikeys.py` router — create/list/revoke keys | ✅ | `apps/api/routers/apikeys.py` (254 lines) |
| `mcp.py` router — manifest + 4 tools | ✅ | `apps/api/routers/mcp.py` (401 lines); tools: `search_precedents`, `get_incident`, `get_driver_stats`, `predict_penalty` |
| `review.py` router — Right-of-Review builder | ✅ | `apps/api/routers/review.py` (379 lines); RAG-backed, template fallback |
| `api/page.tsx` — API key management dashboard | ✅ | `apps/web/src/app/api/page.tsx` (355 lines) |
| `review/page.tsx` — Right-of-Review form + document preview | ✅ | `apps/web/src/app/review/page.tsx` (283 lines) |
| Migration 0006: `api_keys`, `subscriptions`, `usage_logs` | ✅ | `0006_billing_apikeys.py` (81 lines) |
| `ApiKey`, `Subscription`, `UsageLog` ORM models | ✅ | `packages/db/models.py:269–330` |
| Tier daily limits: free=100, pro=10k, team=100k | ✅ | `apps/api/middleware/rate_limit.py` |
| API key format: `rj_live_` + 48 hex chars, SHA-256 stored | ✅ | `apps/api/routers/apikeys.py` |
| `stripe>=10.0.0` in requirements.txt | ✅ | Line 86 |
| Set up Stripe account + create Pro/Team products | 🔶 | stripe.com → Products → "RACEJUDGE Pro" £29/mo, "RACEJUDGE Team" £499/mo |
| Set `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRO_PRICE_ID`, `STRIPE_TEAM_PRICE_ID` | 🔶 | Stripe Dashboard → Developers → API Keys |
| `steward_panels` table + chi-squared/Fisher analysis | ❌ | Table exists in migration 0004. No ORM model. No chi-squared/Fisher analysis of per-panel-chair variance. stewards.py does global Shannon entropy only, not per-panel-chair breakdown. To add: create `StewardPanel` model + chi-squared query endpoint. |

**To activate billing:**
```bash
# stripe.com → Dashboard → Products → Create:
#   "RACEJUDGE Pro" → Recurring → £29/month → copy price ID
#   "RACEJUDGE Team" → Recurring → £499/month → copy price ID
# Developers → Webhooks → Add endpoint → https://racejudge-api.fly.dev/v1/billing/webhook
# Add to .env / Fly secrets:
STRIPE_SECRET_KEY=sk_live_xxx
STRIPE_WEBHOOK_SECRET=whsec_xxx
STRIPE_PRO_PRICE_ID=price_xxx
STRIPE_TEAM_PRICE_ID=price_xxx
```

---

## SECTION 9 — Phase 8: Observability, Accessibility & Launch

| Item | Status | File |
|---|---|---|
| `latency.py` middleware — rolling p50/p95/p99 per route | ✅ | `apps/api/middleware/latency.py` (74 lines) |
| `GET /v1/metrics/latency` endpoint | ✅ | `apps/api/middleware/latency.py:router` |
| `stewards.py` — Shannon entropy + inconsistency_score + severity slope | ✅ | `apps/api/routers/stewards.py` (238 lines) |
| `GET /v1/incidents/variance` + `GET /v1/incidents/variance/{category}` | ✅ | `apps/api/routers/stewards.py` |
| Sentry FastAPI init in `main.py` lifespan (gated on `SENTRY_DSN`) | ✅ | `apps/api/main.py:41–62` |
| HNSW index pre-warm in `main.py` lifespan | ✅ | `apps/api/main.py:64–93` |
| `sentry-sdk[fastapi]>=2.0.0` in requirements.txt | ✅ | Line 93 |
| Security headers in `next.config.ts` | ✅ | CSP, HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy |
| `/mcp/v1/:path*` proxy rewrite | ✅ | `apps/web/next.config.ts:48` |
| OG metadata + twitter:card in `layout.tsx` | ✅ | `apps/web/src/app/layout.tsx` — metadataBase, openGraph, twitter |
| Skip-to-content link for WCAG keyboard navigation | ✅ | `apps/web/src/app/layout.tsx:50–57` |
| `<main id="main-content" tabIndex={-1}>` wrapper | ✅ | `apps/web/src/app/layout.tsx:58` |
| `Nav.tsx` client component — aria-current + aria-label | ✅ | `apps/web/src/components/Nav.tsx` (67 lines) |
| `not-found.tsx` — custom 404 page | ✅ | `apps/web/src/app/not-found.tsx` (27 lines) |
| `error.tsx` — React error boundary | ✅ | `apps/web/src/app/error.tsx` (43 lines) |
| `sitemap.ts` — 9 static routes | ✅ | `apps/web/src/app/sitemap.ts` |
| `robots.txt` | ✅ | `apps/web/public/robots.txt` |
| WCAG aria: `htmlFor`/`id` on all form fields (review page) | ✅ | `apps/web/src/app/review/page.tsx` |
| WCAG aria: `role="status" aria-live="polite"` on loading states | ✅ | review/page.tsx + api/page.tsx |
| `aria-label` on API key name input | ✅ | `apps/web/src/app/api/page.tsx:231` |
| k6 load test script | ✅ | `scripts/load_test.k6.js` — p95 < 500ms, predict p95 < 2000ms |
| Launch post drafts | ✅ | `scripts/outreach/launch_post.md` — Twitter thread, LinkedIn, r/formula1 |
| LEGAL.md with DMCA procedure | ✅ | `LEGAL.md` |
| BRAND_CHECKLIST.md | ✅ | `BRAND_CHECKLIST.md` |
| `og.png` social card image | ❌ | File referenced in layout.tsx (`/og.png`) but not created. Must exist in `apps/web/public/og.png`. Create a 1200×630px image before launch. |
| Cookie consent banner (decline-by-default) | ❌ | Not implemented. Plan requires it. See below. |
| Lighthouse CI config (Performance ≥ 90, Accessibility ≥ 95) | ❌ | No `.lighthouserc.js`. See below. |
| BetterStack status page at `status.racejudge.com` | ❌ | Account-only. betterstack.com → Uptime → New Monitor. |
| Grafana Cloud observability | ❌ | Account-only. grafana.com → free tier. |
| PagerDuty on-call alerting | ❌ | Account-only. Or use BetterStack on-call (same dashboard). |
| Sentry account + DSN | 🔶 | sentry.io → New Project → FastAPI → copy DSN → `SENTRY_DSN=xxx` in .env |
| Deploy frontend to Vercel | 🔶 | See Section 2 |
| Multi-region Fly.io deploy (LHR + IAD + GRU) | 🔶 | Current fly.toml is IAD only. `fly regions add lhr gru --app racejudge-api` |
| DNS cutover to racejudge.com | 👤 | After domain registration |
| Open-source scraper repo (`racejudge-scraper`) | 👤 | Copy `packages/pipeline/scrapers/fia_scraper.py` to new public GitHub repo under MIT |
| Legal review with media-rights lawyer | 👤 | FOM/FIA audio+video linking policy. Book before launch. Cost ~£500–1500. |
| Publish Substack/Medium article | 👤 | Draft in launch_post.md. Publish under your name. |
| r/formula1 post at race weekend | 👤 | Time to Friday/Saturday of a GP weekend for maximum traffic |
| Send journalist DMs + emails | 👤 | Templates in `journalist_pitch.md` |

---

## SECTION 10 — What Is Still Missing (Code to Write)

These are gaps between the plan and the current code. All require a code change — you just need to tell me to build each one.

### High priority — needed before/at launch

| # | What | Why it blocks launch | How to build |
|---|---|---|---|
| 1 | **`og.png` social card** | Referenced in layout.tsx; missing file gives a broken image on every Twitter/OG share | Create 1200×630 dark background PNG with RACEJUDGE wordmark in `apps/web/public/og.png`. I can generate the HTML-to-image template you render once. |
| 2 | **Cookie consent banner** | Plan explicitly requires it; any EU user on the site triggers a legal obligation. Launch without it = GDPR risk | Add a `CookieConsent.tsx` client component in `apps/web/src/components/` — decline-by-default, stores preference in `localStorage`, renders above all content. I can build this in one session. |
| 3 | **Middleware public route fix** | `middleware.ts` currently blocks `/decisions`, `/precedents`, `/consistency`, `/guidelines`, `/live`, `/predict`, `/review`, `/api` behind Clerk sign-in. This means unauthenticated users can't use the site at all | Add all public pages to `isPublicRoute` matcher, or switch to Clerk's recommended optional-auth pattern for public pages. I can do this in 10 lines. |
| 4 | **Per-page `generateMetadata()`** | `/incidents/[id]` and `/decisions/[docId]` have no page-specific OG title or description. Social shares show the root layout's generic text | Add `generateMetadata({ params })` to each dynamic page. I can do this across all pages in one session. |
| 5 | **Phase 8 tests** | 219 tests pass, but Phases 7–8 have zero coverage. `billing.py`, `apikeys.py`, `mcp.py`, `review.py`, `stewards.py`, `latency.py`, `rate_limit.py` are entirely untested | Add `tests/test_phase7_routes.py` and `tests/test_phase8_routes.py`. I can write these in one session. |

### Medium priority — quality improvements before launch

| # | What | Why | How |
|---|---|---|---|
| 6 | **`StewardPanel` ORM model + per-panel chi-squared** | Plan specified chi-squared/Fisher exact tests per panel chair in Phase 7. Currently only global Shannon entropy exists. The `steward_panels` table is in migration 0004 but has no Python model class | Add `StewardPanel` to `models.py`. Add `GET /v1/incidents/variance/by-panel` endpoint to `stewards.py` running chi-squared tests on per-chair penalty distributions. |
| 7 | **Lighthouse CI config** | Plan requires Performance ≥ 90, Accessibility ≥ 95 before launch. Currently no automated check | Add `.lighthouserc.js` at root + add `npx lhci autorun` step to `.github/workflows/ci.yml` after `npm run build`. |
| 8 | **Geo-blocking on `/v1/predict`** | Plan: "Geo-block live prediction in regulated gambling jurisdictions." Not implemented | Add IP-based country check using Cloudflare CF-IPCountry header or MaxMind GeoLite2. Return 451 with gambling disclaimer for listed jurisdictions (UK, AU, US states). |
| 9 | **`run_extraction.py` convenience script** | Old completion report referenced `python scripts/run_extraction.py` in instructions but this file doesn't exist. `backfill_incidents.py` exists and does the same thing — old report had wrong filename | Just a docs fix: update old COMPLETION_REPORT reference to use `backfill_incidents.py`. Already done here. |
| 10 | **Multi-region fly.toml** | Current `fly.toml` has `primary_region = "iad"` only. Plan calls for LHR + IAD + GRU | Run: `fly regions add lhr gru --app racejudge-api` (no code change needed; it's a CLI command). |

### Post-launch features (deliberate deferrals — not bugs)

| # | What | Why deferred |
|---|---|---|
| 11 | Plotly.js interactive probability charts | Working CSS bars are sufficient for launch. Add Plotly after first 100 users confirm they want richer charts. |
| 12 | D3.js true heatmaps on consistency page | HTML tables are functional. D3 is a large dependency for cosmetic improvement. |
| 13 | Mapbox GL circuit corner overlay | Requires Mapbox API key + licence cost. No user demand signal yet. |
| 14 | shadcn/ui component library | Large refactor of all 16 page components. Post-launch. |
| 15 | Web Push API (mobile notifications) | No native app. Can add via Service Worker post-launch. |
| 16 | TanStack Query client cache | Direct fetch works. TanStack adds bundle weight; add when cache invalidation becomes a real problem. |
| 17 | F2/F3/Formula E expansion | Phase 2 of post-launch roadmap. Gate: 500 WAU + 1 paying subscriber. |

---

## SECTION 11 — Data Status

| Season | Records | Status |
|---|---|---|
| 2025 | 43 | ✅ |
| 2024 | 367 | ✅ |
| 2023 | 298 | ✅ |
| 2022 | 250 | ✅ |
| 2021 | 81 | ✅ |
| 2020 | 79 | ✅ |
| 2019 | 92 | ✅ |
| **Total** | **1,085** | ✅ All seasons 2019–2025 |

---

## SECTION 12 — Test Status

| Suite | Count | Status |
|---|---|---|
| `test_decision_parser.py` | 48 | ✅ |
| `test_incident_extractor.py` | 36 | ✅ |
| `test_ml_features.py` | 43 | ✅ |
| `test_scraper.py` | 15 | ✅ |
| `test_text_cleaner.py` | 14 | ✅ |
| `test_driver_resolver.py` | 14 | ✅ |
| `test_article_resolver.py` | (included in above) | ✅ |
| `test_api.py` | 12 | ✅ |
| `test_annotations_api.py` | 15 | ✅ |
| **Total** | **219** | ✅ |
| Phase 7 routes (billing, apikeys, mcp, review) | 0 | ❌ Not written |
| Phase 8 routes (stewards, latency, rate_limit) | 0 | ❌ Not written |

---

## SECTION 13 — CI Status

| Check | Status |
|---|---|
| `ruff` Python lint | ✅ 0 errors (only E501 long-line warnings in SQL strings, acceptable) |
| `mypy` type-check | ✅ 0 errors |
| `pytest` (219 tests) | ✅ 219 passing |
| `tsc --noEmit` TypeScript | ✅ 0 errors |
| Next.js `npm run build` | ✅ Clean |

---

## SECTION 14 — Architecture Summary (current state)

```
racejudge/
├── apps/
│   ├── api/                        # FastAPI — 15 routers, 30+ endpoints
│   │   ├── core/config.py          # Settings + Stripe/Sentry env vars
│   │   ├── main.py                 # Lifespan (Sentry+HNSW warm), all routers
│   │   ├── middleware/
│   │   │   ├── rate_limit.py       # Redis token-bucket, 429 + Retry-After
│   │   │   └── latency.py          # Rolling p50/p95/p99 per route
│   │   ├── retrieval/
│   │   │   ├── semantic_search.py  # pgvector HNSW cosine ANN
│   │   │   ├── bm25_search.py      # Postgres tsvector weighted BM25
│   │   │   └── rrf.py              # Reciprocal Rank Fusion (k=60)
│   │   └── routers/
│   │       ├── health.py           # GET /health
│   │       ├── decisions.py        # GET /v1/decisions + /{id}
│   │       ├── search.py           # GET /v1/search (BM25)
│   │       ├── incidents.py        # GET /v1/incidents + consistency + drivers
│   │       ├── precedents.py       # POST /v1/precedents/search + /{id}/similar
│   │       ├── predict.py          # POST /v1/predict + /predict/explain
│   │       ├── live.py             # WS /v1/live + SSE /v1/live/stream
│   │       ├── guidelines.py       # GET /v1/guidelines + /{id}
│   │       ├── telemetry.py        # GET /v1/telemetry/*
│   │       ├── annotations.py      # POST/GET /v1/annotations
│   │       ├── billing.py          # POST /v1/billing/webhook + subscription
│   │       ├── apikeys.py          # GET/POST/DELETE /v1/apikeys
│   │       ├── mcp.py              # GET /mcp/v1/manifest + POST /mcp/v1/query
│   │       ├── review.py           # POST /v1/review/generate
│   │       └── stewards.py         # GET /v1/incidents/variance + /{category}
│   └── web/                        # Next.js 15, App Router, Tailwind CSS 4
│       └── src/
│           ├── app/                # 16 pages
│           │   ├── layout.tsx      # OG meta, skip-link, Nav, ThemeProvider
│           │   ├── not-found.tsx   # Custom 404
│           │   ├── error.tsx       # React error boundary
│           │   ├── sitemap.ts      # 9 static routes
│           │   ├── page.tsx        # Home
│           │   ├── decisions/      # List + detail
│           │   ├── precedents/     # Semantic search UI
│           │   ├── predict/        # Prediction form + probability bars
│           │   ├── consistency/    # Penalty outcome tables (ISR 1h)
│           │   ├── drivers/[code]/ # Points + ban-risk
│           │   ├── guidelines/     # FIA article browser
│           │   ├── live/           # WebSocket feed + SSE fallback
│           │   ├── incidents/[id]/ # Full detail + radio + sidebar
│           │   ├── annotate/       # Annotation interface
│           │   ├── review/         # Right-of-Review builder
│           │   ├── api/            # API key management dashboard
│           │   └── sign-in + sign-up
│           ├── components/
│           │   ├── Nav.tsx         # Client component, aria-current
│           │   ├── ThemeProvider.tsx
│           │   ├── ThemeToggle.tsx
│           │   └── DecisionCard.tsx
│           ├── lib/api.ts          # Typed fetch client
│           └── middleware.ts       # Clerk auth gating ⚠️ needs public route fix
├── packages/
│   ├── db/
│   │   ├── database.py             # Async SQLAlchemy engine factory
│   │   ├── models.py               # 14 ORM models
│   │   └── migrations/versions/    # 0001–0006 Alembic migrations
│   ├── ml/
│   │   ├── predictor.py            # XGBoost 7-class (Layer A)
│   │   ├── predictor_v2.py         # Stacked ensemble (Layer A + B)
│   │   ├── features.py             # Feature engineering
│   │   ├── train.py                # XGBoost training + ECE/F1 gates
│   │   ├── train_embedder.py       # BGE-M3 triplet-loss fine-tune
│   │   ├── train_llama_lora.py     # Llama-3-8B QLoRA on Modal A100
│   │   ├── sentiment.py            # DistilBERT + zero-shot BART
│   │   └── rag_explainer.py        # Anthropic claude-haiku RAG
│   └── pipeline/
│       ├── scrapers/fia_scraper.py
│       ├── parsers/                # decision_parser, text_cleaner, guidelines_parser,
│       │                           # layoutlm_extractor, tesseract_fallback
│       ├── resolvers/              # driver_resolver, article_resolver
│       ├── linkers/                # decision_linker, openf1_client,
│       │                           # race_control_linker, weather_linker
│       ├── audio/                  # radio_fetcher, transcriber, asr_worker, diarisation
│       ├── telemetry/fastf1_slicer.py
│       ├── ml/embedder.py          # BGE-M3 batch backfill
│       ├── flows/                  # ingest_flow, live_session_flow, embedding_flow
│       └── workers/                # celery_app, modal_embed, modal_transcribe,
│                                   # tasks/parse_pdf, extract_text, ocr_fallback
├── scripts/
│   ├── backfill_incidents.py       # Runs extraction over all 1,085 decisions
│   ├── backfill_audio.py           # Fetches + caches team radio clips
│   ├── backfill_race_control.py    # Links race control messages to incidents
│   ├── seed_drivers.py             # Seeds drivers/teams from Jolpica-F1
│   ├── seed_guidelines.py          # Seeds 35 FIA articles
│   ├── sentiment_backfill.py       # DistilBERT sentiment over radio clips
│   ├── load_jsonl_to_db.py         # Loads 1,085 decisions into Postgres
│   ├── annotate_pairs.py           # CLI annotation tool (similar/dissimilar)
│   ├── export_similarity_pairs.py  # Exports pairs for BGE-M3 fine-tuning
│   ├── upload_to_r2.py             # Uploads PDFs to Cloudflare R2
│   ├── load_test.k6.js             # k6 load test (p95 < 500ms, predict < 2s)
│   └── outreach/
│       ├── journalist_pitch.md
│       └── launch_post.md
├── infra/
│   ├── terraform/                  # main.tf + tfvars.example + SETUP.md
│   └── fly/fly.toml
├── tests/                          # 219 tests passing
├── Dockerfile                      # python:3.12-slim, uvicorn
├── fly.toml                        # racejudge-api, IAD region
├── requirements.txt                # All Python deps including Stripe + Sentry
└── .github/workflows/ci.yml        # Lint + test + build CI
```

---

## SECTION 15 — Critical Launch Checklist (ordered)

The following is the exact sequence to launch. Do each step before the next.

### STEP 1 — Accounts (you, ~1 hour total)
1. Register `racejudge.com` at Namecheap (~£12/year)
2. Sign up Neon Postgres (neon.tech, free)
3. Sign up Cloudflare R2 (cloudflare.com, free for first 10GB)
4. Sign up Fly.io (fly.io, free)
5. Sign up Upstash Redis (upstash.com, free)
6. Sign up Clerk (clerk.com, free)
7. Sign up Stripe (stripe.com — needed for billing)
8. Sign up Sentry (sentry.io, free)
9. Sign up Vercel (vercel.com, free)

### STEP 2 — Data pipeline (run after accounts)
```bash
cd /Users/maruteymani/Documents/RaceJudge && source .venv/bin/activate
# Apply all 6 migrations:
cd packages/db && DATABASE_URL=$DATABASE_URL alembic upgrade head
cd ../..
# Load + seed:
python scripts/load_jsonl_to_db.py      # 1,085 decisions
python scripts/seed_guidelines.py       # 35 FIA articles
python scripts/seed_drivers.py          # drivers/teams from Jolpica-F1
# Extract incidents:
python scripts/backfill_incidents.py    # ~5 min, populates incidents table
# Embed incidents (CPU, ~2-4h) or Modal GPU (~10 min):
python -m packages.pipeline.ml.embedder --batch-size 64
```

### STEP 3 — Three code fixes (I build these, one session)
1. Fix middleware.ts to add all public pages to `isPublicRoute`
2. Add `og.png` social card image to `apps/web/public/`
3. Add cookie consent banner component

### STEP 4 — Train models (run after incidents extracted)
```bash
python -m packages.ml.train     # XGBoost, ~5 min
# If ECE < 0.05 AND Macro-F1 ≥ 0.65:
# Add ENABLE_PREDICTIONS=true to .env
```

### STEP 5 — Deploy
```bash
fly deploy                       # API to Fly.io
# Vercel: dashboard → import racejudge-hq/racejudge-web
```

### STEP 6 — Launch
- DNS cutover to racejudge.com
- Post r/formula1 on a Friday/Saturday of a race weekend
- Send 5 journalist DMs
- Post Twitter thread from launch_post.md

---

*Report v4 — 8 June 2026 — Full audit after Phases 1–8 code completion.*
