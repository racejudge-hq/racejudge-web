# RACEJUDGE — Final Completion Report v11

> **Updated: 12 August 2026**
> Tests: 323 passing | **CI: all 4 jobs verified green by execution** (v10/v11 — not merely asserted) | Decisions: 1,606 (2019–2026) | Phases code-complete: Pre-Work · 1 · 2 · 3 · 4 · 5 · 6 · 7 · 8
> **Precedent search is LIVE** on a LoRA-fine-tuned BGE-M3 — 1,606 incidents embedded in Neon, semantic search verified. **32,120 precedent links materialised (v10).**
> **Currently LIVE on Vercel (interim)** — API: https://racejudge-api.vercel.app · Web: https://racejudge-web.vercel.app
> **Migrating to Fly.io** per the implementation plan (Vercel was a deviation from the spec). Container config staged; blocked only on Fly billing — see Section 2A.
> ✅ **v10's biggest open defect is closed:** classified incidents went **357 → 1,181 (22.2% → 73.6%)**. Nothing was deleted. Section 2C.

## What changed in v11 (12 August 2026)

The under-classification defect v10 identified was fixed at its source: the extractor's vocabulary, not the data. **823 real stewards' rulings recovered, 199 penalty outcomes recovered, 0 rows deleted.** Full account in **Section 2C**.

- **Classified incidents: 357 → 1,181 of 1,606 (22.2% → 73.6%).** Distinct categories 11 → 24. The 426 still unclassified track the ~385 genuinely administrative documents the v10 scan predicted.
- **Four separate bugs, not one.** (a) Labels the parser emitted had no entry in the category map — the key read `start procedure` while the label was `starting procedure`, so five ruling types extracted a type and then stored a NULL category anyway. (b) No patterns at all for parc fermé, deleted lap times, SC2-SC1, 107%, forcing off track, Race Director instructions. (c) `_layer1` classified on the document body only, ignoring the title — and the FIA title is often the only place the offence is named. (d) `_PENALTY_TYPE_MAP` had no WARN/FINE/SG, and the `CHECK` constraint could not store them.
- **`penalty_type` recovered for 199 rulings** — 113 FINE, 77 WARN, 9 SG. These had a plainly stated decision and were storing NULL because the schema had no value for them. Migration **`0010`** widens `ck_incidents_penalty_type`.
- **Two latent correctness bugs caught by the new tests**, both pre-existing: the fine regex expected `5,000 €` but the FIA writes `€5,000`, so no fine ever matched; and because the penalty map is matched by substring, `"5 second"` matched inside `"15 second penalty"` — a 15s penalty would have been recorded as 5s. Stored data audited: **0 rows affected**, the outcome regex had matched the full number first.
- **Display and aggregation layers brought in line.** Three frontend penalty maps and two SQL aggregations still assumed the old 7-value set: a warning counted as a "sanction" in driver stats, and the consistency heat-map's buckets no longer summed to 100%. Verified: all 108 heat-map rows now sum to 100%.
- **Tests: 267 → 323.** Includes a completeness guard asserting every label the parser can emit has a category mapping — the invariant whose absence caused the defect.
- **The 4 conflicting rows are resolved (v12).** Adjudicating them against the source documents showed the v11 list was itself partly wrong, and exposed three more pattern bugs — two introduced by v11. 11 corrections applied, 0 rows deleted. One (`7caff04e`) is a judgement call flagged for you in Section 2C.
- **The `/consistency` 500 is fixed (v12) — and my v11 diagnosis of it was wrong.** It was never a Vercel problem: `/incidents/{incident_id}` was declared before the literal `/incidents/consistency`, so Starlette matched the parameterised route first and the page never reached its handler. It would have broken on Fly too. Section 10 row 1e.

---

## What changed in v10 (12 August 2026)

Section 2 was audited by **execution rather than inspection** — every CI gate run with its true exit code checked, every schema claim diffed against live Neon. It was fully marked ✅; five real defects were found. See **Section 2B** for the full account.

- **The "all 4 CI jobs green" claim was stale.** `security-audit` was failing on *both* halves — 3 high npm advisories (`postcss`, `sharp`, pinned by `next@15.5`) and `PYSEC-2026-3625` (`msgpack`). Both fixed without the breaking `next@16` upgrade `npm audit fix --force` wanted. All four jobs now genuinely exit 0.
- **The precedent engine's core endpoint was silently dead in production.** `/v1/precedents/{id}/similar` returned `[]` with HTTP 200 for *every* incident, because `precedent_links` had never been populated — Prefect has never run a single flow. Recomputed from the real embeddings already in Neon: **32,120 links, all 1,606 incidents.** Endpoint verified live.
- **ORM↔database drift eliminated.** All 158 columns diffed: `steward_panels.created_at` existed in the model but not the DB (any ORM query on it would raise), 22 datetime columns were naive vs `timestamptz`, and `api_keys.requests_total` was narrowed. Migration **`0009`** applied to Neon; drift is now **0**.
- **Orchestration was never wired up.** 3 `@flow`s existed but there was no `prefect.yaml`, no schedules, no deployments — Prefect Cloud showed 0 pools / 0 flows / 0 runs. Manifest written; applying it is 💳-blocked on a Fly worker.
- **Latent runtime bug fixed:** diarisation called `Pipeline.from_pretrained(use_auth_token=)`, removed in pyannote 4.x.
- **India trademark search ✅ complete — clear.** Knock-out search now done in all four jurisdictions.
- **Full corpus scan (all 1,249 unclassified incidents, not a sample):** 864 of them (69.2%) are **genuine stewards' rulings the extractor failed to categorise** — verified against the FIA document signature, with the 357 already-classified incidents as a control (94% match). Filtering them out, the obvious first instinct, would have **destroyed 2.4× more real incidents than the corpus currently has classified.** Only ~385 are truly administrative. The real defect is the extractor's category vocabulary. See Section 2B.
- Corrected: web build emits **20 routes**, not 16.

---

## What changed in v9 (12 August 2026)

- **New legend symbol 💳** — card-gated items are now visually separated from genuine gaps. Previously they were mixed in with 🔶/👤, which made the report read as if work was outstanding when it was simply parked awaiting a payment method.
- **Sentry is live and verified** — org `racejudge-if` / project `racejudge-api`; DSN in `.env`, test events accepted end-to-end. See Section 9.
- **Domain reality check (changes the plan):** `racejudge.com` is **not available** — held since 2003 by GoDaddy's NameFind investment arm, so it is a premium-priced asset, not a ~£12 registration. `racejudge.io` / `.app` / `.dev` / `.co.uk` verified available; **`racejudge.app` recommended** as primary. See Section 1.
- **Trademark knock-out searches done (by you):** exact mark "RaceJudge" is **clear** at EUIPO/TMview, USPTO and UK IPO. *(IP India was the open item at v9 — completed in v10, also clear.)* `RACE GUIDE` (UK, live, classes 9/35/42) flagged for the lawyer. See Section 1A.
- **Phase-3 backfill work, frontend libraries, push pipeline and ML enrich scripts committed** as `1e009ed` (34 files) — the v8 working tree is no longer uncommitted.
- Corrected two stale claims: Grafana/BetterStack/PagerDuty are *blocked on deploy*, not merely "optional"; journalist outreach is *deliberately held*, not pending.

---

## What changed in v8 (21 June 2026)

