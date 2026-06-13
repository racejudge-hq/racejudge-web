# RACEJUDGE — Final Completion Report v6

> **Updated: 13 June 2026**
> Commits: 32 | Tests: 267 passing | Decisions: 1,606 (2019–2026) | Phases code-complete: Pre-Work · 1 · 2 · 3 · 4 · 5 · 6 · 7 · 8
> **Currently LIVE on Vercel (interim)** — API: https://racejudge-api.vercel.app · Web: https://racejudge-web.vercel.app
> **Migrating to Fly.io** per the implementation plan (Vercel was a deviation from the spec). Container config staged; blocked only on Fly billing — see Section 2A.

---

## What changed since v4 (8 June → 13 June)

v4 is superseded. Three commits after it (`2ecac01`, `93a80b6`, `201101b`) closed nearly every gap v4 listed, and the app was deployed. Verified against disk + live endpoints on 13 June:

| Area | v4 said | v5 reality (verified) |
|---|---|---|
| Hosting | Fly.io (planned, not deployed) | **Deployed to Vercel** — API + Web both live, health 200 |
| Data | 1,085 decisions (2019–2025) | **1,606 decisions (2019–2026)**, full 2026 season added |
| Cookie consent | ❌ missing | ✅ `CookieConsent.tsx`, wired in layout |
| Middleware public routes | ⚠️ blocked everything | ✅ fixed — public pages open, only `/annotate` gated |
| `generateMetadata()` | ❌ missing | ✅ incidents/[id] + decisions/[docId] |
| Phase 7/8 tests | ❌ 0 coverage | ✅ `test_phase7_routes.py`, `test_phase8_routes.py`, `test_auth.py` |
| `StewardPanel` + chi-squared | ❌ missing | ✅ model + `GET /v1/incidents/variance/by-panel` (live 200) |
| Geo-blocking on `/v1/predict` | ❌ missing | ✅ implemented |
| Lighthouse CI | ❌ no config | ✅ `.lighthouserc.js` + CI job |
| `og.png` social card | ❌ 404 | ✅ replaced by dynamic `opengraph-image.tsx` (live 200) |
| Security hardening | (not covered) | ✅ **new** — auth layer, security headers, non-root Docker, scoped CORS, CI dep-audit (see Section 16) |

**One functional gap remains:** the embeddings backfill has not been run against the production DB, so `/v1/precedents/search` returns 0 results. See Section 10, item 1.

**Hosting correction (v6):** the plan specifies **Fly.io (multi-region)**, not Vercel. Vercel was chosen during the deploy session for expedience and is the wrong fit for this app — serverless can't hold the live-mode WebSocket, has nowhere to run the Celery/Prefect workers, and its read-only filesystem already forced `contextlib.suppress` patches in 4 files. Migration back to Fly is underway — see Section 2A.

---

## Legend

| Symbol | Meaning |
|---|---|
| ✅ | Code written, committed, pushed (and live-verified where deployed) |
| 🔶 | Code done — blocked on your account / credentials / GPU to run |
| ⚠️ | Code done — but a one-time data/command step is still pending |
| 👤 | Only you can do this — no code involved |
| ❌ | Not built — post-launch scope or explicitly not started |

---

## SECTION 1 — Pre-Work

| Item | Status | Notes |
|---|---|---|
| GitHub repo + 32 commits, pushed | ✅ | |
| Journalist pitch templates | ✅ | `scripts/outreach/journalist_pitch.md` |
| 1,606 decisions scraped 2019–2026 | ✅ | `data/parsed/decisions.jsonl` |
| Curated driver/team reference rosters | ✅ | `data/reference/drivers.json` + `teams.json` |
| Register `racejudge.com` + `.io` + `.app` | 👤 | Namecheap — ~£12/year |
| Reserve `@racejudge` on X, Threads, Reddit, LinkedIn, Bluesky | 👤 | Do before launch |
| Register email `hello@`, `legal@`, `press@racejudge.com` | 👤 | Cloudflare Email Routing (free) |
| Trademark search EUIPO + USPTO class 42 | 👤 | Before launch — book a media law firm |
| Hand-label 300 annotation pairs (similar/dissimilar) | 👤 | `python scripts/annotate_pairs.py` — feeds BGE-M3 fine-tune + lifts the penalty model |
| Cold-email / DM 5 journalists | 👤 | Templates in `journalist_pitch.md` |

---

## SECTION 2 — Phase 1: Foundation

### Infrastructure code (all written, committed)

| Item | Status | File |
|---|---|---|
| Monorepo scaffold | ✅ | `apps/`, `packages/`, `infra/`, `scripts/` |
| GitHub Actions CI | ✅ | `.github/workflows/ci.yml` — ruff, mypy, pytest, tsc, next build, **dep-audit, Lighthouse** |
| API deploy workflow | ✅ | `.github/workflows/deploy-api.yml` (Fly.io, gated on `FLY_API_TOKEN`) |
| Dockerfile (non-root `racejudge` uid 1001) | ✅ | `Dockerfile` |
| `.dockerignore` / `.vercelignore` | ✅ | Keep secrets + data out of build/bundle |
| Vercel Python runtime entrypoint | ✅ | `pyproject.toml [tool.vercel] entrypoint = "apps.api.main:app"` |
| Migrations 0001–0006 | ✅ | `packages/db/migrations/versions/` |
| SQLAlchemy ORM models (incl. `StewardPanel`) | ✅ | `packages/db/models.py` |
| Async engine + URL normaliser (asyncpg) | ✅ | `packages/db/database.py` — strips libpq `sslmode`/`channel_binding` |
| FastAPI app + `/health` + settings | ✅ | `apps/api/main.py`, `apps/api/core/config.py` |

### Infrastructure accounts

| Item | Status | Notes |
|---|---|---|
| **Neon Postgres** (eu-west-2 / London) | ✅ | Provisioned, all 6 migrations applied, data loaded — **live** |
| **Vercel (API + Web)** — interim host | ⚠️ | Live and serving, but being replaced by Fly.io (Section 2A) |
| **Fly.io (API + Web)** — target host | 🔶 | Config staged + committed; blocked on Fly billing (add a card / prepaid credit) |
| Cloudflare R2 (PDF/audio/telemetry buckets) | 🔶 | Optional for soft launch — only needed for raw-PDF + audio hosting |
| Upstash Redis (rate-limit + live pub/sub) | 🔶 | Optional — rate limiter falls back to bounded in-memory; live mode needs it for fan-out |
| Prefect Cloud (scheduled flows) | 🔶 | Optional — backfills can be run manually |

### SECTION 2A — Hosting migration: Vercel → Fly.io (in progress)

The plan specifies **Fly.io multi-region** persistent containers; the interim Vercel deployment is being migrated back to that. **Region scope chosen: LHR + IAD + GRU, always-on.** flyctl is installed and authenticated (`marutey.mani.ug25@plaksha.edu.in` / org `disturbedsage`). All config is committed and staged — the only blocker is enabling billing on the Fly org (Fly has no free tier; a card or prepaid credit is required before `fly apps create` succeeds; current error: `We need your payment information to continue`).

| Staged | File | Purpose |
|---|---|---|
| API container config | `fly.toml` | primary `lhr` (co-located with Neon), always-on (`min_machines_running=1`, `auto_stop=false`), 1 GB VM, `release_command` runs `alembic upgrade head` |
| Web container config | `apps/web/fly.toml` | `racejudge-web`, lhr, always-on, API URL baked at build via `[build.args]` |
| Web image | `apps/web/Dockerfile` + `apps/web/.dockerignore` | multi-stage Next.js **standalone**, non-root (uid 1001) |
| Standalone output | `apps/web/next.config.ts` | `output: "standalone"` — required for the container |
| Slim API image | `requirements-api.txt` + `Dockerfile` | API runtime deps only — strips torch / sentence-transformers / fastf1 / playwright / xgboost / sklearn (verified all lazy-imported, so the API boots without them). Builds in ~2–3 min vs 15+ for the full set. |