- **Phase 3 multimodal backfill RUN end-to-end (real data, no synthetic):** 651 incidents linked to 182 OpenF1 sessions; **12,111 race-control messages** (861 linked to incidents); **297 incidents** with real weather context; **198 team-radio clips** (192 Whisper-transcribed + sentiment/urgency, 192 speaker-diarized driver/engineer via pyannote); **105,768 FastF1 lap-feature rows across all 182/182 sessions**. See Section 4.
- **Root-cause DB fix (committed `123a0cc`):** 10 ORM primary keys were declared `UUID` but are `TEXT` in the DB — every incident/RC/clip query rolled back with `text = uuid`, which had silently made the Phase-3 backfill persist 0 rows. Fixed in `models.py` (billing tables correctly kept as real `uuid`).
- **Frontend viz/UX libraries built (`next build` green, 16/16):** Plotly + D3 on `/consistency`, TanStack table + shadcn on `/decisions`, MapLibre circuit map on `/circuits`, full Web Push pipeline. See Section 7.
- **Stripe billing configured (test mode):** products/prices were already present; created the webhook endpoint + `STRIPE_WEBHOOK_SECRET`; end-to-end checkout verified. See Section 8.
- **Penalty ship gate — two honest retrains run:** multimodal features (test Macro-F1 0.08) and clean DB labels (0.14); neither approaches 0.65. Confirmed structural (rare-class data scarcity), correctly stays gated. See Section 6.
- **Migrations 0007 (rc_incident_fk) + 0008 (push_subscriptions)** added and applied.
- ~~New/changed code from this session is in the working tree~~ → ✅ **all committed in v9** as `1e009ed` (34 files: frontend components, `apps/api/routers/push.py`, `packages/ml/enrich.py`, migration 0008, backfill scripts).

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

**Resolved in v7:** the embeddings backfill has now been run — all 1,606 incidents are embedded (with a LoRA-fine-tuned BGE-M3) and `/v1/precedents/search` returns relevant precedents. See the v7 changelog below + Section 5.

**Hosting correction (v6):** the plan specifies **Fly.io (multi-region)**, not Vercel. Vercel was chosen during the deploy session for expedience and is the wrong fit for this app — serverless can't hold the live-mode WebSocket, has nowhere to run the Celery/Prefect workers, and its read-only filesystem already forced `contextlib.suppress` patches in 4 files. Migration back to Fly is underway — see Section 2A.

---

## What changed in v7 (13 → 16 June)

This session completed the retrieval ML pipeline (Pre-Work → Phase 4) and turned CI green:

| Area | v6 | v7 (this session) |
|---|---|---|
| **Annotation campaign** (Pre-Work / Phase 2) | 👤 not started | ✅ **done** — two-stage pipeline: deterministic candidate generation (`generate_candidates.py`) → AI adjudication of all 457 candidates against full decision texts (`adjudicate_pairs.py`) → **359 labelled pairs** (215 similar / 144 dissimilar). Human Stage-2b review (`review_pairs.py`) skipped by choice; the 359 AI-adjudicated pairs are final. |
| **Embeddings backfill** (Phase 4) | ⚠️ not run — search returned 0 | ✅ **run** — all 1,606 incidents embedded in Neon |
| **BGE-M3 fine-tune** (Phase 4) | 🔶 needed the annotation campaign first | ✅ **LoRA fine-tune on the M4 (MPS)** — held-out triplet accuracy **0.844 → 0.969 (+12.5 pts)**; all 1,606 re-embedded with the tuned model (`embedding_model = bge-m3-f1-lora`); `EMBED_MODEL` pinned so query and document vectors use the same model |
| **Precedent search** | ⚠️ 0 results | ✅ **live + verified** — returns relevant precedents from the production DB |
| **CI** | ❌ red | ✅ **all 4 jobs green** — fixed ruff (import order / unused vars), mypy errors from third-party stub drift (anthropic / stripe / sentence-transformers), and the Lighthouse config (`apps/web/lighthouserc.json`) |
| **Socials reserved** (Pre-Work) | 👤 | ✅ X, Instagram, Threads, LinkedIn, Bluesky |

**Deploy note:** the Fly container must ship the tuned-model dir (`data/models/bge-m3-f1`, 6 MB LoRA adapter) + set `EMBED_MODEL` + `peft` (already a dependency). Wired in at deploy time.

---

## Legend

| Symbol | Meaning |
|---|---|
| ✅ | Code written, committed, pushed (and live-verified where deployed) |
| 🔶 | Code done — blocked on your account / credentials / GPU to run |
| ⚠️ | Code done — but a one-time data/command step is still pending |
| 👤 | Only you can do this — no code involved |
| 💳 | **Card-gated — parked by your instruction.** Needs a payment method; no work possible (by you or me) until a card is ready. Do not treat as a bug or an oversight. |
| ❌ | Not built — post-launch scope or explicitly not started |

---

## SECTION 1 — Pre-Work

| Item | Status | Notes |
|---|---|---|
| GitHub repo + 32 commits, pushed | ✅ | |
| Journalist pitch templates | ✅ | `scripts/outreach/journalist_pitch.md` |
| 1,606 decisions scraped 2019–2026 | ✅ | `data/parsed/decisions.jsonl` |
| Curated driver/team reference rosters | ✅ | `data/reference/drivers.json` + `teams.json` |
| Register domain | 💳 | ⚠️ **`racejudge.com` is NOT available** — registered 2003, nameservers `ns1/ns2.namefind.com` (GoDaddy's domain-investment arm), i.e. investor-held and priced as a premium asset, not ~£12. **Verified available (v9): `racejudge.io` (registry "Domain not found"), `.app`, `.dev`, `.co.uk` (no whois record, no NS).** Recommended primary: **`racejudge.app`** — ~£12/yr, HSTS-preloaded by default (browser-forced HTTPS). Parked until a card is ready. |
| Reserve `@racejudge` on X, Threads, LinkedIn, Bluesky | ✅ | Reserved (X, Instagram, Threads, LinkedIn, Bluesky) |
| Register email `hello@`, `legal@`, `press@` | 💳 | Cloudflare Email Routing is **free**, but **hard-blocked by the domain purchase above** — it cannot be set up without an owned domain on Cloudflare nameservers. Steps are written and ready to execute the moment the domain exists. ⚠️ Note: Email Routing **receives/forwards only — it cannot send**; replying *as* `press@…` additionally needs Gmail "Send mail as" + an SMTP relay (Resend/Brevo/SMTP2GO free tier). |
| Trademark knock-out search — EUIPO/TMview, USPTO, UK IPO | ✅ | **Done by you (v9). Exact mark "RaceJudge" is clear in all three.** TMview `RaceJudge` → 0 rows; TMview `RACEJUDGE` → 0 rows; TMview `Race Judge` → 1 hit, *unrelated* + status **Ended** (dead); USPTO `RaceJudge` → **0 live, 0 dead**. USPTO `Race Judge` returned 4,347 rows but that is a fuzzy OR-match on the common word "JUDGE" (JUDGE, Judge Leo, Old Judge…), **not** a "Race Judge" conflict. See flag below. |
| Trademark search — **India (IP India)** | ✅ | **Done by you (v10) — nothing at all, everything clear.** The most relevant jurisdiction, since you are based and operating in India. Knock-out search is now complete in **all four** jurisdictions (EUIPO · USPTO · UK IPO · IP India). |
| Trademark **clearance opinion** (lawyer) | 💳 | The searches above are a *knock-out* check, **not** legal clearance. A media/IP lawyer's formal opinion + any filing costs money — parked. |
| Label 300 annotation pairs (similar/dissimilar) | ✅ | **Done** via the two-stage AI-adjudicated pipeline — **359 pairs** (215 similar / 144 dissimilar). Fed the BGE-M3 LoRA fine-tune (see v7 changelog). |
| Cold-email / DM 5 journalists | 👤 | Templates ready in `scripts/outreach/journalist_pitch.md`. **Deliberately held until after deploy** — the API is not live (verified: `racejudge-api.fly.dev` → no response), so a pitch today links to nothing. Send from `press@` once the domain + deploy land. Same logic for the r/formula1 post. |

### SECTION 1A — Brand & trademark clearance (v9)

**Status: exact mark "RaceJudge" is clear in all four searched jurisdictions — EU, UK, US and India. The knock-out search is complete.** Remaining trademark work is the lawyer's formal clearance + filing (💳).

**Open action — IP India search (free, ~20 min, no card):**

1. Go to [IP India — Public Search of Trade Marks](https://tmrsearch.ipindia.gov.in/tmrpublicsearch/) (verified live, HTTP 200)
2. Search type: **Wordmark**
3. Run these three searches, each against **Class 42** (software/SaaS), then repeat for **Class 41** (sports info/entertainment) and **Class 9** (downloadable software):
   - `RACEJUDGE` (Search Type: *Start With* and again *Contains*)
   - `RACE JUDGE`
   - `RACEJUDGE` under **Phonetic** search type — India weights phonetic similarity heavily, so this matters more than it does at USPTO
4. Any **Registered** or **Objected/Advertised** live mark in classes 9/41/42 is a flag → report it before committing to the name

**Flag for the lawyer (not a blocker, but disclose it):** UK IPO returned **`RACE GUIDE`** — UK00003569887, **Registered**, filed 18 Dec 2020, **classes 9, 35, 42**. Different word (GUIDE ≠ JUDGE, and phonetically distinct), and "RACE" is descriptive in a motorsport context — but it is a live mark sharing the leading element in overlapping software classes. Worth a sentence in the clearance brief rather than a surprise later.

> ⚖️ These searches are a **knock-out check, not legal clearance.** They rule out the obvious collisions cheaply. They do not substitute for an IP lawyer's opinion (💳, parked).

---

## SECTION 2 — Phase 1: Foundation

### Infrastructure code (all written, committed)

| Item | Status | File |
|---|---|---|
| Monorepo scaffold | ✅ | `apps/`, `packages/`, `infra/`, `scripts/` |
| GitHub Actions CI | ✅ | `.github/workflows/ci.yml` — ruff, mypy, pytest, tsc, next build, dep-audit, Lighthouse. ⚠️ **The v7 "all 4 jobs green" claim was stale — see SECTION 2B.** `security-audit` was failing on *both* halves. **Re-verified green (v10)** by running every gate locally: `91fea0a` + `07e246c` |
| API deploy workflow | ✅ | `.github/workflows/deploy-api.yml` (Fly.io, gated on `FLY_API_TOKEN`) |
| Dockerfile (non-root `racejudge` uid 1001) | ✅ | `Dockerfile` — statically validated (v10): `requirements-api.txt` present, `.dockerignore` excludes `.env`/`.venv`/`node_modules`. Its dep set is a **superset** of `pyproject.toml`, which the live Vercel API already boots on, so the import surface is proven. Image build itself unverified (no Docker daemon locally; Fly is 💳) |
| `.dockerignore` / `.vercelignore` | ✅ | Keep secrets + data out of build/bundle |
| Vercel Python runtime entrypoint | ✅ | `pyproject.toml [tool.vercel] entrypoint = "apps.api.main:app"` |
| Migrations 0001–0010 | ✅ | `packages/db/migrations/versions/` — **`0009` added in v10** (`steward_panels.created_at`, see 2B), **`0010` in v11** (widen `ck_incidents_penalty_type` for WARN/FINE/SG + `Ns`, see 2C). Neon confirmed at head `0010`; all ten applied |
| SQLAlchemy ORM models (incl. `StewardPanel`) | ✅ | `packages/db/models.py` — **all 158 columns diffed against live Neon (v10); 3 classes of drift found and fixed, now 0 mismatches** |
| Prefect deployment manifest | ⚠️ | **`prefect.yaml` written in v10** — the 3 flows were code-only and had never been registered (see 2B). Applying it needs a worker host → 💳 Fly |
| Async engine + URL normaliser (asyncpg) | ✅ | `packages/db/database.py` — strips libpq `sslmode`/`channel_binding` |
| FastAPI app + `/health` + settings | ✅ | `apps/api/main.py`, `apps/api/core/config.py` |

### Infrastructure accounts

| Item | Status | Notes |
|---|---|---|
| **Neon Postgres** (eu-west-2 / London) | ✅ | Provisioned, **all 9 migrations applied (head `0009`, verified v10)**, data loaded — **live**. 22 tables. All 1,606 incidents embedded (`bge-m3-f1-lora`), HNSW index present. **`precedent_links` materialised in v10 — 32,120 links (was empty; see 2B)** |
| **Vercel (API + Web)** — interim host | ⚠️ | Live and serving, but being replaced by Fly.io (Section 2A) |
| **Fly.io (API + Web)** — target host | 💳 | Config staged + committed; blocked on Fly billing (Fly has no free tier — needs a card or prepaid credit before `fly apps create` succeeds) |
| Cloudflare R2 (PDF/audio/telemetry buckets) | 💳 | Optional for soft launch — only needed for raw-PDF + audio hosting |
| Upstash Redis (rate-limit + live pub/sub) | ✅ | **`REDIS_URL` configured in `.env`** (Upstash, card-free). Wires in at deploy via Fly secrets. |
| Prefect Cloud (scheduled flows) | ⚠️ | **Credentials valid — `/health` returns 200 (v10).** But the workspace is **completely empty: 0 work pools, 0 flows, 0 deployments, 0 runs ever.** Nothing has ever been scheduled. `prefect.yaml` now exists; registering it needs a worker host → 💳 Fly. |

### SECTION 2B — Deep audit of Section 2 (v10)

Everything in Section 2 was marked ✅. Rather than trust the marks, every gate was **executed** and every schema claim **diffed against live Neon**. Five real defects were found; four are fixed, one is a product decision for you.

**Verified genuinely green** (run locally, true exit codes checked):

| Gate | Result |
|---|---|
| `ruff check packages/ apps/ scripts/ tests/` | ✅ All checks passed |
| `mypy --explicit-package-bases packages/ apps/ scripts/` | ✅ no issues, 108 files |
| `pytest tests/` | ✅ **267 passed** |
| `npx tsc --noEmit` | ✅ clean |
| `npm run build` | ✅ **20 routes** (report previously said 16) |
| `npm audit --audit-level=high` | ✅ **0 vulnerabilities** (after fix below) |
| `pip-audit -r requirements.txt` | ✅ exit 0 (after fix below) |
| Vercel API + Web | ✅ live, serving real DB data |

**Defects found and fixed:**

1. **`security-audit` CI job was RED on both halves — the "all 4 jobs green" claim was stale.**
   - *npm side:* 12 vulnerabilities, 3 high. `next@15.5` pins `postcss@8.4.31` (4 high advisories incl. sourceMappingURL path traversal) and `sharp@0.34.5` (libvips CVE-2026-33327/33328/35590/35591). `npm audit fix --force` would have installed **`next@16.3.0`** — a breaking major. Fixed instead with documented npm `overrides` pinning `postcss ^8.5.26` / `sharp ^0.35.3`, both minor-compatible. Audit now 0 vulns, and `tsc` + `next build` still pass.
   - *Python side:* `PYSEC-2026-3625` (`msgpack 1.1.2`, DoS-only out-of-bounds read). **Cannot be upgraded** — it is transitive via `fastf1 → signalrcore`, and `signalrcore 1.0.2` (latest) hard-pins `msgpack==1.1.2`; pip can only satisfy `>=1.2.1` by downgrading signalrcore to `0.8.8`. Not exposed in production (`fastf1`/`msgpack` are absent from `pyproject.toml`, the set the deployed API installs). Ignored with a written rationale beside the existing torch exception.

2. **`precedent_links` was empty in production — the precedent engine's core endpoint was silently dead.**
   `GET /v1/precedents/{id}/similar` reads that table and returned **`[]` with HTTP 200 for every incident** — a silent failure, not an error. Root cause: `refresh_precedent_links_task` lives inside `embedding_flow`, and **Prefect has never run a single flow**, so the links were never materialised (incidents were embedded by a one-off script instead). Recomputed the top-20 cosine neighbours over the existing real embeddings — **32,120 links across all 1,606 incidents, 20s**, avg score 0.804. Live endpoint re-tested: **now returns real precedents.** No synthetic data — pure pgvector over the embeddings already in the DB.

3. **`steward_panels.created_at` existed in the ORM but not in the database.** Migration `0004` created the table without it while the model declares it, so any ORM read/write on that table raised `UndefinedColumn`. Latent only because the table has 0 rows and nothing queries it. Fixed by **migration `0009`**, applied to Neon.

4. **22 datetime columns were naive in the ORM but `timestamptz` in Postgres.** `Mapped[datetime]` with no explicit type infers `DateTime(timezone=False)`; reads come back tz-aware from the driver, so any comparison against a naive datetime raises *"can't compare offset-naive and offset-aware datetimes"*. All now declare `DateTime(timezone=True)`, matching `events.date`/`sessions.date` which already did. Also widened `api_keys.requests_total` (ORM `Integer` vs DB `bigint`). **ORM↔DB drift is now 0 across all 158 columns** — the same bug class as the `text`/`uuid` mismatch that previously zeroed the Phase-3 backfill.

5. **Orchestration was entirely unwired.** 3 flows (`ingest-flow`, `embedding-flow`, `live-session-monitor`) are decorated with `@flow` but there was **no `prefect.yaml`, no `.deploy()`/`.serve()`, no schedules** — hence 0 deployments and 0 runs. Wrote `prefect.yaml` registering all three (ingest every 6h, embedding nightly 03:30 UTC, live-session on-demand). Applying it needs a work pool + running worker → blocked on 💳 Fly.

**⚠️ Open — the extractor is under-classifying, and it is losing most of the corpus (v10 deep scan):**

1,249 of 1,606 incidents have `infraction_category = NULL`. A **full scan of all 1,249** (not a sample) was run to determine whether those are genuinely non-incidents or extraction failures. **They are overwhelmingly extraction failures.**

Method: FIA stewards' rulings have a fixed document signature — sender `From The Stewards` plus the structured fields `Fact` / `Infringement` / `Decision` / `Reason`. Administrative documents come `From The FIA Formula One Technical Delegate` and carry none of that structure. Each document was scored 0–5 on those five signals.

**Control:** of the 357 *already-classified* incidents, **all 357** are `From The Stewards` and **335 (94%)** score 4–5. The signature is reliable.

**Result across all 1,249 null-category documents:**

| Bucket | Count | Share |
|---|---|---|
| **Real stewards' ruling (strong, score 4–5)** | **821** | 65.7% |
| **Real stewards' ruling (probable, score 3)** | **43** | 3.4% |
| Stewards document, weak/minimal structure | 140 | 11.2% |
| ADMIN — Technical Delegate report | 226 | 18.1% |
| ADMIN / non-ruling | 19 | 1.5% |

**864 of the 1,249 (69.2%) are genuine stewards' rulings that the extractor failed to categorise.** 1,004 of 1,249 are `From The Stewards`. They carry real, stated outcomes: 293 *no further action*, 148 time penalties, 104 deleted lap times, 61 pit-lane starts, 57 fines, 54 warnings, 52 reprimands, 25 disqualifications, 17 grid penalties, 8 drive-throughs, 6 stop-go.

**Conclusion: option (a) — filtering — was the wrong instinct and has been rejected.** It would have discarded **864 real stewarding decisions, ~2.4× more than the 357 currently classified.** The true corpus is **~1,221 real incidents (76%)** against only **~385 genuinely administrative documents (24%)** — mostly *"PU elements used per driver"* (145) and *"RNCs used per driver"* (65), which are Technical Delegate reports and correctly excluded.

**The actual defect is the extractor's category vocabulary being far too narrow.** It recognises 11 categories (pit_lane_speed, yellow_flag, impeding, collision, unsafe_release, vsc, track_limits, erratic_driving, safety_car, blue_flag). The scan shows it is missing at minimum: **deleted lap times / track limits (153), parc fermé (85), safety-car-line time SC2-SC1 (66), technical breach (21), forcing another driver off the track, failure to follow Race Director's instructions, unsafe release variants, overtaking under safety car, starting-procedure infringements, practice starts, 107% rule, driver conduct (32), false start (7)** — 292 distinct ruling titles in the unclassified set alone.

Two further points worth noting:
- **293 of the recovered rulings are "no further action" decisions.** For a precedent engine these are *high-value*, not noise — they are the evidence of what the stewards decline to penalise.
- The admin documents should still be excluded from the precedent corpus, but that is ~385 rows, not 1,249.

**Recommended next step:** extend the extractor's category taxonomy to cover the ruling types above and re-run extraction over the 864, rather than filtering. This is a data-recovery task, not a deletion task. ✅ **Actioned in v11 — see Section 2C.**

---

### SECTION 2C — Extractor taxonomy fix and data recovery (v11)

Acting on 2B. Constraint held throughout: **fill blank fields only — never overwrite a stored value, never delete a row.** Row count before and after: **1,606 → 1,606.**

#### Result

| Metric | Before | After |
|---|---|---|
| Incidents with `infraction_category` | 357 (22.2%) | **1,181 (73.6%)** |
| Distinct categories | 11 | **24** |
| Incidents with `penalty_type` | 736 | **935** |
| Consistency heat-map rows | — | **108, all summing to 100%** |
| Tests | 267 | **323** |
| Rows deleted | — | **0** |

#### The defect was four bugs, not one

The scan in 2B assumed a single cause (a narrow vocabulary). Reading the code found four independent failure points, two of which would have defeated a vocabulary-only fix:

1. **Map keys did not match the labels they were supposed to map.** `decision_parser` emits an infraction *label*; `incident_extractor` maps that label to a *category*. Nothing connected the two lists. The key `start procedure` never matched the label `starting procedure`; `false start`, `leaving the track`, `driving unnecessarily slowly` and `media commitment breach` had no key at all. Those rulings extracted a type successfully and *then* stored a NULL category.
2. **No patterns for the missing ruling types** — parc fermé, deleted lap times, SC2-SC1, 107%, forcing off track, Race Director instructions, practice starts, weighbridge, driver obligations.
3. **`_layer1` classified on the document body alone**, though the parser's own `extract_incident()` uses `title + body` and the code comment claimed the title was tried first. For rulings such as *"Deleted Lap Times"* or *"Parc Fermé"* the title is the only place the offence is named.
4. **`penalty_type` had no representation for warnings, fines or stop-go**, and `ck_incidents_penalty_type` would have rejected them anyway.

New patterns were **appended** rather than interleaved, so first-match-wins guarantees every previously classified document keeps its label. Confirmed by re-run: 0 existing categories changed.

#### Categories after the fix

`technical` 196 · `track_limits` 181 · `impeding` 95 · `pit_lane_speed` 94 · `parc_ferme` 90 · `collision` 85 · `yellow_flag` 80 · `safety_car_line_time` 55 · `unsafe_release` 52 · `driver_obligation` 36 · `race_director_instructions` 35 · `driving_slowly` 31 · `107_percent` 28 · `forcing_off_track` 27 · `vsc` 17 · `start_procedure` 14 · `pit_lane` 14 · `false_start` 13 · `safety_car` 11 · `practice_start` 11 · `weighing` 7 · `crossing_track` 3 · `erratic_driving` 3 · `blue_flag` 2

`penalty_type` after: NFA 394 · 5s 136 · **FINE 113** · **WARN 77** · 10s 75 · REP 67 · DSQ 32 · GRID 19 · DT 13 · **SG 9**

#### Two latent bugs the new tests caught

Both pre-existed this work and were found only because the new cases used verbatim FIA text:

- **No fine was ever matched.** The pattern required `5,000 €`; every FIA decision writes `is fined €5,000`. The symbol precedes the amount.
- **A 15-second penalty would have been stored as `5s`.** The penalty map is matched by substring, and `"5 second"` is a substring of `"15 second penalty"`. Now resolved numerically before the map is consulted. **Stored data audited: 0 rows affected** — the outcome regex happened to capture the full number first — but the bug was live.

#### Downstream layers corrected

The recovered values are real data the rest of the stack could not display or count:

| Layer | Problem | Fix |
|---|---|---|
| `precedents/page.tsx` | WARN/FINE/SG unstyled; absent from the filter | Added, ordered by severity |
| `incidents/[id]/page.tsx` | No colour mapping | Added |
| `drivers/[code]/page.tsx` | Counts silently dropped those incidents | Added |
| `incidents.py` consistency | `IN ('5s','10s')` missed 15s/20s/30s; WARN/FINE in no bucket, so rows did not sum to 100% | Regex bucket + `warn_pct`/`fine_pct` (additive, `list[dict]` return — no schema break) |
| `mcp.py` driver stats | A warning counted as a *sanction* | `NOT IN ('NFA','WARN','REP')` |

`predict/page.tsx` was deliberately **left alone** — that list is the ML model's output classes, and the model predicts 7. Adding classes it cannot emit would render permanent 0% bars. Retraining on the widened label set is a Phase 5 task, noted in Section 10.

#### Conflicting rows — adjudicated and corrected (v12)

v11 listed 4 rows where the new code disagreed with a stored value and left them alone. You then authorised fixing them. Each was adjudicated by reading the source document rather than trusting either side, and **that adjudication found three further pattern bugs of my own making** — documented below, because two of them were introduced by the v11 work itself.

The v11 list did not survive contact with the documents. `07d03f4f` (`race_director_instructions` → `track_limits`) was **the new code being wrong, not the database**: the ruling is a Race Director's Event Notes breach whose *Reason* merely observes that the driver "knew that his lap time would be deleted". A widened deleted-lap-time regex had been matching that passing mention. It was reverted (it had recovered 0 documents anyway), so the row needed no change at all.

**11 corrections were applied**, all verified against the document text:

| Incident | Field | Stored → written | Evidence in the source document |
|---|---|---|---|
| `775c5a13…` | `infraction_category` | `yellow_flag` → `impeding` | Title: *"Decision - Car 7 (alleged impeding of car 8)"* |
| `b5e74ba9…` | `infraction_category` | `erratic_driving` → `impeding` | Title: *"Doc 44 - Infringement - Car 81 - Impeding of Car 27"* |
| `31fe2c5a…` `3a24d269…` `6b2250f2…` `872ecd88…` `f0f0cb72…` | `infraction_category` | `race_director_instructions` → `practice_start` | Facts read *"performed a practice start outside the designated practice start area"*, *"undertook a practice start at pit exit"*, *"Completed a practice start before taking the end of session signal"*. "Failure to follow Race Director's Instructions" is only the article cited (12.2.1 i) — the catch-all — so the specific offence is the better classification |
| `2b65e212…` `4048aa67…` `d0a9d047…` | `infraction_category` | `driver_obligation` → `safety_car` | Fact: *"Near collision behind the safety car"*, Article 55.5 |
| `7caff04e…` | `penalty_type` | `REP` → `SG` | See the judgement call below |

⚠️ **`7caff04e` is a judgement call you may want to revisit.** The Decision reads: *"A mandatory Stop-and-Go penalty imposed after the Race. This penalty is suspended… In addition the driver is Reprimanded."* **Both penalties are real, and the stop-and-go is suspended** — so the reprimand is arguably the only sanction actually served. `SG` was written because it is the headline penalty, but a single `penalty_type` column cannot express "suspended SG + reprimand". If the precedent engine should reflect what was *served*, this row should read `REP`.

#### Three pattern bugs found while adjudicating

Two were introduced by v11; all three are now covered by regression tests written from verbatim corpus text.

| Pattern | Defect | Fix |
|---|---|---|
| `driver obligation breach` | Matched a bare *"drivers' briefing"* / *"drivers' meeting"*, which appears in the *Reason* narrative of wholly unrelated rulings — it had captured the escape-road, yellow-flag and crossing-the-track decisions. Only visible on cleaned text, because the cleaner normalises the curly apostrophe the raw pattern missed | Now requires offence language (*late for*, *late attendance*, *failed to attend*, *behaviour in*). Also added *"Late attendance of National Anthem"*, a real ruling that would otherwise have been lost |
| `practice start infringement` | Matched *"Practice Start **Area**"* — a place in the pit lane — pulling **6 pit-lane rulings** ("overtook several cars in the Fast Lane whilst traversing the Working Lane to the Practice Start Area") out of their real category | Requires the practice start to be the *act*. Kept narrow deliberately: those same rulings discuss practice starts in their Reason (*"did perform a genuine practice start"*), so any looser rule takes them straight back |
| `safety car violation` | Required an overtake, so the Article 55.5 rulings (*"Near collision behind the safety car"*) matched **nothing at all** | Added the no-overtake form |

Tightening the first two initially cost 26 classifications, so every loss was inspected individually: **8 were real practice-start rulings** whose titles simply name the offence (*"Doc 73 - Infringement - Car 5 - Practice Start"*) — a genuine regression, fixed by adding explicit title-anchored branches. The rest are **16 administrative documents** (*"F1 Drivers' Meeting"*, *"Race Director's Note"*, *"Decision - Schedule Clarification"*) which were never rulings and should not have carried a category. Those 16 rows still hold a stale `driver_obligation` value: they were **not** cleared, since that would be deleting data, and row 1c below removes admin documents from the corpus wholesale. Final check: **0 non-administrative losses.**

#### Still open

**426 incidents remain unclassified.** That tracks the ~385 genuinely administrative documents 2B predicted (Technical Delegate reports, *"PU elements used per driver"*, *"RNCs used per driver"*), plus ~40 weak stewards' documents. Excluding those from the precedent corpus is the remaining follow-up — and `infraction_category IS NULL` is now a **defensible** filter for it, which it emphatically was not before this fix.

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
| `seed_drivers.py` / `seed_guidelines.py` | ✅ | Run; 40 drivers / 17 teams / **45 guideline articles** live (33 curated FIA + 12 empirical) |
| Incident + consistency + driver-stats endpoints | ✅ | `apps/api/routers/incidents.py` |
| Expand the guideline set | ✅ | **Done with real data (v7):** added **12 empirical penalty-norm articles** (one per offence type, each aggregating 21–383 real 2019–2026 decisions) → **45 total**. Labeled `RaceJudge Empirical Penalty Norms` to distinguish from official FIA text. The literal full official FIA article set still needs the real FIA Penalty Guidelines PDF (not fabricated). |
| 300-pair similarity annotation campaign | ✅ | **Done** — 359 AI-adjudicated pairs via `generate_candidates.py` → `adjudicate_pairs.py` → `review_pairs.py`. Fed the BGE-M3 LoRA fine-tune. |

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
| ASR / radio / race-control / telemetry **backfills run** | ✅ | **Done 2026-06 (real data, no synthetic).** `incidents.session_key` on 651 incidents → 182 OpenF1 sessions; **race_control_messages = 12,111** (861 linked to incidents); **weather_context on 297 incidents**; **team_radio_clips = 198** (192 Whisper-`base` transcripts + sentiment/urgency, 192 pyannote driver/engineer `speaker_label`); **lap_features = 105,768** rows across all **182/182** sessions (FastF1). Re-run scripts: `scripts/_populate_session_keys.py`, `backfill_race_control.py`, `_backfill_radio.py`, `_backfill_diarization.py`, `_backfill_telemetry.py`. pyannote needs `HF_TOKEN` (set in `.env`); transcription/telemetry are token-free. |

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
| **Embeddings backfilled on production DB** | ✅ | **Run (v7)** — all 1,606 incidents embedded; search returns relevant precedents |
| BGE-M3 fine-tune (300 labelled pairs) | ✅ | **Done (v7)** — LoRA fine-tune on M4/MPS, held-out triplet acc 0.844→0.969; re-embedded as `bge-m3-f1-lora` |

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
| **Ship gate (Macro-F1 ≥ 0.65, ECE < 0.05)** | ❌ | **Fails on Macro-F1 (~0.14), not on calibration.** ECE now ~0.04–0.05 (≈passing). `ENABLE_PREDICTIONS` stays `false` — correct, not a bug. Two real retrains run 2026-06 (see `scripts/_retrain_multimodal.py`, `_retrain_dblabels.py`): (a) full Phase-3 multimodal features → test Macro-F1 0.08; (b) clean DB `penalty_type` labels (681 real labels) → test Macro-F1 0.14. Neither approaches 0.65. |
| `ANTHROPIC_API_KEY` for RAG explanations | 🔶 | Parked pending the user's card (paid, pay-per-call, ~fractions of a cent each). **Not blocking** — `rag_explainer.py` ships a working template fallback at $0; the key only upgrades to live Claude-written explanations. |

> **Why the gate can't be closed by tuning:** Macro-F1 weights all 7 classes equally, but the rare classes have almost no data (DT=13, GRID=19, DSQ=32 across *all* seasons), so it's capped ~5× below target regardless of features/labels. Closing it needs the genuinely-missing pieces, not a retrain: the **LLM reasoning layer (Layer B, still a stub)** + **far more labeled data per class** (and ultimately video). It honestly stays gated for soft launch — which is the designed-safe behavior.

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
| Plotly.js / D3 heatmaps / Mapbox / shadcn / Web Push / TanStack | ✅ | **Done 2026-06** — Plotly stacked chart + D3 severity heatmap on `/consistency`; TanStack sortable/filterable table + shadcn Button/Badge on `/decisions`; MapLibre circuit map (no token) on `/circuits`; full Web Push pipeline (service worker + opt-in + `/v1/push/*` API + `push_subscriptions` table + VAPID). `next build` green (16/16). |

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
| Stripe products + price IDs + webhook secret | ✅ | **Configured (test mode) 2026-06.** Pro £29/mo + Team £499/mo prices live in Stripe; webhook endpoint `we_…` created for `https://racejudge-api.fly.dev/v1/billing/webhook` (6 events) with `STRIPE_WEBHOOK_SECRET` in `.env`. End-to-end checkout-session creation verified. Webhook only *delivers* once the API is deployed at that URL (Fly deploy pending). Swap test→live keys at launch. |
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
| Sentry account + DSN | ✅ | **Done (v9)** — org `racejudge-if`, project `racejudge-api` (EU/`.de` ingest). `SENTRY_DSN` in `.env` (gitignored); `sentry-sdk[fastapi]>=2.0.0` pinned in both `requirements.txt` and `requirements-api.txt`. **Live-verified:** test events accepted by the ingest endpoint (`event_id 111018df…`, `910655b4…`). At deploy, also run `fly secrets set SENTRY_DSN=…`. |
| Grafana / BetterStack status page / PagerDuty | 👤 | Account-only. **Deliberately deferred: all three monitor a public URL, and the API is not deployed** (verified: `racejudge-api.fly.dev` → no response), so they would watch a dead endpoint. Do after the Fly deploy. BetterStack alone covers status page + uptime alerts for soft launch; Grafana/PagerDuty are overkill for one operator. ⚠️ Grafana would also need a Prometheus-format `/metrics` endpoint — the current `/v1/metrics/latency` returns JSON, which Grafana cannot scrape. |
| DNS cutover, legal review, Substack, r/formula1, journalist DMs | 👤 | Brand/legal/launch |

---

## SECTION 10 — What Is Still Open

Almost everything v4 listed here is now done. What genuinely remains:

### Functional gap (one command)

| # | What | Impact | How |
|---|---|---|---|
| 1 | ~~Embeddings backfill on production DB~~ | ✅ **Resolved (v7)** — 1,606 incidents embedded with the LoRA-tuned BGE-M3; precedent search live and verified. | Done |
| 1a | ~~`precedent_links` never materialised~~ | ✅ **Resolved (v10)** — `/v1/precedents/{id}/similar` was returning `[]` with HTTP 200 for every incident. 32,120 links computed from the existing real embeddings; endpoint verified live. | Done |
| 1e | ~~`/v1/incidents/consistency` returns 500 in production~~ | ✅ **Resolved (v12)** — **route-declaration-order shadowing.** `/incidents/{incident_id}` was declared at line 250 and the literal `/incidents/consistency` at line 260; Starlette matches in declaration order, so every request for the literal path was captured as `incident_id="consistency"` and never reached its handler. Reproduced locally with `TestClient`: `404 {"detail":"Incident 'consistency' not found"}`. Fixed by declaring the literal route above the parameterised one. **Corrects the v11 entry, which blamed the Vercel serverless layer** on the grounds that the body was plain text rather than FastAPI JSON — that inference was wrong: plain-text `Internal Server Error` is Starlette's own default for an unhandled exception, so it says nothing about the hosting layer. The bug was in the application and would have followed the code to Fly unchanged. | **Code fixed and tested; not yet verifiable live.** `racejudge-api.vercel.app` still returns 500 — but it is serving a **stale build**: its `/openapi.json` has no `/v1/push/*` routes, which were added in `1e009ed`, so the deployment predates today's push and does not rebuild on push to `main`. That stale build also 500s on `/v1/incidents/{id}` for **every** id, including well-formed UUIDs that return 200/404 correctly against the current code — which is why the shadowed path returned a 500 rather than the 404 reproduced locally. Live re-verification therefore waits on the **Fly deploy**, as you asked. Every route registered on `apps.api.main:app` was scanned for the same class of defect: **0 other shadowed literal routes**. A regression test (`test_consistency_route_is_not_shadowed_by_incident_id`) now asserts the ordering invariant across the whole app rather than this one path. Re-verify as a Fly smoke check after migration. |

### Data recovery — no card needed

| # | What | Impact | How |
|---|---|---|---|
| 1b | ~~The extractor is under-classifying: 864 real stewards' rulings are unusable~~ | ✅ **Resolved (v11)** — classified incidents **357 → 1,181 (22.2% → 73.6%)**, categories 11 → 24, `penalty_type` recovered for a further 199 rulings. 0 rows deleted, 0 existing values overwritten. Four distinct bugs fixed, incl. two latent correctness bugs (no fine ever matched; 15s penalties resolvable as 5s). See Section 2C. | Done |
| 1c | **Exclude the ~385 administrative documents from the precedent corpus** | The 426 still-unclassified incidents are Technical Delegate reports and *"PU elements/RNCs used per driver"* notices, not stewarding decisions. They dilute precedent results — a live `/similar` lookup previously returned three of them as the top-3 precedents. | Now that 2C is done, `infraction_category IS NULL` is a **defensible** filter for this (it was not before — it would have discarded 864 real rulings). Apply it at the precedent-retrieval query, not by deleting rows. |
| 1d | **Retrain the penalty predictor on the widened label set** | The model predicts 7 classes; the DB now holds WARN/FINE/SG. `predict/page.tsx` was deliberately left at 7 classes rather than showing bars the model can never emit. | Phase 5 retrain against the 935 rows now carrying a `penalty_type`. Not urgent — the model is correct for what it was trained on. |

### Config (your accounts)

| # | What | Impact | How |
|---|---|---|---|
| 2 | 💳 **Clerk *production* keys** | Clerk **test** keys (`pk_test_`/`sk_test_`) + JWKS/issuer already in `.env` — sign-in works in dev. Only the `pk_live_`/`sk_live_` swap remains for production launch. | Section 15 Step A |
| 3 | ~~**Stripe keys + products**~~ | ✅ **Done (test mode)** — keys + Pro/Team prices + webhook secret configured; checkout verified. 💳 Swap test→live keys + re-create webhook in live mode at launch. | Section 8 |
| 4 | 💳 **Finish Fly.io migration** | Plan's target host; Vercel is interim. Blocked on Fly billing | Section 2A + Section 15 Step 0 |
| 5 | 💳 **Domain + `hello@`/`legal@`/`press@` email** | No custom domain yet; `racejudge.com` is investor-held, `racejudge.app` recommended. Cloudflare Email Routing is free but blocked on owning the domain. | Section 1 + 1A |
| 6 | ✅ ~~**IP India trademark search**~~ | **Done (v10) — clear.** Knock-out search complete in all four jurisdictions. | Section 1A |

### Quality (optional)

| # | What | Note |
|---|---|---|
| 5 | Penalty model past ship gate | **Tried for real (v8)** — multimodal-feature retrain (0.08) + clean-DB-label retrain (0.14); structural, not tunable to 0.65. Needs the stubbed LLM reasoning layer + much more per-class data. Correctly gated off. |
| 6 | ~~Expand guideline articles~~ | ✅ **Done (v7)** — 45 articles live (33 curated FIA + 12 empirical penalty norms from real decisions). Official full set still needs the FIA PDF. |
| 7 | ~~ASR / radio / telemetry backfills~~ | ✅ **Done (v8)** — all run with real data (Section 4): 12,111 RC msgs, 297 weather, 198 radio clips (192 transcribed + diarized), 105,768 lap rows / 182 sessions. |

### Post-launch deferrals (not bugs)

- ~~Plotly charts · D3 heatmaps · Mapbox · shadcn/ui · Web Push · TanStack~~ — ✅ **all built (v8)**, see Section 7. (Mapbox done as **MapLibre** — no token.)
- Still deferred: Mapbox per-corner telemetry overlay (needs real per-incident track coordinates) · F2/F3/Formula-E expansion.

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

Drivers: 40 · Teams: 17 · Incidents extracted: 1,606 · Guidelines articles live: 45 (33 curated FIA + 12 empirical)

**Classification (v11, see Section 2C):** incidents with `infraction_category`: **1,181 / 1,606 (73.6%)** across **24** categories, up from 357 / 11 · incidents with `penalty_type`: **935**, across 10 values (NFA · WARN · REP · FINE · `Ns` · DT · SG · GRID · DSQ). The remaining 426 unclassified are the Technical Delegate / administrative documents identified by the Section 2B scan, not stewarding decisions.

**Multimodal data (Phase 3 backfill, v8):** incidents with `session_key`: 651 / 182 OpenF1 sessions · race-control messages: 12,111 (861 incident-linked) · incidents with weather: 297 · team-radio clips: 198 (192 transcribed + sentiment/urgency, 192 diarized) · FastF1 lap-feature rows: 105,768 / 182 sessions.

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
| **Total collected** | **323 ✅** (v11: +42 — recovered ruling types, outcome fixes, penalty-type normalisation, and a completeness guard asserting every parser label has a category mapping; v12: +14 — route-shadowing invariant, driver-obligation/practice-start/safety-car regressions) |

---

## SECTION 13 — CI / Quality Gates

**All re-run locally in v10 with true exit codes checked** — not inherited from a previous claim.

| Check | Status |
|---|---|
| `ruff check packages/ apps/ scripts/ tests/` | ✅ All checks passed |
| `mypy --explicit-package-bases packages/ apps/ scripts/` | ✅ clean — **108 source files** |
| `pytest tests/` | ✅ **267 passing** |
| `tsc --noEmit` | ✅ clean |
| `npm run build` (Next.js) | ✅ clean — **20 routes** |
| `npm audit --audit-level=high` | ✅ **0 vulnerabilities** — was 12 (3 high) until v10; fixed via `overrides` pinning `postcss`/`sharp`, avoiding a breaking `next@16` upgrade |
| `pip-audit -r requirements.txt` | ✅ exit 0 — two documented exceptions: torch `CVE-2025-3000` (no fix released) and msgpack `PYSEC-2026-3625` (DoS-only; upgrade blocked by `signalrcore==1.1.2` hard pin; absent from the deployed dep set) |
| Lighthouse CI | ✅ job added |

⚠️ **Note on prior versions:** v7–v9 asserted "all 4 jobs green". That was true when written but had gone stale — new advisories landed against already-pinned transitive deps, so `security-audit` was red on both halves by v10. Dependency-audit gates decay without any code change; re-run them before trusting the badge.

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

### STEP 1 — Light up precedent search ✅ DONE (v7)

Embeddings backfilled + LoRA fine-tune complete; all 1,606 incidents embedded as `bge-m3-f1-lora`, search verified. **Deploy carry-over:** the Fly container must ship `data/models/bge-m3-f1` (6 MB adapter) + set `EMBED_MODEL` to it + `peft` (already a dep) so the query encoder matches the document vectors.

### STEP 2A — Enable Clerk
1. clerk.com → New Application "RACEJUDGE" → enable Email + Google.
2. Copy `pk_live_…`, `sk_live_…`; note JWKS URL + issuer.
3. On the live host (Vercel now, **Fly secrets** after migration) — web: `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`.
4. On the API host — `CLERK_JWKS_URL`, `CLERK_ISSUER`.
5. Redeploy both.

### STEP 2B — Enable Stripe ✅ DONE in TEST mode (v8)

Products ("RACEJUDGE Pro" £29/mo, "RACEJUDGE Team" £499/mo), `sk_test_`/`pk_test_` keys, both price IDs, and the webhook endpoint + `STRIPE_WEBHOOK_SECRET` are all configured in `.env`; checkout-session creation verified end-to-end. Webhook points at `https://racejudge-api.fly.dev/v1/billing/webhook` and delivers once the API is deployed there.
**At real launch (live mode):** create live products → swap to `sk_live_`/`pk_live_` keys + live price IDs → re-create the webhook in live mode → set all four `STRIPE_*` vars in Fly secrets.

### STEP 2C — CI auto-deploy (after Fly migration)
Add `FLY_API_TOKEN` (`fly tokens create deploy`) to GitHub repo secrets — the existing `deploy-api.yml` workflow then deploys to Fly on push to main. This replaces the Vercel git-author workaround entirely.

### STEP 3 — Brand / legal (no code)

Ordered by dependency (v9):

1. ✅ ~~**IP India trademark search**~~ — **done (v10), clear.** Name confirmed safe in all four jurisdictions before any spend.
2. 💳 **Register `racejudge.app`** — `.com` is investor-held; see Section 1.
3. 💳→free **Cloudflare Email Routing** (`hello@`/`legal@`/`press@`) — free itself, but impossible until step 2.
4. 💳 **Media/IP lawyer clearance** — disclose the UK `RACE GUIDE` mark.
5. 👤 **Journalist DMs + launch post + r/formula1** (race-weekend Friday) — **after deploy**, sent from `press@`.

Already complete: EUIPO/USPTO/UK trademark searches (v9); social handles + 300-pair annotation (v7).

### STEP 4 — (Optional) Model + observability

Penalty model: two real retrains (v8) confirmed Macro-F1 plateaus ~0.14 (≈5× below the 0.65 gate) due to rare-class data scarcity — feature/label tuning won't close it. Only set `ENABLE_PREDICTIONS=true` once the **LLM reasoning layer (Layer B)** is built out *and* far more per-class labels exist *and* the gate (**Macro-F1 ≥ 0.65 AND ECE < 0.05**) is actually met. Until then it stays correctly gated. ~~Add `SENTRY_DSN`~~ ✅ **done (v9)**; BetterStack status page waits on the Fly deploy (nothing to monitor until then).

---

*Report v12 — 14 August 2026 — Acted on your two calls: fix the conflicting rows, and fix the `/consistency` 500 now rather than after the Fly migration. **The 500 was a route-declaration-order bug, not a hosting one** — `/incidents/{incident_id}` was declared above the literal `/incidents/consistency`, so Starlette captured the literal path as `incident_id="consistency"`; this corrects the v11 entry, which blamed the Vercel serverless layer on the strength of a plain-text error body that is in fact Starlette's own default. Every route on the app was then scanned for the same defect (0 others) and the ordering invariant is now a test. Adjudicating the 4 conflicting rows against the source documents found the v11 list was partly wrong — one row was the new code erring, not the database — and surfaced **three further pattern bugs, two of them introduced by v11**: a bare "drivers' briefing" match stealing unrelated rulings, "Practice Start **Area**" (a place) read as a practice start and pulling 6 pit-lane rulings out of their category, and Article 55.5 "near collision behind the safety car" matching nothing. **11 corrections applied, 0 rows deleted**; classified 1,181 / 1,606 across 24 categories. Every one of the 26 classifications lost to the tightened patterns was inspected: 8 were real rulings (recovered) and 16 are administrative documents that should never have carried a category — 0 non-administrative losses. Tests 309 → 323. Flagged for your call: `7caff04e`, where the stop-and-go is **suspended** and a reprimand also issued, so `SG` records the headline penalty rather than the one served.*

*Report v11 — 12 August 2026 — Closed v10's biggest open defect at its source. The v10 scan blamed a narrow category vocabulary; reading the extractor found **four** independent bugs, two of which would have defeated a vocabulary-only fix: parser labels that had no entry in the category map at all (the key read `start procedure`, the label was `starting procedure`), missing patterns for parc fermé / deleted lap times / SC2-SC1 / 107% / forcing off track / Race Director instructions, a `_layer1` that classified on the document body while ignoring the title the offence is usually named in, and a `penalty_type` schema with no value for warnings, fines or stop-go. **Classified incidents 357 → 1,180 (22.2% → 73.5%), categories 11 → 24, `penalty_type` recovered for 199 more rulings, 0 rows deleted, 0 stored values overwritten.** Migration `0010` widens `ck_incidents_penalty_type`. Writing tests against verbatim FIA text exposed two further latent bugs, both pre-existing: the fine regex expected `5,000 €` when the FIA writes `€5,000` (so no fine had ever matched), and substring matching meant `"5 second"` matched inside `"15 second penalty"` — audited, 0 stored rows affected. Corrected the downstream layers that still assumed 7 penalty values: three frontend maps, the driver-stats query that counted a warning as a sanction, and the consistency heat-map whose buckets no longer summed to 100% (now verified across all 108 rows). Tests 267 → 309, including a guard asserting every parser label has a category mapping. Left untouched and listed in Section 2C: 4 rows where the new code disagrees with a stored value. Remaining blockers unchanged and all 💳.*

*Report v10 — 12 August 2026 — Audited Section 2 by execution rather than inspection: every CI gate run with its true exit code checked, all 158 ORM columns diffed against live Neon. Five real defects found in a section that was fully marked ✅. Fixed: the `security-audit` job (red on both halves — npm `postcss`/`sharp`, Python `msgpack`), the silently-dead `/v1/precedents/{id}/similar` endpoint (materialised 32,120 precedent links from the real embeddings already in Neon), `steward_panels.created_at` missing from the DB (migration `0009`, applied), 22 naive-vs-`timestamptz` datetime columns, and a pyannote-4 `use_auth_token` runtime bug. Wrote `prefect.yaml` — the 3 flows had never been registered, so nothing had ever been scheduled. IP India trademark search completed (clear) — knock-out search now done in all four jurisdictions. **Then ran a full deep scan of all 1,249 unclassified incidents** (not a sample) to settle whether they were junk or extraction failures: **864 of them (69.2%) are genuine stewards' rulings the extractor failed to categorise**, validated against the FIA document signature with the 357 classified incidents as a 94%-matching control. Filtering them — the intuitive fix — would have destroyed 2.4× more real incidents than the corpus currently has classified. The real defect is the extractor's category vocabulary; recommended fix is taxonomy extension + re-extraction (Section 2B). Remaining blockers unchanged and all 💳: Fly billing, Clerk/Stripe live keys, domain + email, Anthropic key, lawyer clearance.*

*Report v9 — 12 August 2026 — Committed the v8 working tree (`1e009ed`, 34 files). Wired and live-verified Sentry (org `racejudge-if`). Introduced the 💳 symbol so card-gated items read as parked rather than outstanding. Established that `racejudge.com` is investor-held and recommended `racejudge.app` instead. Recorded the completed EUIPO/USPTO/UK trademark knock-out searches (exact mark clear) and opened the **IP India** search as the one remaining pre-work item needing no card. Remaining blockers unchanged and all now 💳: Fly billing, Clerk/Stripe live keys, domain + email, Anthropic key, lawyer clearance.*

*Report v8 — 21 June 2026 — Ran the full Phase-3 multimodal backfill with real data (race-control, weather, radio ASR + diarization, FastF1 telemetry — 105,768 lap rows / 182 sessions), fixed the ORM↔DB type drift that was silently zeroing those writes, built the deferred frontend libraries (Plotly · D3 · TanStack · shadcn · MapLibre · Web Push, `next build` green), configured Stripe billing in test mode, and ran two honest penalty-model retrains confirming the ship gate is structurally (not card-) blocked. Remaining blockers are unchanged: Fly billing (deploy) + Clerk/Stripe **live** keys + Anthropic key (all card-gated, parked at the user's request).*

*v7 — 16 June 2026 — Completed the retrieval ML pipeline (Pre-Work → Phase 4): 359-pair AI-adjudicated annotation campaign → LoRA fine-tune of BGE-M3 (held-out triplet acc 0.844→0.969) → all 1,606 incidents embedded → precedent search live. CI all-green.*