**Remaining to finish (once Fly billing is enabled — I run all of it):** `fly apps create` (api + web) → set `DATABASE_URL` secret → `fly deploy` both → clone machines into iad + gru → verify `/health` per region → repoint the web build at the Fly API → tear down the Vercel projects so there's one source of truth.

---

## SECTION 3 — Phase 2: Structured Extraction

| Item | Status | File |
|---|---|---|
| `decision_parser.py` regex field extractor | ✅ | `packages/pipeline/parsers/decision_parser.py` |
| `text_cleaner.py` | ✅ | `packages/pipeline/parsers/text_cleaner.py` |
| `guidelines_parser.py` | ✅ | `packages/pipeline/parsers/guidelines_parser.py` |
| `layoutlm_extractor.py` / `tesseract_fallback.py` | ✅ | 3-layer fallback chain |
| `incident_extractor.py` | ✅ | `packages/pipeline/extractors/incident_extractor.py` |
| `driver_resolver.py` (per-season car numbers) | ✅ | Tracks `#1` champion handover per season (2022–25 VER, 2026 NOR) |
| `article_resolver.py` | ✅ | |
| `backfill_incidents.py` | ✅ | **Run** — 1,606 incidents populated, live |
| `seed_drivers.py` / `seed_guidelines.py` | ✅ | Run; 40 drivers / 17 teams / 33 guideline articles live |
| Incident + consistency + driver-stats endpoints | ✅ | `apps/api/routers/incidents.py` |
| Expand 33 → full 100-article 2025 guidelines | 🔶 | Optional; re-run `seed_guidelines.py` after expanding source |
| Label Studio 300-pair annotation campaign | 👤 | See Pre-Work |

---

## SECTION 4 — Phase 3: Multimodal Linking

| Item | Status | File |
|---|---|---|
| `openf1_client.py`, `radio_fetcher.py`, `transcriber.py` | ✅ | OpenF1 wrapper + Whisper large-v3 + pyannote |
| `asr_worker.py`, `diarisation.py` | ✅ | Celery ASR + speaker diarisation |
| `decision_linker.py`, `race_control_linker.py`, `weather_linker.py` | ✅ | |
| `fastf1_slicer.py` telemetry features | ✅ | |
| `modal_transcribe.py`, `sentiment_backfill.py` | ✅ | |
| Prefect `live_session_flow.py` | ✅ | |
| ASR / radio / race-control / telemetry **backfills run** | 🔶 | Needs `HF_TOKEN` + compute. **Optional for launch** (graceful degradation: "No radio available") |

---

## SECTION 5 — Phase 4: Precedent Retrieval

| Item | Status | File |
|---|---|---|
| `semantic_search.py` (pgvector HNSW) | ✅ | |
| `bm25_search.py` (tsvector) | ✅ | |
| `rrf.py` (Reciprocal Rank Fusion, k=60) | ✅ | |
| `precedents.py` router | ✅ | `POST /v1/precedents/search` (live, responds 200) |
| `embedder.py` / `modal_embed.py` / `train_embedder.py` | ✅ | BGE-M3 batch + fine-tune |
| `precedents/page.tsx` search UI | ✅ | |
| **Embeddings backfilled on production DB** | ⚠️ | **NOT run — search returns 0 results.** See Section 10 item 1 |
| BGE-M3 fine-tune (300 labelled pairs) | 👤 | Needs annotation campaign first |

---

## SECTION 6 — Phase 5: Penalty Prediction

| Item | Status | File |
|---|---|---|
| `predictor.py` (XGBoost 7-class, class-balanced, sigmoid-calibrated) | ✅ | `models/penalty_v1.pkl` trained |
| `predictor_v2.py` (stacked XGBoost + Llama) | ✅ | |
| `features.py`, `train.py`, `train_llama_lora.py` | ✅ | Time-split CV, ECE/F1 gates |
| `sentiment.py`, `rag_explainer.py` | ✅ | |
| `predict.py` router + gambling disclaimer + **geo-block** | ✅ | `/v1/predict` returns 503 (gated) — live |
| Probability distributions (never point predictions) | ✅ | |
| **Ship gate (Macro-F1 ≥ 0.65, ECE < 0.05)** | ❌ | Current: **Macro-F1 0.27, ECE 0.07 → FAILS gate**. `ENABLE_PREDICTIONS` stays `false`. **This is the planned Stage-3 outcome, not a bug** — plan says "do NOT ship publicly if miscalibrated." |
| `ANTHROPIC_API_KEY` for RAG explanations | 🔶 | Optional |

> To lift the model past the gate: run the 300-pair annotation campaign + richer telemetry features, then retrain. Realistically stays gated for soft launch.

---

## SECTION 7 — Phase 6: UX & Live Mode

| Item | Status | File |
|---|---|---|
| All 16 pages (home, decisions, precedents, predict, consistency, drivers, guidelines, live, incidents, annotate, review, api, search, sign-in/up) | ✅ | Live — `/`, `/decisions`, `/consistency`, `/guidelines` verified 200 |
| `live.py` WebSocket + Redis Pub/Sub + SSE fallback | ✅ | |
| `middleware.ts` — Clerk gating + public-mode fallback | ✅ | Only `/annotate` gated; public pages open |
| `generateMetadata()` on dynamic pages | ✅ | |
| Cookie consent (decline-by-default) | ✅ | `CookieConsent.tsx` |
| Dynamic OG image (1200×630) | ✅ | `opengraph-image.tsx` (live 200) |
| `next-themes` dark/light, Nav, error/404 boundaries, sitemap, robots | ✅ | |
| Plotly.js / D3 heatmaps / Mapbox / shadcn / Web Push / TanStack | ❌ | Deliberate post-launch deferrals (CSS bars + HTML tables suffice) |

---

## SECTION 8 — Phase 7: API, MCP Server & Billing

| Item | Status | File |
|---|---|---|
| `rate_limit.py` (Redis token-bucket + bounded in-memory fallback) | ✅ | Singleton client, 30s failure backoff, Retry-After |
| `billing.py` (Stripe webhook + subscription + portal) | ✅ | `return_url` locked to allowed origins |
| `apikeys.py` (create/list/revoke, SHA-256 stored) | ✅ | **Auth-gated** — `/v1/apikeys` returns 401 in prod (verified) |
| `mcp.py` (manifest + 4 tools) | ✅ | search_precedents, get_incident, get_driver_stats, predict_penalty |
| `review.py` Right-of-Review builder | ✅ | RAG-backed, template fallback |
| API key + Right-of-Review dashboards | ✅ | `apps/web/src/app/api` + `review` |
| `StewardPanel` model + **per-panel chi-squared** | ✅ | `GET /v1/incidents/variance/by-panel` (live 200) |
| Stripe products + price IDs + webhook secret | 🔶 | Not configured — billing inactive. Section 15 Step B |
| Onboard 3 journalists | 👤 | |

---

## SECTION 9 — Phase 8: Observability, Accessibility & Launch

| Item | Status | File |
|---|---|---|
| `latency.py` (p50/p95/p99 per route) + `/v1/metrics/latency` | ✅ | |
| `stewards.py` (Shannon entropy + inconsistency + severity slope + by-panel) | ✅ | |
| Sentry init (gated on `SENTRY_DSN`) + HNSW pre-warm in lifespan | ✅ | |
| Security headers (CSP, HSTS, X-Frame DENY, nosniff, Referrer-Policy) | ✅ | `apps/api/middleware/security_headers.py` — **verified live on API** |
| OG meta, skip-link, aria, not-found, error boundary, sitemap, robots | ✅ | |
| Cookie consent banner | ✅ | |
| Lighthouse CI (`.lighthouserc.js` + CI job) | ✅ | |
| Geo-blocking on `/v1/predict` | ✅ | |
| k6 load test, launch posts, LEGAL.md (DMCA), BRAND_CHECKLIST.md | ✅ | |
| Sentry account + DSN | 🔶 | Code wired; needs account |
| Grafana / BetterStack status page / PagerDuty | 👤 | Account-only; optional for soft launch |
| DNS cutover, legal review, Substack, r/formula1, journalist DMs | 👤 | Brand/legal/launch |

---

## SECTION 10 — What Is Still Open

Almost everything v4 listed here is now done. What genuinely remains:

### Functional gap (one command)

| # | What | Impact | How |
|---|---|---|---|
| 1 | **Embeddings backfill on production DB** | `/v1/precedents/search` returns **0 results** until this runs — it's the product's headline feature | `export DATABASE_URL=… && pip install sentence-transformers pgvector && python -m packages.pipeline.ml.embedder --batch-size 64` (~1–3h CPU / ~10min Modal GPU). Downloads BGE-M3 ~2.2GB, writes `vector(1024)` per incident. |

### Config (your accounts)

| # | What | Impact | How |
|---|---|---|---|
| 2 | **Clerk production keys** | Site runs in public mode; sign-in + API-key dashboard inert | Section 15 Step A |
| 3 | **Stripe keys + products** | Billing inactive | Section 15 Step B |
| 4 | **Finish Fly.io migration** | Plan's target host; Vercel is interim. Blocked on Fly billing | Section 2A + Section 15 Step 0 |

### Quality (optional)

| # | What | Note |
|---|---|---|
| 5 | Penalty model past ship gate | Needs annotation campaign + retrain. Correctly gated off until then. |
| 6 | Expand 33 → 100 guideline articles | Re-run seed after expanding source |
| 7 | ASR / radio / telemetry backfills | Needs HF token + compute; graceful degradation without |

### Post-launch deferrals (not bugs)

Plotly charts · D3 heatmaps · Mapbox corner overlay · shadcn/ui refactor · Web Push · TanStack Query · F2/F3/Formula-E expansion.

---

## SECTION 11 — Data Status

| Season | Records | Status |
|---|---|---|
| 2026 | 135 | ✅ |
| 2025 | 429 | ✅ |
| 2024 | 367 | ✅ |
| 2023 | 298 | ✅ |
| 2022 | 125 | ✅ |
| 2021 | 81 | ✅ |
| 2020 | 79 | ✅ |
| 2019 | 92 | ✅ |
| **Total** | **1,606** | ✅ All seasons 2019–2026 |

Drivers: 40 · Teams: 17 · Incidents extracted: 1,606 · Guidelines articles live: 33

---

## SECTION 12 — Test Status

| Suite | Status |
|---|---|
| `test_decision_parser.py` | ✅ |
| `test_incident_extractor.py` | ✅ |
| `test_ml_features.py` | ✅ |
| `test_scraper.py` | ✅ |
| `test_text_cleaner.py` | ✅ |
| `test_driver_resolver.py` (per-season `#1`) | ✅ |
| `test_article_resolver.py` | ✅ |
| `test_api.py` | ✅ |
| `test_annotations_api.py` | ✅ |
| `test_auth.py` (dev fallback, prod 401, 403 mismatch, garbage JWT) | ✅ |
| `test_phase7_routes.py` (billing, apikeys, mcp, review) | ✅ |
| `test_phase8_routes.py` (stewards, latency, rate_limit) | ✅ |
| **Total collected** | **267 ✅** |

---

## SECTION 13 — CI / Quality Gates

| Check | Status |
|---|---|
| `ruff` lint | ✅ clean |
| `mypy` type-check | ✅ clean (all 12 prior errors fixed) |
| `pytest` | ✅ 267 passing |
| `tsc --noEmit` | ✅ clean |
| `npm run build` (Next.js) | ✅ clean |
| pip-audit + npm audit (dep CVEs) | ✅ job added (torch CVE-2025-3000 ignored — no fix released) |
| Lighthouse CI | ✅ job added |

---

## SECTION 16 — Security Hardening (new in v5)

| Item | Status | File |
|---|---|---|
| Identity verification layer (API-key → Clerk JWT → fail-closed) | ✅ | `apps/api/core/auth.py` — `get_verified_user_id` 401s in prod, `ensure_user_match` 403s on mismatch |
| User-scoped endpoints secured | ✅ | apikeys + billing no longer trust caller-supplied `user_id` (verified: 401 live) |
| Security headers middleware | ✅ | `apps/api/middleware/security_headers.py` — verified live |
| CORS narrowed (`Authorization`, `Content-Type` only) | ✅ | `apps/api/main.py` |
| Stripe portal `return_url` locked to allowed origins | ✅ | `apps/api/routers/billing.py` |
| Rate limiter hardened (singleton, backoff, bounded memory) | ✅ | `apps/api/middleware/rate_limit.py` |
| Non-root Docker user + `.dockerignore` + `.vercelignore` | ✅ | secrets/data excluded from image + serverless bundle |
| `PyJWT[crypto]` for RS256 JWKS verification | ✅ | `requirements.txt` |

---

## SECTION 15 — Critical Launch Checklist (current)

Both services are live on Vercel (interim). Step 0 completes the move to the plan's Fly.io host; the rest follow.

### STEP 0 — Finish the Fly.io migration (see Section 2A)
1. Enable billing on the Fly `disturbedsage` org: https://fly.io/dashboard/disturbedsage/billing (add a card or prepaid credit — Fly has no free tier).
2. Then I run: `fly apps create racejudge-api && fly apps create racejudge-web` → set `DATABASE_URL` secret → `fly deploy` both → clone machines into `iad` + `gru` → verify `/health` per region → repoint web at the Fly API → remove the Vercel projects.

### STEP 1 — Light up precedent search (highest value)
```bash
cd /Users/maruteymani/Documents/RaceJudge && source .venv/bin/activate
export DATABASE_URL="<your Neon connection string>"   # already in .env
pip install sentence-transformers pgvector
python -m packages.pipeline.ml.embedder --batch-size 64
# Verify:
curl -X POST https://racejudge-api.vercel.app/v1/precedents/search \
  -H "Content-Type: application/json" -d '{"query":"unsafe release pit lane","limit":3}'
```

### STEP 2A — Enable Clerk
1. clerk.com → New Application "RACEJUDGE" → enable Email + Google.
2. Copy `pk_live_…`, `sk_live_…`; note JWKS URL + issuer.
3. On the live host (Vercel now, **Fly secrets** after migration) — web: `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`.
4. On the API host — `CLERK_JWKS_URL`, `CLERK_ISSUER`.
5. Redeploy both.

### STEP 2B — Enable Stripe
1. stripe.com → Products: "RACEJUDGE Pro" £29/mo, "RACEJUDGE Team" £499/mo → copy price IDs.
2. API keys → `sk_live_…`; Webhooks → `https://racejudge-api.vercel.app/v1/billing/webhook` (`customer.subscription.*`) → `whsec_…`.
3. On the API host (Vercel now / Fly after migration): `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRO_PRICE_ID`, `STRIPE_TEAM_PRICE_ID` → redeploy. (Point the webhook endpoint at the live API host.)

### STEP 2C — CI auto-deploy (after Fly migration)
Add `FLY_API_TOKEN` (`fly tokens create deploy`) to GitHub repo secrets — the existing `deploy-api.yml` workflow then deploys to Fly on push to main. This replaces the Vercel git-author workaround entirely.

### STEP 3 — Brand / legal (no code)
Register domain + handles; EUIPO/USPTO trademark search; media-rights lawyer review; 300-pair annotation; journalist DMs; publish launch post; r/formula1 on a race-weekend Friday.

### STEP 4 — (Optional) Model + observability
300-pair annotation → retrain → only set `ENABLE_PREDICTIONS=true` if **Macro-F1 ≥ 0.65 AND ECE < 0.05**. Add `SENTRY_DSN`; set up BetterStack status page.

---

*Report v6 — 13 June 2026 — Adds the Vercel→Fly.io hosting migration (Section 2A) per the implementation plan. Interim Vercel still live; Fly config staged and committed, blocked only on Fly billing.*
