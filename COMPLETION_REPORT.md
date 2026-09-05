# RACEJUDGE — Final Completion Report v18

> **Updated: 24 August 2026**
> Tests: **606 passing** | **CI: all 4 jobs verified green by execution** (v10/v11 — not merely asserted) | Decisions: 1,606 (2019–2026) | Migrations: **0001–0022 applied** | Phases code-complete: Pre-Work · 1 · 2 · 3 · 4 · 5 · 6 · 7 · 8
> **Precedent search is LIVE** on a LoRA-fine-tuned BGE-M3 — 1,606 incidents embedded in Neon, semantic search verified. **27,133 precedent links materialised** (re-computed after the corpus repair; v10's 32,120 predated it).
> **Currently LIVE on Vercel (interim)** — API: https://racejudge-api.vercel.app · Web: https://racejudge-web.vercel.app
> **Migrating to Fly.io** per the implementation plan (Vercel was a deviation from the spec). Container config staged; blocked only on Fly billing — see Section 2A.
> ✅ **v10's biggest open defect is closed:** classified incidents went **357 → 1,181 (22.2% → 73.5%)** across 24 categories. Nothing was deleted. Section 2C.
> ✅ **v12: the `/consistency` 500 is fixed at its real cause** (route-declaration order, not Vercel — v11 misdiagnosed it) and the 4 conflicting rows are adjudicated and corrected. Section 10 row 1e.
> ✅ **v16: the extractor now reads the document rather than guessing from it.** Session type was 42.5% wrong and is now 0.1% wrong; `sessions` and `events` are no longer empty; contact, incident time and the drivers named in tables are read from the text. Section 3B.
> ✅ **v17: race control messages are attached to the incidents they are actually about.** The linker anchored on the FIA's publication time, kept one incident per message when a message routinely belongs to several, and read only the first driver on the ruling. Rebuilt on a join table (migration `0018`): **861 → 3,293 links**, 0 cross-session. Section 4A.
> ✅ **v18: a quarter of every cited article was a fragment of an ordinary word.** `article_cited` was reported "97.4%, healthy" by counting filled rows — 1,254 of the 5,048 values in them were debris like `artin`, from steward *Martin*'s name. Fixed at both causes and backfilled: **0 fragments, 573 references recovered.** Section 3C.

## What changed in v18 (24 August 2026)

A coverage table asks whether a column is filled. It cannot ask whether what fills it is real — and this one was 97.4% filled with a quarter of its contents nonsense.

- **`Art` had no word boundary in front of it.** The citation pattern began `(?:Art(?:icle)?\.?\s*|Appendix\s+)`, so it matched inside ordinary words, and `_normalize_article` returned whatever it could not parse instead of rejecting it. Steward **Martin** Donnelly's surname was stored as a cited FIA article **402 times**; `art the` 151, `art of` 84, `Articles` 57, `articipates` 52, `arts` 47, `arties` 39, `articular` 38. **1,254 of 5,048 stored citations (24.8%) named no article**, and 194 incidents cited nothing else. This is the project's fifth recurring-pattern instance and a new variant of it: **a loose pattern paired with a normaliser whose failure path returns its input unchanged**, so junk flows to the database rather than being dropped.
- **Requiring a real article number fixes both halves.** Text carrying no number cites nothing and now returns empty for the caller to drop. A rule that only accepts an article number cannot resurrect the word-fragment problem by another route.
- **Rewriting the pattern exposed four things it had been getting wrong**, all of them silent: *"Articles 28.2 and 29.2"* names two articles and **only the first was ever recorded**; `12.4.1.e` was truncated to `12.4.1.`, losing the paragraph letter and keeping a trailing dot; `B1.8.6` was missed entirely because the number could not begin with a letter; and `Appendix L` swallowed its own `, Chapter IV`.
- **The same article sat in the column under two keys.** The corpus writes both `12.4.1.e` (86×) and `12.4.1e` (9×), so four articles were split across two spellings of themselves and no query could group their precedents — the project's second recurring pattern, **comparing two spellings of the same value**. The separator dot is now dropped after a digit only, which leaves `B1.6.2b.i` intact rather than mangling a number whose letter is part of the article.
- **Result: 5,048 references with 1,254 fragments → 3,854 with none**, 573 recovered. Every dropped value is a malformed spelling of one that replaced it — `26.1` became `26.1a`, `Appendix L` became `Appendix L, Chapter IV`, and `11.00` was a time misread as an article. The **233 documents now citing nothing contain no article pattern anywhere in their text**; they are the *"PU elements used per driver up to now"* tallies.
- **The backfill re-runs the fixed extractor over the stored rows**, which the pipeline does not revisit on its own. Nothing is re-parsed from a PDF: every incident is `v2.0-layer1`, so recomputing from `decisions.raw_text` is exactly what the corrected extractor would have written the first time. `scripts/backfill_article_citations.py`, with `--dry-run` and `--backup`.
- **11 incidents claimed weather that nothing could place in time.** `weather_context` asserts a fact about a moment, so it is meaningless unless the moment is known. v16 re-anchored the column and cleared 44 rows built on publication time, but keyed that pass off incidents whose time was *wrong* rather than incidents with **no time at all** — no `incident_time`, no linked race control message. `get_weather_at_incident` already returns None without an anchor, so the current code cannot recreate them; what was missing was a test saying so, and the weather linker had **no test file at all**. **820 → 809 rows, all anchored**, and 11 tests now cover the rule and the selection around it — including the OpenF1 timestamp spellings `strptime` used to drop silently.
- **The publication date had no type, and its timezone label is wrong for half the year.** `decisions.published_at` is TEXT holding the FIA listing page's raw date element — `Published on08.10.23 20:58CET` on 1,447 rows, a bare `07.12.25 15:59` on 159. Sorting that text puts every prefixed row after every bare one and then sorts **day-of-month before month**: ordered by it, the 2024 season opens on **1 September**; it opens on 29 February. `packages/ml/predictor_v2.py` was ordering by it. (The train/test split is by `season`, so this misordered records *within* a season rather than leaking across the boundary.)
- **"CET" means Paris local time, and that was measured, not assumed.** The page prints `CET` in July as well as January, so the label alone cannot say whether it is a fixed UTC+1 or a local clock that follows DST. Against the 642 incidents whose UTC time is known and validated, publication lag is **114 min in winter under either reading** — and in summer **192 min read as fixed UTC+1** against **132 min read as Paris local**. Winter is identical because it must be; only summer separates the two, and the fixed reading inflates it by almost exactly the hour a missed DST change adds. Neither reading produces a document published *before* the incident it describes, so that check alone could not have decided it. Migration **`0022`** adds `published_at_utc TIMESTAMPTZ` **beside** the raw string rather than converting in place — the raw text is what the source said, and a parse that later proves wrong must stay re-derivable. **All 1,606 parse, every one inside its own season**, spanning 2019-03-16 to 2026-06-11.
- **Two stale headline figures corrected.** Sections 4A's summary line and the Section 15 checklist row still carried the intermediate **1,874** race-control links; the live figure is **3,293** across 712 incidents, which the body of Section 4A already stated.

## What changed in v17 (19–22 August 2026)

The v16 audit reached Phase 3's linkers. The same whole-document-scan pattern was there in a different form: the linker anchored on the one timestamp that has nothing to do with the incident.

- **Race control messages were attached by publication time, not incident time.** The linker's first strategy took every message within **1,800 seconds of `Decision.published_at`** — the FIA's paperwork timestamp, hours after the flag and next-day for a technical infringement — while its docstring claimed "±30s around incident time". A third strategy matched a car number **with no time bound at all**. Between them, a waved blue flag for car 2 attached itself to whichever ruling happened to be published nearby. The rules are now: same session; the message **names one of the cars the ruling was issued against**; if both name a turn, they agree; and it falls inside a window around the time the decision states, measured rather than assumed.
- **The window is asymmetric because race control writes after the fact.** On the 393 message/incident pairs that independently agree on both car *and* turn, the median message is **+264s** after the incident, p75 **+470s**, p90 **+847s**. The window is −120s / +900s: the negative side only absorbs the minute the decision rounds its time to.
- **One message can belong to several decisions, and the schema could not say so.** The stewards issue one ruling per driver, so a message about a two-car incident is the record behind two of them. `race_control_messages.incident_id` is a single FK and could only name one — **285 of the matching messages belong to more than one incident**. Migration **`0018`** adds an `incident_race_control` join table and empties the old column rather than dropping it, so the stale interim Vercel build degrades to "no messages" instead of a 500.
- **Only the first driver on a ruling was ever consulted.** `drivers[0]`, on documents that name four in a joint summons and up to twenty in a table — the other nineteen could not match anything.
- **A deleted lap time is the record of one offence and no other.** Deletions are the single most numerous message there is, so one lands inside the window of nearly every ruling against a busy driver: *"CAR 20 (MAG) TIME 1:39.463 DELETED — TRACK LIMITS"* was filed under a **collision** decision. A deletion now has to name the offence the ruling was issued for.
- **Where the decision states no time, wording alone was near-useless.** *"Doc 108 — Infringement — Race Deleted Lap Times"* names eighteen drivers and prints no time, so the fallback keyword rule gave it **33 messages of which not one was a deleted lap time** — starting procedure, pit lane speeding, collisions, yellow flags — while missing the deletions that are the actual record, because "deleted" was not in the keyword list. Untimed rulings now require the message to **name the same offence**; the document's links are now 37 deletion messages and nothing else. Race control has no words for a safety-car-line time, parc fermé or a 107% decision, so those fall back to wording rather than being held to an offence they can never match.
- **Result: 861 → 3,293 links** across **712 incidents** and **2,798 distinct messages**, 427 of them shared between rulings, **0 cross-session**. Verified through the ORM in both directions. (The intermediate figure of 1,874 was measured before the ingest was re-run against the corrected session keys and the duplicates were removed — the two bullets below.)
- **Two readers were still on the emptied column.** `packages/ml/enrich.py` (the race-control signal fed to the penalty predictor) and `scripts/_backfill_radio.py` (the anchor time for radio clips) both selected `race_control_messages.incident_id`; both would have silently returned nothing. Now joined through the association table.
- **`scripts/backfill_race_control.py` could not run as documented.** Every sibling backfill script loads `.env`; this one did not, so its own usage line fails on "DATABASE_URL not set" unless the caller exports it by hand.
- **Race control messages were only ingested for 181 of the 380 sessions.** The backfill drives off `incidents.session_key`, which pointed into an empty table until v16 — so **87 of the 268 sessions holding incidents had no messages at all** (330 incidents), and their rulings could never link to anything. Re-run against the corrected keys.
- **The ingest had no working de-duplication, and re-running it doubled the table.** `fetch_and_store_rc_messages` skipped a message it already held by comparing `str(row.date)` — which renders as `2024-05-26 14:30:00+00:00` — against OpenF1's raw `2024-05-26T14:30:00+00:00`. The key never matched, so each re-run re-inserted every message in the session: **12,437 duplicate rows** had accumulated. Fixed to key on parsed datetimes, and migration **`0019`** deletes the copies and adds the `uq_rcm_session_date_message` constraint that should have been there — nothing in the schema had ever said the row was meant to be unique.
- **Every lap in the database began at the same instant.** `lap_features.time` is the moment a lap started and it is what places an incident on a lap; **all 105,768 rows held their session's scheduled start**, one distinct value per session, so lap 1 and a lap two hours later were indistinguishable. `scripts/_backfill_telemetry.py` falls back to the session start when FastF1's `LapStartDate` is `NaT` — and FastF1 only computes `LapStartDate` during the *telemetry* load, which that script does not do, so the fallback written for the occasional out-lap fired on every lap ever ingested. This is the third instance of the project's other recurring pattern: **a NOT NULL column filled with a fallback constant rather than the real value.** `LapStartTime` was present the whole time; `t0_date` turns it absolute, and `t0_date` (`max(Date - Time)`) is reproducible to the millisecond from the `car_data` stream alone, verified against a full telemetry load on three sessions — so the repair needed no telemetry download. **104,327 of 105,768 rows now hold a real lap start and 179 of 182 sessions vary.** The three sessions FastF1 has no laps for are set to NULL, not left holding a false constant; migration `0021` drops the NOT NULL that forced the invented value in the first place and narrows the PK to `(id)`, the composite `(id, "time")` having existed only for a TimescaleDB hypertable that was never created.
- **The two permanently empty columns now hold real data, and one of them could never have held what its name says.** `position_change`: **208 rows**, from a new `lap_features.position` (migration `0020`) that FastF1's lap table had carried all along. `video_refs`: **784 rows** — but **0 of 1,606 documents contain a URL**, so the column can never hold a video link; what the stewards do record is the evidence they reviewed, and only vision evidence is stored, only when a reviewing verb governs it. See Section 10 rows 1g and 1o.
- **The administrative documents are filtered at query time, and the filter v12–v16 recommended was the wrong one.** Those reports called `infraction_category IS NULL` a defensible exclusion. Measured, it discards **249 genuine rulings** that carry a real penalty but no taxonomy label — 134 of them No Further Action, which is precedent of exactly the kind a steward searches for. The filter adopted is *decides something*: `infraction_category IS NOT NULL OR penalty_type IS NOT NULL`, on **both** retrieval legs, excluding the 96 that decide neither. No rows deleted.
- **The penalty predictor was retrained, and it failed to train.** XGBoost rejects a label set with a hole in it, and 2019–2023 contains no drive-through at all. Fixing the crash exposed the more serious bug behind it: `predict` zipped seven class names against six probability columns **with `strict=False`**, so every class after the gap was reported under its neighbour's name — silently, including in the evaluation that feeds the ship gate. Now trained on a dense label space and expanded back under the right names, with `strict=True` so the mismatch can never hide again. **Test 2025: Macro-F1 0.2605, ECE 0.0512 — the 0.65 gate still fails** (v16: 0.14), and it fails for lack of data, not modelling: 402 labelled training rows across 10 penalty types. `position_change` was ablated and makes no difference (0.2613 without, 0.2605 with) — it is non-zero on 15 of 337 training rows.
- **Tests: 495 → 558.**

---

## What changed in v16 (17–18 August 2026)

Every remaining defect in the extraction layer, found by measuring each stored field against what the document itself says. Six were real; three suspected ones were not.

- **Session type was wrong on 42.5% of the corpus.** Measured against the `Session` line the documents print: 486 disagreements in the 1,144 documents that state one. Practically every practice, qualifying and sprint ruling was filed as a *race*, because the phrase *"having received a report from the Race Director"* sits above the field and the parser scanned the whole document for the first session-like word. It now reads the `Session` field and falls back to a scan only when there is no field, with "Race Director / Race Control / Race Steward" masked out. **486 → 1 disagreement (0.1%)**, and the one remaining is a post-race press conference. `sprint_qualifying` is separated from `sprint` for the first time.
- **`sessions` was an empty table that 651 incidents pointed into.** `incidents.session_key` was a bare integer referencing nothing, so every Phase 3 join through it was unverifiable. 380 sessions loaded for the 76 events OpenF1 covers; 1,011 post-2023 incidents relinked on *(the event the document names, the session the document states)*. That caught **23 incidents from the 2026 Canadian GP pointing at 2025 Canadian GP sessions**. Now **1,027 / 1,229** post-2023 incidents carry a key, **0 dangling, 0 cross-event**, and migration **`0016`** makes it a real foreign key.
- **`contact` was inferred from the category label, never read.** A collision-category ruling was stamped `true` and everything else `NULL`, which is a restatement of the category rather than a fact about the incident. It is now read from the **Fact** section only — the Reason argues about contact that did not happen, and *"near collision behind the safety car"* was flagged as contact until that was fixed. **689 rows corrected**; known on **1,142 / 1,606**, up from 460.
- **The incident time was never extracted.** FIA decisions print two `Time` fields — publication in the letterhead, and the incident itself directly above `Session`. Only the letterhead one was visible to anything, so an incident's only timestamp was when the FIA published the paperwork: routinely hours after the flag, next day for a technical infringement. The incident time is now read, converted from local circuit time to UTC using the session's `gmt_offset`, and **checked against the session window** — **686 stored, 262 rejected** as paperwork times. Migration **`0017`**.
- **Weather was being manufactured from the publication time.** With no race-control message attached, `weather_linker` fell back to `Decision.published_at` and took the nearest reading *however far away it was* — up to 50 minutes, long enough for rain to start and stop. It now uses the real incident time and refuses anything more than 10 minutes out. Coverage **297 → 673** rows, mean **21.9s** from the incident, worst **577s**; 44 pre-existing readings too distant to mean anything were cleared.
- **164 rulings named their drivers in a table and were stored against nobody.** Deleted lap times, safety-car delta breaches and one document penalising nine drivers at once list car and driver in columns rather than in a subject header. **1,127 driver entries recovered, every one resolved.** Incidents with no driver at all: **457 → 293**, and what remains is genuinely driverless — protests, team technical infringements, panel substitutions, promoter decisions.
- **Three suspected defects were checked and two are not defects.** `lap` (7.5%) and `corner` (26.7%) are NULL exactly when the document does not state them — perfect agreement on a 400-row sample each, nothing to fix. The third, `position_change`, v16 called "not derivable from anything held". **v17 corrected that**: `lap_features` carried no position column, but FastF1's lap table — the very table the telemetry backfill already reads — has carried `Position` all along and it was simply never selected. See Section 10 rows 1g and 1o.
- **Tests: 395 → 495.**

---

## What changed in v15 (16 August 2026)

Three defects, all found by pulling on the one judgement call v14 left open.

- **A suspended penalty is no longer indistinguishable from a served one.** `penalty_type` records what the stewards imposed and says nothing about whether it was enforced. Hulkenberg's 2026 Canadian GP stop-and-go (document 99) was suspended for the rest of the season and never served, yet was stored as a bare `SG` — identical to a driver who served one. Migration **`0012`** adds `penalty_suspended`.
- **It is three-state, not a boolean, because the corpus is.** **22 decisions carry a suspended penalty** — not the 2 an earlier scan suggested. Only **6** are suspended in full; the other **16** are part-fines ("fined €50,000, €25,000 of which is suspended"), where half the penalty really was paid. A boolean would have to assert one of those two things about both, so the column is `'full'`, `'partial'`, or NULL.
- **Read from the Decision section only.** The surrounding prose uses the same word for unrelated things — a red-flagged *"session, which was suspended"*, and a 2020 protest arguing at length whether DAS is a *"suspension system"*. Both sit in the Reason section and both would otherwise have registered as suspended penalties. A Super Licence suspension is excluded by name: that is a race ban, where the suspension *is* the penalty rather than a reprieve from one. Validated against **all 26 documents in the corpus containing the word, each verdict checked by hand against the verbatim ruling: 26/26**.
- **43 documents were filed under the wrong season.** The whole 2026 Canadian GP was stored as 2025. The FIA lists a new year's opening events on the outgoing year's filter page, and the scraper stamped each document with the season of the page it was found on rather than the one the document states. Confirmed by two independent signals — the year in the FIA's own filename and the year printed on the document. The scraper now reads the year off the document; the 43 rows and `data/parsed/decisions.jsonl` are both corrected. **Driver resolution was unaffected** — re-resolving every subject and counterparty against the corrected season changes nothing, because the subject header states name and number together — but the rows were in the wrong bucket for every season-scoped variance endpoint.
- **BM25 search was returning nothing on every query.** The full-text conditions matched against `query`, the name of the CTE, rather than `query.q`, its column; Postgres read the bare name as a whole-row record and rejected `tsvector @@ record`. A surrounding `try/except` logged it and returned an empty list, so it never surfaced: **hybrid search has been running on vector similarity alone**, with the keyword half contributing nothing to the reciprocal-rank fusion. "collision turn 1" now returns 5 ranked hits where it returned 0.
- **Tests: 367 → 395.**

---

## What changed in v14 (15 August 2026)

The one-driver-per-incident limitation recorded in v13 is closed. An incident row can now hold every driver a ruling is issued against, and — separately — the other cars in the incident.

- **Counterparties are recorded for the first time.** A collision was stored as a ruling against one car with no trace of the car it hit, so "who else was in this incident" was unanswerable and collision precedent had nothing to match on. The stewards state the parties in the decision's Fact line ("Turn 2 incident between Cars 11, 27 and 31"); that line is now parsed. **297 of 1,606 incidents carry 308 counterparty references** — every impeding, unsafe-release, forcing-off and collision ruling in the corpus. 307 of the 308 resolve to a named driver.
- **They are stored in a new column, `involved_drivers`, not merged into `drivers[]`.** Every driver-scoped query in the API reads `drivers @> [{"code": …}]` and means by it *was penalised*. Merging the two would have added someone else's penalty to the record of the driver they drove into — a driver's stats page would count the incidents where they were the victim. Migration `0011` adds the column with a GIN index mirroring the one on `drivers`.
- **Joint summonses now name every driver they are issued to.** The FIA lists them under one header, the first on the "No / Driver" line and the rest on bare continuation lines; only the first was ever read. Both such documents in the corpus (2020 Italian GP, documents 23 and 24) now carry all four drivers. The backfill only ever *grows* `drivers[]`, so the hand-verified single-driver rows from v13 were not touched.
- **A tenth `:param::type` statement was found and fixed.** `GET /v1/incidents?driver=…` — the main incident list filter, the most-used driver query in the product — used `drivers @> :d::jsonb` and 500'd on every call. v13 fixed nine of these; this one was in a `text()` fragment attached to a SQLAlchemy `select()` rather than a raw query, which is why the earlier sweep missed it. Verified 200 against the live database.
- **`POST /v1/incidents/extract` no longer disagrees with the backfill.** It never passed the decision title to the extractor, and layer 1 classifies against the title — for many rulings it is the only place the offence is named. The same document extracted through the endpoint came out with a different `infraction_category` than the one already stored.
- **Tests: 351 → 367**, covering the joint summons, the two- and three-car Fact forms, the Fact/Reason section boundary, and the invariant that the accused is never filed as their own counterparty (verified 0/1,606 in the database).
- **Not guessed:** one counterparty, car 46 at the 2025 Bahrain GP, is stored with its number and a null driver. The corpus names that car exactly once and never says who drove it.

---

## What changed in v13 (14 August 2026)

Section 3 (Phase 2 — Structured Extraction) audited end to end, by execution. Everything below was already marked ✅; four defects were sitting underneath the ticks. Pushed as `93a9e9e`.

- **The subject of the ruling was wrong in one decision out of four.** Layer 1 picked the car number out of the title and body by word order, so whenever the title named the *other* party the wrong driver was recorded — "Decision - Car 44 - Alleged impeding of Car 18" was filed against Stroll rather than Hamilton. The decisions state their subject outright in a header field ("Driver 44 - Lewis Hamilton"), which is the one unambiguous statement in the document, so that now wins. **Measured against the 1,017 decisions that state their own subject: 737 correct (72.5%) → 1,017 (100.0%), zero regressions.**
- **The per-season car-number history was per-season in shape only.** The upstream roster API exposes each driver's number *today*, and the seed wrote that single value into every season. So **car 33 (Verstappen through 2021) and car 4 (Norris through 2025) resolved to nobody at all**, and **car 3 resolved to Verstappen for six seasons that were Ricciardo's**. Reserve numbers (Lawson 40, Hadjar 37, Bearman 38 *and* 50, Lindblad 36, Shwartzman 97) were missing outright. Corrected from the decisions themselves — **verified against all 164 season/number pairs the corpus states verbatim: 164/164.**
- **342 corpus rows re-resolved** — 152 filled that were empty, 190 corrected. `drivers[]` populated goes **997 → 1,149**, and every populated row now resolves to a *named* driver rather than a bare number.
- **Nine SQL statements were broken in production code.** `:param::type` does not survive SQLAlchemy's `text()` under asyncpg — it raises a syntax error at the colon. Every occurrence failed: **driver stats, review, MCP and API-key revocation all 500'd on every call**, as did both driver-filtered search paths. Fixed with `CAST(… AS …)`; `incidents.incident_id` is `TEXT` and needed no cast at all, so its `::uuid` was wrong in type as well as syntax. Driver stats additionally had the current season **pinned to `2025`**, reporting every 2026 driver as being on zero points, and still stubbed `full_name` to the three-letter code.
- **The OCR and LayoutLM layers were unreachable.** `backfill_incidents.py` never passed a PDF path, and the extractor only escalates when it is handed one — so a scanned decision had no recovery path and would have landed with empty fields. Now wired, but deliberately only for text-poor documents: the extractor also escalates on sparse fields, which would have pushed the 85 administrative tables through OCR for nothing. **No document in the corpus needs OCR today** (`needs_ocr` is false for all 1,606, minimum text length 284 characters), so this changes nothing now and exists for the scanned document that eventually arrives.
- **Tests: 323 → 351.** The additions are per-season resolution across every changed number, the subject-header precedence, and the corpus phrasings the car-number pattern used to miss.
- **Corrected in this report:** teams is **43 rows, 17 of them active** — the "17 teams" figure counted only the active ones. `layoutlm_extractor.py` and `tesseract_fallback.py` live in `parsers/`, not `extractors/`.

---

## What changed in v12 (14 August 2026)

Your two calls, both done and pushed (`cd85c28`, `91cc877`). Neither turned out to be what v11 said it was.

- **The `/consistency` 500 was a route-ordering bug, not a hosting one — my v11 diagnosis was wrong.** `/incidents/{incident_id}` was declared above the literal `/incidents/consistency`, and Starlette matches in declaration order, so every request for that page was captured as `incident_id="consistency"`. v11 blamed the Vercel serverless layer because the error body was plain text rather than FastAPI JSON; that inference was wrong — plain-text `Internal Server Error` is Starlette's own default for an unhandled exception and says nothing about the host. **The bug was in the application and would have followed the code to Fly.** Fixed, every route scanned for the same defect (0 others), and the ordering invariant is now enforced by a test across the whole app.
- **The 4 conflicting rows are resolved — and the v11 list was partly wrong.** One row (`07d03f4f`) was the *new code* erring, not the database. Adjudicating each against its source document surfaced **three further pattern bugs, two introduced by v11 itself**: a bare "drivers' briefing" match stealing the escape-road / yellow-flag / crossing-the-track rulings, "Practice Start **Area**" (a place in the pit lane) read as a practice start and pulling 6 pit-lane rulings out of their category, and the Article 55.5 rulings ("near collision behind the safety car") matching nothing at all. **11 corrections applied, 0 rows deleted.**
- **Every classification lost to the tightened patterns was inspected — all 26.** 8 were real practice-start rulings whose titles simply name the offence (recovered via title-anchored branches); the other 16 are administrative documents ("F1 Drivers' Meeting", "Race Director's Note") that should never have carried a category. **0 non-administrative losses.** Those 16 still hold a stale `driver_obligation` value — deliberately not cleared, since that is deleting data, and row 1c removes admin documents wholesale.
- **The live API is serving a stale build**, so the consistency fix cannot yet be verified in production. `racejudge-api.vercel.app/openapi.json` has no `/v1/push/*` routes — added in `1e009ed` — so the deployment predates today's push and does not rebuild on push to `main`. That old build also 500s on `/v1/incidents/{id}` for *every* id, including well-formed UUIDs that return 200/404 correctly against current code. Verified locally instead: **200, 108 rows, all summing to 100%.** Live re-check happens at the Fly deploy, as you asked.
- **Tests: 309 → 323.** Includes the app-wide route-shadowing guard and regression tests written from verbatim corpus text for all three pattern bugs.
- **Sections 1 and 2 re-audited end to end (new Section 2D).** Every checkable claim re-executed rather than re-read: Alembic head `0010`, 0 ORM drift across 158 columns, 32,120 precedent links, 1,606/1,606 embedded, both security-audit halves clean, every cited file present. **Nothing is left undone that is not card-gated.** Four stale/wrong claims corrected — including "categories 11 → 24", which is actually **10 → 24** (the pre-fix snapshot has 10 categories summing to exactly 357), and a Section 1A block still presenting the completed IP India search as open work.
- ~~⚠️ **One judgement call for you — `7caff04e`.**~~ **Closed in v15.** The row keeps `penalty_type = 'SG'` — what the stewards imposed — and now also carries `penalty_suspended = 'full'`, recording that it was never served. Both facts are preserved rather than one being chosen over the other. 21 further suspended rulings were found and populated in the same pass. See "What changed in v15".

---

## What changed in v11 (12 August 2026)

The under-classification defect v10 identified was fixed at its source: the extractor's vocabulary, not the data. **823 real stewards' rulings recovered, 199 penalty outcomes recovered, 0 rows deleted.** Full account in **Section 2C**.

- **Classified incidents: 357 → 1,181 of 1,606 (22.2% → 73.5%).** Distinct categories **10 → 24** (v12 correction: earlier reports said 11; the pre-fix snapshot has 10, and they sum to exactly the documented 357). The 425 still unclassified track the ~385 genuinely administrative documents the v10 scan predicted.
- **Four separate bugs, not one.** (a) Labels the parser emitted had no entry in the category map — the key read `start procedure` while the label was `starting procedure`, so five ruling types extracted a type and then stored a NULL category anyway. (b) No patterns at all for parc fermé, deleted lap times, SC2-SC1, 107%, forcing off track, Race Director instructions. (c) `_layer1` classified on the document body only, ignoring the title — and the FIA title is often the only place the offence is named. (d) `_PENALTY_TYPE_MAP` had no WARN/FINE/SG, and the `CHECK` constraint could not store them.
- **`penalty_type` recovered for 199 rulings** — 113 FINE, 77 WARN, 9 SG. These had a plainly stated decision and were storing NULL because the schema had no value for them. Migration **`0010`** widens `ck_incidents_penalty_type`.
- **Two latent correctness bugs caught by the new tests**, both pre-existing: the fine regex expected `5,000 €` but the FIA writes `€5,000`, so no fine ever matched; and because the penalty map is matched by substring, `"5 second"` matched inside `"15 second penalty"` — a 15s penalty would have been recorded as 5s. Stored data audited: **0 rows affected**, the outcome regex had matched the full number first.
- **Display and aggregation layers brought in line.** Three frontend penalty maps and two SQL aggregations still assumed the old 7-value set: a warning counted as a "sanction" in driver stats, and the consistency heat-map's buckets no longer summed to 100%. Verified: all 108 heat-map rows now sum to 100%.
- **Tests: 267 → 323.** Includes a completeness guard asserting every label the parser can emit has a category mapping — the invariant whose absence caused the defect.

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
| GitHub repo + 48 commits, pushed | ✅ | Re-counted v12 (`git rev-list --count HEAD` = 48); the "32" was stale. Working tree clean, `main` pushed |
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

**IP India search — ✅ done by you (v10), nothing found.** Recorded here for the lawyer's file; **no action remains.** The method used, should it ever need repeating: [IP India Public Search](https://tmrsearch.ipindia.gov.in/tmrpublicsearch/) → Wordmark → `RACEJUDGE` (*Start With* and *Contains*), `RACE JUDGE`, and `RACEJUDGE` under **Phonetic** (India weights phonetic similarity heavily) — each across classes **42** (software/SaaS), **41** (sports info) and **9** (downloadable software). A live **Registered** or **Objected/Advertised** mark in those classes would be the flag. None found.

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
| Migrations 0001–0021 | ✅ | `packages/db/migrations/versions/` — **`0009` in v10** (`steward_panels.created_at`, see 2B), **`0010` in v11** (widen `ck_incidents_penalty_type` for WARN/FINE/SG + `Ns`, see 2C), **`0011` in v14** (`incidents.involved_drivers` + GIN index), **`0012` in v15** (`incidents.penalty_suspended` + check constraint + partial index), **`0013`–`0015`** with the corpus repair (`decisions.event_id`, `PIT` penalty type, nullable event venue, `decisions.is_precedent`), **`0016` in v16** (`incidents.session_key` becomes a real FK, ON DELETE SET NULL, + index), **`0017` in v16** (`sessions.gmt_offset`, `incidents.incident_time` + index). **`0018` in v17** (`incident_race_control` join table — one race control message can be the record behind several rulings; the old single FK column is emptied rather than dropped so the stale interim Vercel build degrades to "no messages" instead of a 500). **`0019` in v17** (de-duplicates `race_control_messages` and adds the uniqueness constraint on `(session_key, date, message)` that would have prevented it). **`0020` in v17** (`lap_features.position` — FastF1's lap table has always carried it and it was never selected; it is what makes `position_change` derivable). **`0021` in v17** (`lap_features.time` becomes nullable and the PK narrows to `(id)` — the NOT NULL is what forced a fallback constant into all 105,768 rows, and the composite `(id, "time")` key existed only for a TimescaleDB hypertable that was never created; the migration is guarded so a database that *does* have the extension is left alone). Neon confirmed at head **`0021`**; all twenty-one applied |
| SQLAlchemy ORM models (incl. `StewardPanel`) | ✅ | `packages/db/models.py` — **all 158 columns diffed against live Neon (v10); 3 classes of drift found and fixed, now 0 mismatches** |
| Prefect deployment manifest | ⚠️ | **`prefect.yaml` written in v10** — the 3 flows were code-only and had never been registered (see 2B). Applying it needs a worker host → 💳 Fly |
| Async engine + URL normaliser (asyncpg) | ✅ | `packages/db/database.py` — strips libpq `sslmode`/`channel_binding` |
| FastAPI app + `/health` + settings | ✅ | `apps/api/main.py`, `apps/api/core/config.py` |

### Infrastructure accounts

| Item | Status | Notes |
|---|---|---|
| **Neon Postgres** (eu-west-2 / London) | ✅ | Provisioned, **all 21 migrations applied (head `0021`, re-verified v17 against live Neon)**, data loaded — **live**. 23 tables. All 1,606 incidents embedded (`bge-m3-f1`), HNSW index present, and nothing modified since its embedding. **`precedent_links` materialised — 27,133 links** (32,120 in v10, recomputed after the v15 corpus repair) |
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

**The actual defect is the extractor's category vocabulary being far too narrow.** It recognises 10 categories (pit_lane_speed 94, yellow_flag 77, impeding 71, collision 54, unsafe_release 28, vsc 15, track_limits 12, erratic_driving 3, safety_car 2, blue_flag 1 — summing to exactly the 357 classified). *(v12: this line and the two summary counts said 11; the snapshot has 10.)* The scan shows it is missing at minimum: **deleted lap times / track limits (153), parc fermé (85), safety-car-line time SC2-SC1 (66), technical breach (21), forcing another driver off the track, failure to follow Race Director's instructions, unsafe release variants, overtaking under safety car, starting-procedure infringements, practice starts, 107% rule, driver conduct (32), false start (7)** — 292 distinct ruling titles in the unclassified set alone.

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
| Incidents with `infraction_category` | 357 (22.2%) | **1,181 (73.5%)** |
| Distinct categories | 10 | **24** |
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

New patterns were **appended** rather than interleaved, so first-match-wins guarantees every previously classified document keeps its label. Confirmed by re-run: 0 existing categories changed by the backfill itself. **v12 then changed 11 rows deliberately**, on your instruction and after reading each source document — see "Conflicting rows" below. That is the only route by which a stored value has ever been overwritten.

#### Categories after the fix

`technical` 196 · `track_limits` 181 · `impeding` 97 · `pit_lane_speed` 94 · `parc_ferme` 90 · `collision` 85 · `yellow_flag` 79 · `safety_car_line_time` 55 · `unsafe_release` 52 · `driver_obligation` 34 · `driving_slowly` 31 · `race_director_instructions` 30 · `107_percent` 28 · `forcing_off_track` 27 · `vsc` 17 · `practice_start` 16 · `pit_lane` 14 · `safety_car` 14 · `start_procedure` 14 · `false_start` 13 · `weighing` 7 · `crossing_track` 3 · `blue_flag` 2 · `erratic_driving` 2

These are the **v12** figures, i.e. after the 11 conflict corrections below. The five categories that moved against v11 are exactly those corrections: `impeding` 95→97, `practice_start` 11→16, `safety_car` 11→14, against `race_director_instructions` 35→30, `driver_obligation` 36→34, `yellow_flag` 80→79, `erratic_driving` 3→2.

`penalty_type` after: NFA 394 · 5s 136 · **FINE 113** · **WARN 77** · 10s 75 · REP 66 · DSQ 32 · GRID 19 · DT 13 · **SG 10** — REP 67→66 / SG 9→10 is the single `7caff04e` correction.

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
| `7caff04e…` | `penalty_type` | `REP` → `SG` | Resolved in v15 — kept as `SG`, with `penalty_suspended = 'full'` alongside it |

✅ **`7caff04e` was a judgement call, and it is now resolved (v15).** The Decision reads: *"A mandatory Stop-and-Go penalty imposed after the Race. This penalty is suspended… In addition the driver is Reprimanded."* Rather than choose between what was *imposed* and what was *served*, the row now records both: `penalty_type = 'SG'` with `penalty_suspended = 'full'`. Migration `0012` added the column; 22 rulings across the corpus carry a suspension.

#### Three pattern bugs found while adjudicating

Two were introduced by v11; all three are now covered by regression tests written from verbatim corpus text.

| Pattern | Defect | Fix |
|---|---|---|
| `driver obligation breach` | Matched a bare *"drivers' briefing"* / *"drivers' meeting"*, which appears in the *Reason* narrative of wholly unrelated rulings — it had captured the escape-road, yellow-flag and crossing-the-track decisions. Only visible on cleaned text, because the cleaner normalises the curly apostrophe the raw pattern missed | Now requires offence language (*late for*, *late attendance*, *failed to attend*, *behaviour in*). Also added *"Late attendance of National Anthem"*, a real ruling that would otherwise have been lost |
| `practice start infringement` | Matched *"Practice Start **Area**"* — a place in the pit lane — pulling **6 pit-lane rulings** ("overtook several cars in the Fast Lane whilst traversing the Working Lane to the Practice Start Area") out of their real category | Requires the practice start to be the *act*. Kept narrow deliberately: those same rulings discuss practice starts in their Reason (*"did perform a genuine practice start"*), so any looser rule takes them straight back |
| `safety car violation` | Required an overtake, so the Article 55.5 rulings (*"Near collision behind the safety car"*) matched **nothing at all** | Added the no-overtake form |

Tightening the first two initially cost 26 classifications, so every loss was inspected individually: **8 were real practice-start rulings** whose titles simply name the offence (*"Doc 73 - Infringement - Car 5 - Practice Start"*) — a genuine regression, fixed by adding explicit title-anchored branches. The rest are **16 administrative documents** (*"F1 Drivers' Meeting"*, *"Race Director's Note"*, *"Decision - Schedule Clarification"*) which were never rulings and should not have carried a category. Those 16 rows still hold a stale `driver_obligation` value: they were **not** cleared, since that would be deleting data, and row 1c below removes admin documents from the corpus wholesale. Final check: **0 non-administrative losses.**

#### Closed in v17

**425 incidents remain unclassified**, and v12–v16 read too much into that. The claim above — that they track the ~385 administrative documents, so `infraction_category IS NULL` is now a *defensible* exclusion filter — was **wrong, and is corrected in v17**. Measured directly rather than inferred: of the 345 uncategorised incidents that are embedded and pass `decisions.is_precedent`, **249 record a real penalty** — 134 No Further Action, 27 × 5s, 20 reprimands, 16 fines, 14 × 10s, 13 disqualifications, 10 grid drops, 10 warnings, 3 drive-throughs, 2 stop-gos. An NFA on a Turn 2 incident is precedent of exactly the kind a steward searches for. The taxonomy fix cut the damage from 864 real rulings to 249; it did not remove it.

Only **96** decide neither an offence nor a penalty, and those are the genuine paperwork: Stewards Bulletins and Substitutions, *"Formation of the Grid"*, *"Decision - Free Practice 3"*, protests, summonses, permissions to start, right-of-review communications.

So the filter adopted is **`infraction_category IS NOT NULL OR penalty_type IS NOT NULL`** — a document earns its place by *deciding something*. It keeps all 249 and excludes all 96. It is applied to both retrieval legs (`apps/api/retrieval/semantic_search.py` as `_DECIDES_SOMETHING`, and `bm25_search.py` — a hybrid search is only as clean as its dirtiest branch) and pinned by `tests/test_precedent_filter.py`. The other ~245 administrative documents were already excluded by `decisions.is_precedent`.

### SECTION 2D — Re-audit of Sections 1 & 2 (v12)

You asked whether anything in Sections 1 and 2 was still outstanding. Every checkable claim was **re-executed**, not re-read. Result: **no work is left undone that is not card-gated** — but four claims were stale or wrong and are now corrected in place.

| Re-verified by execution (v12) | Result |
|---|---|
| Alembic head on live Neon | `0010` — all ten applied ✅ |
| ORM ↔ Neon drift, all 158 columns | **0 mismatches** ✅ (re-run after the v11/v12 model changes) |
| Table count / `precedent_links` / embeddings / HNSW | 22 tables · 32,120 links · 1,606/1,606 embedded · `idx_incidents_embedding` present ✅ |
| `security-audit` — both halves | `npm audit --audit-level=high` → **0 vulnerabilities**; `pip-audit` → **no known vulnerabilities**, 1 documented ignore ✅ |
| ruff · mypy · pytest · tsc · `next build` | all green — 323 tests, 109 source files, 16/16 pages ✅ |
| Every file cited in Sections 1–2A | all present ✅ (`fly.toml`, `apps/web/fly.toml`, `requirements-api.txt`, `prefect.yaml`, `Dockerfile`, both CI workflows, rosters, `decisions.jsonl` = 1,606 lines) |
| Labelled similarity pairs | 359 in `data/annotations/similarity_pairs.jsonl` (215 similar / 144 dissimilar) ✅ |

**Four corrections made as a result:**

1. **"Distinct categories 11 → 24" was wrong — it is 10 → 24.** The pre-fix snapshot holds exactly 10 categories, and they sum to precisely the 357 documented as classified. Corrected in four places.
2. **The Neon row still read "all 9 migrations applied (head `0009`)"** while migration `0010` had been applied in v11. Corrected.
3. **Section 1A still presented the IP India search as an "Open action"** with step-by-step instructions, though the Section 1 table records it as done by you in v10. It read as outstanding work when none remained. Rewritten as a record of method.
4. **"32 commits" was stale** — the repo is at 48.

**One observation, not a defect:** the `annotation_pairs` table in Neon is **empty (0 rows)** while the 359 labelled pairs live in `data/annotations/similarity_pairs.jsonl`. That is consistent — the pairs were produced by the offline adjudication pipeline and fed the LoRA fine-tune from the file; the table backs the `/v1/annotations` review UI, which nobody has used yet. Worth knowing before anyone reads an empty table as data loss.

---

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
| `layoutlm_extractor.py` / `tesseract_fallback.py` | ✅ | 3-layer fallback chain — both in `packages/pipeline/parsers/` (v13 path correction). **Reachable as of v13**: the backfill never passed a PDF path, so layers 2–3 could not fire. No document in the corpus needs them (`needs_ocr` false for all 1,606; shortest text 284 chars), so all 1,606 rows are legitimately `v2.0-layer1`. |
| `incident_extractor.py` | ✅ | `packages/pipeline/extractors/incident_extractor.py`. **v14:** resolves every subject of a ruling, not just the first, and resolves the incident's counterparties into the new `involved_drivers` field. |
| `driver_resolver.py` (per-season car numbers) | ✅ | **Fixed in v13.** `#1` champion handover was right (2022–25 VER, 2026 NOR), but every *other* number was the driver's present-day one repeated across all seasons — car 33 and car 4 resolved to nobody, car 3 to the wrong driver. Real history curated from the decisions; **164/164 season/number pairs stated in the corpus now resolve correctly.** |
| `article_resolver.py` | ✅ | |
| `backfill_incidents.py` | ✅ | **Run** — 1,606 incidents populated, live |
| `seed_drivers.py` / `seed_guidelines.py` | ✅ | Run; **42 drivers** / **43 teams (17 active)** / **45 guideline articles** live (33 curated FIA + 12 empirical). v13 correction: earlier reports said "17 teams", which counted only the active ones. **v16: +2 drivers** (Robert Shwartzman, Luke Browning) — the resolver knew them and the `drivers` table did not, so their incidents had no row to join to. **0 driver codes appearing in incidents now lack a `drivers` row.** |
| Incident + consistency + driver-stats endpoints | ✅ | `apps/api/routers/incidents.py`. **Driver stats 500'd on every call until v13** — a `:param::jsonb` cast that asyncpg rejects, plus the current season pinned to `2025` and `full_name` stubbed to the driver code. All three fixed; the same cast bug was found and fixed in 8 further statements across review, MCP, key revocation and both search paths. **v14 found a tenth**, on `GET /v1/incidents?driver=…` — the main list filter — which had 500'd on every call for the same reason; and `POST /v1/incidents/extract` was not passing the decision title to the extractor, so it classified the same document differently than the backfill did. |
| Expand the guideline set | ✅ | **Done with real data (v7):** added **12 empirical penalty-norm articles** (one per offence type, each aggregating 21–383 real 2019–2026 decisions) → **45 total**. Labeled `RaceJudge Empirical Penalty Norms` to distinguish from official FIA text. The literal full official FIA article set still needs the real FIA Penalty Guidelines PDF (not fabricated). |
| 300-pair similarity annotation campaign | ✅ | **Done** — 359 AI-adjudicated pairs via `generate_candidates.py` → `adjudicate_pairs.py` → `review_pairs.py`. Fed the BGE-M3 LoRA fine-tune. |

### 3A — Field-level extraction coverage (v13, measured)

Phase 2's stated milestone is >90% F1 on field extraction. That was never measured per field, so here it is across all 1,606 rows. The important distinction is between a field that the extractor *misses* and one the FIA simply *does not write down* — most of the low numbers are the second kind, and no amount of extractor work moves them.

| Field | Populated | Reading |
|---|---|---|
| `article_cited` | **1,373 (85.5%)** | **v13–v17 read 1,564 (97.4%) and called this "healthy"; it was 24.8% debris (corrected v18).** Counting filled rows could not see that 1,254 of the 5,048 values in them named no article — `artin` 402 times, from a steward's surname. Now **0 fragments across 3,854 references**, with 573 recovered that the old pattern silently dropped. The count *fell* because junk-only rows became empty, not because anything real was lost. Section 3C. |
| `reasoning_text` | 1,606 (100%) | Healthy. The 2,000-character hard slice reported in v13 is **gone** — 0 rows sit at the cap, longest is 5,986 characters, and all 1,606 were re-embedded afterwards (no row has been edited since its embedding). |
| `infraction_category` | 1,181 (73.5%) | **The 425 gaps are *not* all administrative — v13–v16 said they were and were wrong (corrected v17).** 249 of them record a real penalty; only 96 decide neither an offence nor a penalty. Row 1c. |
| `drivers[]` | **1,313 (81.8%)** | Was 997 before v13, 1,149 before v16. **100% agreement with every decision that states its own subject.** v14: joint summonses hold 4 drivers each. **v16: +164 tabular rulings, 1,127 driver entries, 0 unresolved.** |
| `involved_drivers` | 297 (18.5%) | **New in v14.** The other cars in the incident — 308 references, 307 resolved to a named driver. Empty by design for the ~80% of rulings that concern one car only. |
| `penalty_type` | 1,039 (64.7%) | Tracks the classified set; administrative documents carry no penalty. 11 values, `PIT` added in v15's corpus repair. |
| `penalty_suspended` | 22 (1.4%) | **New in v15.** 6 `full`, 16 `partial`. NULL means the penalty was served in the ordinary way, which is the overwhelming majority. |
| `session_key` | **1,027 (63.9%)** | Was 651. 2019–22 is structurally 0/377 — OpenF1 has no data before 2023. Within 2023+ it is now **1,027 / 1,229 (83.6%)**, up from 53%, with 0 dangling and 0 cross-event keys, enforced by a real FK (`0016`). |
| `contact` | **1,142 (71.1%)** | **v16: read from the document's Fact section**, not inferred from the category. Was 460. 113 `true`, 1,029 `false`; NULL means the document does not settle it. |
| `incident_time` | **642 (40.0%)** | **New in v16** (v16 reported 686; the live column holds 642). The time the incident happened, from the Time field above `Session`, converted to UTC via the session's `gmt_offset` and validated against the session window. Re-derived from the documents in v17: **every one of the 642 is backed by a document that states that time, and 0 are recoverable beyond them** — 127 further incidents state a time that converts *outside* its session window, which is what a publication time does. |
| `weather_context` | **809 (50.4%)** | Was 297, keyed off publication time. Now anchored on the earliest linked race control message, failing that the time the document states — never publication time — and bounded to 10 minutes. **813 of v17's 820 were within 95s of that anchor**, worst 496s. It rose from v16's 673 because v17's race control fix gave 173 more incidents a real anchor. **v18: −11.** Those 11 had no anchor of any kind — no `incident_time`, no linked message — so nothing in the database said when they happened and their weather could only have been right by luck. Every remaining row is anchored. |
| `corner` | 429 (26.7%) | **Source reality.** Of 400 sampled rows with no corner, **0** name a turn anywhere in the text. Re-verified in v16. |
| `lap` | 121 (7.5%) | **Source reality, not a defect.** Of 400 sampled rows with no lap, **0** contain an explicit lap number. FIA decisions usually cite a time, not a lap. Re-verified in v16. |
| `penalty_points` | 103 > 0 (6.4%) | Correct — points are rare in real rulings. The other 1,503 are a true `0`, not a missing value. |
| `grid_positions` | **55 (3.4%)** | Correct, not a gap. Filled on exactly the 55 rulings whose `penalty_type` is `GRID`, and nowhere else — a lap-time penalty has no grid drop to record. Values are the real ones: 1, 2, 3, 5, 10, 15 places. Earlier reports listed this column as empty; that was wrong. |
| `video_refs` | **784 (48.8%)** | v17: the vision evidence the stewards state they reviewed, read from the ruling. **Not URLs — the corpus contains none.** See below. |

**What this says.** The fields the FIA actually writes down are extracted at 97–100%. The weak numbers are almost entirely documents that do not contain the fact, which is worth stating plainly because "7.5% lap coverage" reads like a broken extractor and is not one.

**Follow-ups** (none blocking, all recorded in Section 10):

1. ~~**`reasoning_text` truncation.**~~ **Closed.** No row is truncated and the corpus has been re-embedded since.
2. **The two dead columns — both now filled from real sources (v17).** `position_change` and `video_refs` were schema no code path wrote, and v16 concluded neither *could* be written. That was true of the database and false of the sources.

   - **`video_refs` — 784 of 1,606.** Its name suggests links, and links are the one thing the corpus cannot supply: **not one of the 1,606 documents contains a URL of any kind**, so there is nothing to store and nothing that could be constructed without inventing it. What the documents do carry is the stewards' own account of the evidence, written to a near-fixed formula — *"The Stewards reviewed positioning/marshalling system data, video, timing, team radio and in-car video evidence."* 803 documents carry such a clause. `extract_video_refs` reads the **vision** items out of it — `video`, `in-car video`, `cctv` — and deliberately leaves telemetry, timing, GPS, team radio and positioning data alone, because those are not what this column is for. The clause must follow a reviewing verb: "video" also appears in narrative prose, and taking every mention would record evidence that was never examined. NULL, not `[]`, when the document names none, so *"reviewed no video"* stays distinguishable from *"does not say"*.
   - **`position_change` — see row 1g.** `lap_features` had no position column; FastF1's lap table has carried one all along and it was simply never selected. Migration `0020` added it, and filling it exposed a separate defect in `lap_features.time` (row 1o).

   (`grid_positions` was listed here in v13–v16 and does not belong: it is filled on all 55 `GRID` rulings by `extract_grid_positions`, and is NULL elsewhere because there is no grid drop to record.)
3. ~~**One driver per incident.**~~ **Closed in v14/v16.** `drivers[]` holds every driver a ruling is issued against, including the 164 rulings that name them in a table (v16), and the other cars in an incident are recorded separately in `involved_drivers`.
4. ~~**The `events` table is empty.**~~ **Closed.** 158 events with steward panels read from the decisions' signature blocks; `/v1/incidents/variance/by-panel` has data to read.
5. ~~**Session type is wrong on 42.5% of the corpus.**~~ **Closed in v16.** See Section 3B.

### 3B — Reading the document instead of guessing (v16)

Each stored field was measured against what the document itself states, rather than against whether it was populated. Populated-but-wrong is the failure mode that coverage tables hide.

| Field | Before | After | How it was checked |
|---|---|---|---|
| session type | 486 / 1,144 disagreements (**42.5%**) | **1 (0.1%)** | Against the `Session` line printed in each document |
| `session_key` | 651 rows pointing into an empty table | 1,027, **0 dangling / 0 cross-event** | FK + a join on (event the document names, session it states) |
| `contact` | inferred from the category label | 689 rows corrected, known on 1,142 | Read from the Fact section; negations and "near collision" handled |
| incident time | did not exist | 686 stored, 262 rejected | Each converted time must fall inside its session's window |
| weather | nearest reading to *publication* time, unbounded | 673 rows, mean 21.9s out | 10-minute ceiling; 44 meaningless pre-existing rows cleared |
| drivers on tabular rulings | 164 documents named nobody | 1,127 entries, 0 unresolved | Every extracted name put through `DriverResolver` |

The recurring bug in every one of these was the same: **scanning the whole document for a pattern instead of reading the section that states the fact.** (v18: the same table, applied to `article_cited`, found the field 24.8% wrong — see 3C. Populated-but-wrong is exactly what 3A's coverage number could not see.) The Decision section is the operative ruling, the Reason argues about penalties that were *not* imposed, the Fact states the contact, and the Session field states the session. Section-scoped parsing is the defence, and the tests now assert it — a decision whose Reason discusses a suspension, a collision that did not happen, or a Race Director report must not read as any of those things.

### 3C — The cited articles were a quarter debris (v18)

`article_cited` is what makes "show me every precedent under Article 33.3" answerable, and it is the feature the penalty predictor reads. 3A measured it as **1,564 populated (97.4%)** and wrote "Healthy." Measuring the *contents* instead:

| | References stored | Naming no article | Share |
|---|---|---|---|
| Before | 5,048 | **1,254** | **24.8%** |
| After | 3,854 | **0** | **0.0%** |

**Two causes, both required.** The pattern began `(?:Art(?:icle)?\.?\s*|Appendix\s+)` with **no leading `\b`**, so `Art` matched inside ordinary words. `_normalize_article` then **returned its input unchanged** when it found no article number, so the fragment was stored rather than dropped. Either one alone is harmless; together they put a quarter of a steward-facing column beyond use.

| Stored as a cited FIA article | Times | Actually |
|---|---|---|
| `artin` | 402 | steward **Mart**in Donnelly's surname |
| `art the` | 151 | "…p**art the** driver played…" |
| `art of` | 84 | "p**art of** the track" |
| `Articles` | 57 | the bare word, citing nothing |
| `articipates` | 52 | "p**articipates** in the sprint" |
| `arts` / `arties` / `articular` | 124 | "spare p**arts**", "both p**arties**", "no p**articular** advantage" |

**Fixing it recovered more than it removed.** Requiring a real article number after the prefix is what makes the fragments impossible, and rewriting the pattern to do that exposed four silent failures: enumerated citations (*"Articles 28.2 and 29.2"*) recorded only their first article; `12.4.1.e` was truncated to `12.4.1.`; `B1.8.6` was never matched at all, the number being unable to start with a letter; and `Appendix L` swallowed its own `, Chapter IV`. **573 references were recovered** — `Appendix L, Chapter IV` ×111, `12.4.1e` ×95, `B1.8.6` ×34, `12.2.1i` ×25, `40.3` ×14, `28.2` ×12.

**Every value dropped is a malformed spelling of one that replaced it.** Verified individually across all 74 non-fragment losses: `26.1` → `26.1a`/`26.1b` (the sub-clause the document actually names), `12.4.1` → `12.4.1e`, `Article\nB1.8.6` → `B1.8.6`, `Appendix L` → `Appendix L, Chapter IV`, `2` → `Appendix 2`, and `11.00` was a **time** misread as an article. The **233 documents left citing nothing contain no `Art`+digit and no `Appendix` anywhere in their text** — their titles are *"PU elements used per driver up to now"* and *"RNCs used per driver up to now"*.

**One article, one key.** The corpus writes `12.4.1.e` 86 times and `12.4.1e` 9 times; four articles were split across two spellings of themselves, so a precedent query on either found only part of the set. The separator dot is now dropped **after a digit only** — `B1.6.2b.i` keeps its dot, because there the preceding letter is part of the article number and removing it would rewrite the citation.

**Applied to the stored rows.** `scripts/backfill_article_citations.py` (with `--dry-run` and `--backup`) re-runs the two fixed functions over `decisions.raw_text` for all 1,606 incidents, updating 1,001. It re-parses no PDF and invents nothing: every incident is `v2.0-layer1`, so this is precisely what the corrected extractor would have produced on the first pass. Verified in the live database afterwards — 0 fragments, 0 values still carrying an `Art`/`Article` prefix.

### 3D — Two columns that could not answer the question they were for (v18)

**`weather_context` on 11 incidents nothing could place in time.** The column states what the conditions were at a moment. v16 re-anchored it on the earliest linked race control message, failing that the time the decision states — never publication time, which is the FIA's paperwork clock — and cleared 44 rows built the old way. That pass keyed off incidents whose time was *wrong*; these 11 have **no time at all**: no `incident_time`, no linked message. Nothing in the database says when they happened, so the weather on them could only have been right by luck. `get_weather_at_incident` already returns `None` without an anchor, so the current code cannot recreate them — the gap was that **nothing tested the rule**, and the weather linker had no test file. **820 → 809, all anchored**, plus 11 tests covering the gap ceiling, nearest-reading selection, the distance reported alongside the value, and the OpenF1 timestamp spellings that `strptime` silently dropped.

**`published_at` could not be ordered, and its timezone label is wrong for half the year.** It is TEXT holding the listing page's raw date element — `Published on08.10.23 20:58CET` (1,447 rows) and a bare `07.12.25 15:59` (159). Sorting that text sorts every prefixed row after every bare one, then by day-of-month before month:

| Ordering the 2024 season by… | First document |
|---|---|
| `published_at` (text — what `predictor_v2.py` did) | `01.09.24 16:11` — **1 September** |
| `published_at_utc` (v18) | `Published on29.02.24 17:54CET` — **29 February** |

The train/test split is by `season`, so this misordered records *within* a season rather than leaking across the boundary — worth stating precisely rather than overstating.

**Which timezone `CET` means was measured, not assumed.** The page prints `CET` on every row, July included, so the label cannot itself say whether it is a fixed UTC+1 or a local clock following DST. Against the 642 incidents whose UTC time is known and validated:

| Reading | Winter lag | Summer lag |
|---|---|---|
| Fixed UTC+1 (the literal label) | 114 min | **192 min** |
| Paris local (`Europe/Paris`) | 114 min | **132 min** |

Winter is identical under both, as it must be — there is no DST to disagree about. Only summer separates them, and the fixed reading inflates it by almost exactly the hour a missed DST change adds, while Paris local brings summer to within 18 minutes of winter. Notably, **no row is published before the incident it describes under either reading**, so the obvious sanity check could not have decided this; the distributions had to be compared. The two raw shapes were checked the same way and are the same clock (median lags 120 and 138 minutes, no negatives).

Migration **`0022`** adds `published_at_utc TIMESTAMPTZ` **beside** the raw string rather than converting in place — the raw text is what the source said, and a parse that later proves wrong must remain re-derivable from it. **All 1,606 parse, every one inside its own season**, 2019-03-16 to 2026-06-11. Text carrying no full date yields NULL rather than a plausible-looking wrong instant, and an impossible date (`31.02`, hour 25) yields NULL rather than raising.

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
| ASR / radio / race-control / telemetry **backfills run** | ✅ | **Done 2026-06 (real data, no synthetic).** `incidents.session_key` on **1,027** incidents (was 651) → **380 sessions now held in the `sessions` table** for the 76 events OpenF1 covers, 182 of them carrying telemetry; **race_control_messages = 12,111** (861 linked to incidents); **weather_context on 673 incidents** (was 297); **team_radio_clips = 198** (192 Whisper-`base` transcripts + sentiment/urgency, 192 pyannote driver/engineer `speaker_label`); **lap_features = 105,768** rows across all **182/182** sessions (FastF1). Re-run scripts: `scripts/_populate_session_keys.py`, `backfill_race_control.py`, `_backfill_radio.py`, `_backfill_diarization.py`, `_backfill_telemetry.py`. pyannote needs `HF_TOKEN` (set in `.env`); transcription/telemetry are token-free. |
| **`sessions` table populated and made authoritative (v16)** | ✅ | Until v16 `incidents.session_key` was an integer referencing an **empty table** — every join in this section was through a key that pointed at nothing, and nothing could detect a wrong one. 380 sessions loaded with `session_type`, start/end and `gmt_offset`; incidents relinked on *(event named by the document, session stated by the document)*, catching 23 incidents filed against the previous year's Canadian GP sessions. Migration **`0016`** adds `fk_incidents_session_key` (ON DELETE SET NULL) + an index; **`0017`** adds `sessions.gmt_offset` and `incidents.incident_time`. |
| **Weather linkage corrected (v16)** | ✅ | `weather_linker` fell back to `Decision.published_at` when no race-control message was linked, and accepted the nearest reading at any distance — up to 50 minutes off. It now uses `incidents.incident_time` and enforces `MAX_WEATHER_GAP_S = 600`. Mean distance from the incident: **21.9s**; worst: 577s. |
| **Race control linkage rebuilt (v17)** | ✅ | See Section 4A. **861 → 3,293 links** over a join table (migration `0018`), 712 incidents, 2,798 distinct messages, 427 shared between rulings, **0 cross-session**. |

---

### SECTION 4A — The race control linker (v17)

`race_control_linker.py` was the last place the v16 pattern was still live: it anchored on the timestamp that has nothing to do with the incident.

**What it did.** Three strategies, tried in order. The first took every message within **1,800 seconds of `Decision.published_at`** — the FIA's publication time, hours after the flag and next-day for a technical infringement — while the docstring above it claimed "±30s around incident time". The second matched the driver code as a substring, which matches "HAM" inside other words. The third matched a car number **with no time bound at all**. Only `drivers[0]` was ever consulted, on documents that name four drivers in a joint summons and up to twenty in a table.

**What it does now.** A message belongs to an incident when all of these hold:

| Rule | Basis |
|---|---|
| Same session | `sessions` became authoritative in v16 |
| The message **names one of the cars the ruling was issued against** | Parsed out of the text (`CAR 44 (HAM)`, `CARS 44 AND 55`, `CAR NO.16`), not found as a substring. A lap time is not a car number: `CAR 11 (PER) TIME 1:23.092 DELETED` names car 11, not 1, 23 and 92 |
| If both name a turn, they agree | Rejects 82 links across 22 incidents — a driver with two rulings minutes apart at different corners |
| Inside **−120s / +900s** of the time the decision states | Race control writes after the fact. Measured on the 393 pairs that independently agree on car *and* turn: median **+264s**, p75 **+470s**, p90 **+847s**. The negative side only absorbs the minute the decision rounds to |
| A deleted lap time names the offence it records | Deletions are the most numerous message there is, so one lands in the window of nearly every ruling against a busy driver — *"CAR 20 (MAG) TIME 1:39.463 DELETED — TRACK LIMITS"* was filed under a **collision** decision |
| Where no time is stated, the message names the **same offence** | Wording alone gave *"Doc 108 — Race Deleted Lap Times"* (18 drivers, no time) **33 messages, not one of them a deleted lap time**, while missing the deletions that are the actual record. Now 37 deletion messages and nothing else |

**The schema was structurally lossy.** The stewards issue one ruling per driver, so a message about a two-car incident is the record behind two of them. `race_control_messages.incident_id` is a single FK and could only name one; **285 of the matching messages belong to more than one incident**. Migration **`0018`** adds an `incident_race_control` join table, indexes the message side, and **empties the old column rather than dropping it** — the interim Vercel build does not rebuild on push and still selects it, so emptying degrades it to "no messages" instead of a 500. Drop it after the Fly cutover.

**Two readers were still on that column** and would have silently returned nothing: `packages/ml/enrich.py` (the race-control signal fed to the penalty predictor) and `scripts/_backfill_radio.py` (the anchor time for radio clips). Both now join through the association table.

**The ingest underneath it had two faults of its own.** It drives off `incidents.session_key`, which pointed into an empty `sessions` table until v16, so messages had only ever been fetched for **181 of the 380 sessions** — **87 of the 268 sessions holding incidents had none at all**, and those rulings could not link to anything however good the matching rules were. And its de-duplication never fired: the key was `str(row.date)` on the stored side against OpenF1's raw ISO string on the incoming side, two spellings of the same instant that never compare equal, so each re-run re-inserted the whole session. **12,437 duplicate rows** had built up. The key is now built from parsed datetimes on both sides, migration **`0019`** deletes the copies, and `uq_rcm_session_date_message` makes the schema state the invariant rather than leaving it to the writer.

---

## SECTION 5 — Phase 4: Precedent Retrieval

| Item | Status | File |
|---|---|---|
| `semantic_search.py` (pgvector HNSW) | ✅ | |
| `bm25_search.py` (tsvector) | ✅ | **Was returning 0 hits on every query until v15** — the full-text conditions matched `query` (the CTE name) instead of `query.q` (its column), so Postgres rejected `tsvector @@ record` and a surrounding `try/except` swallowed it. Hybrid search had been running on vector similarity alone. Fixed and verified against the live corpus. |
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
| **Ship gate (Macro-F1 ≥ 0.65, ECE < 0.05)** | ❌ | **Fails on Macro-F1, not on calibration.** `ENABLE_PREDICTIONS` stays `false` — correct, not a bug. Three real retrains, all honest, none synthetic: (a) full Phase-3 multimodal features → test Macro-F1 0.08; (b) clean DB `penalty_type` labels, 2026-06 → 0.14; (c) **v17, on the repaired corpus → Macro-F1 0.2605, ECE 0.0512 (test 2025, n=187; val 2024 0.3101 / 0.0533)**. Best yet and still 2.5× short of the gate. Run (c) also **found a silent defect** — see Section 10 row 1p — and established that `position_change` makes no measurable difference at its current coverage (ablation: 0.2613 without, 0.2605 with; non-zero on 15 of 337 training rows). |
| `ANTHROPIC_API_KEY` for RAG explanations | 🔶 | Parked pending the user's card (paid, pay-per-call, ~fractions of a cent each). **Not blocking** — `rag_explainer.py` ships a working template fallback at $0; the key only upgrades to live Claude-written explanations. |

> **Why the gate can't be closed by tuning:** Macro-F1 weights all 7 classes equally, but the rare classes have almost no data. Re-counted from the live DB in v17: across *all* seasons `DT`=10, `SG`=10, `DSQ`=31, `GRID`=55 — and the 2019–2023 training split holds **402 labelled rows across 10 penalty types with not one drive-through in it**, drive-throughs appearing in this corpus only from 2024. A class the training split never sees cannot be predicted at all, so its F1 is 0 and the macro average carries that zero no matter how good the rest is. Closing it needs the genuinely-missing pieces, not a retrain: the **LLM reasoning layer (Layer B, still a stub)** + **far more labeled data per class** (and ultimately video). It honestly stays gated for soft launch — which is the designed-safe behavior.

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
| 1b | ~~The extractor is under-classifying: 864 real stewards' rulings are unusable~~ | ✅ **Resolved (v11), refined (v12)** — classified incidents **357 → 1,181 (22.2% → 73.5%)**, categories 10 → 24, `penalty_type` recovered for a further 199 rulings. 0 rows deleted. Four distinct bugs fixed in v11, incl. two latent correctness bugs (no fine ever matched; 15s penalties resolvable as 5s); **three more found in v12** while adjudicating the conflicting rows, two of them introduced by v11 itself. 11 stored values corrected on your instruction. See Section 2C. | Done |
| 1c | ~~**Exclude the administrative documents from the precedent corpus**~~ | ✅ **Resolved in v17, and the filter v12–v16 recommended was the wrong one.** Those reports said `infraction_category IS NULL` was now "defensible". Measured instead of inferred, it still discards **249 genuine rulings** — 134 NFA, 27 × 5s, 13 DSQ, 10 GRID and more — because the taxonomy has no label for them, not because they decided nothing. Only **96** of the uncategorised decide neither an offence nor a penalty (Stewards Bulletins/Substitutions, "Formation of the Grid", protests, summonses, permissions to start); the other ~245 administrative documents were already excluded by `decisions.is_precedent`. | Done — filtered at query time, no rows deleted. `_DECIDES_SOMETHING` = `infraction_category IS NOT NULL OR penalty_type IS NOT NULL`, applied to **both** retrieval legs (`semantic_search.py` and `bm25_search.py`) and pinned by `tests/test_precedent_filter.py`. |
| 1d | **Retrain the penalty predictor on the widened label set** — **run in v17, and it found a bug** | The model predicts 7 classes; the DB holds 11, including `PIT`. v16 widened the gap further: `session_type` was wrong on 42.5% of the corpus and `contact` was inferred rather than read, so two model features had materially changed values. `predict/page.tsx` is deliberately still at 7 classes rather than showing bars the model can never emit. | ✅ **Retrained on your instruction** (scikit-learn + XGBoost, local, no spend). **Test 2025: Macro-F1 0.2605, ECE 0.0512 — the 0.65 gate still FAILS**, so the predictor correctly stays gated. That is an honest improvement on v16's 0.14, not a pass. It first crashed, and the crash was a real defect (row 1p). Two findings worth recording: **(a)** `position_change`, newly sourced in 1g, was ablated and makes no difference — 0.2613 without it vs 0.2605 with — because only **15 of the 337 labelled training rows** have a non-zero value; it is now a real feature carrying real data, but far too sparse to move a gate. **(b)** The train split (2019–2023) contains **402 labelled rows across 10 penalty types and not one `DT`** — drive-throughs appear in this corpus only from 2024. Rare-class scarcity, not a modelling error, is what holds the gate shut. |
| 1p | ~~**A penalty class missing from the training split silently renamed every class after it**~~ (found + fixed v17) | `PenaltyPredictor.predict` zipped `PENALTY_CLASSES` (7 names) against XGBoost's probability row **with `strict=False`**. XGBoost infers its classes from `y` and emits one column per class *present in training* — so with `DT` absent, it returned 6 columns, `zip` truncated the names to 6, and `GRID`'s probability was reported as `DT`, `DSQ`'s as `GRID`. Silent: no error, no shape complaint, just wrong labels on every prediction and on the evaluation that feeds the ship gate. The retrain in 1d surfaced it by crashing first — XGBoost rejects the gapped label set outright (`Expected: [0 1 2 3 4 5], got [0 1 2 3 5 6]`), which is the only reason the mislabelling was ever visible. | ✅ Done. `dense_label_space()` maps the classes actually present onto a gapless `0..k-1` for training; the predictor stores that mapping and `_expand_proba` puts the columns back under their own names, with `0.0` for a class the training split never saw — the honest value, since the model has no evidence for it. The `zip` is now `strict=True`, so the same mismatch raises instead of hiding. Both validation mappings drop rows whose class is outside the training space rather than passing XGBoost a `NaN` label, and `save`/`load` round-trip the label space (a model saved before this covers all 7 classes, which is what the missing key means). |
| 1f | ~~**`reasoning_text` is truncated at 2,000 characters on 289 rows**~~ | ✅ **Resolved.** 0 rows sit at the cap; longest reasoning is 5,986 characters, and all 1,606 rows were re-embedded afterwards (`bge-m3-f1`, 16–17 Aug) — no row has been modified since its embedding. | Done |
| 1g | ~~**Two columns have never held a value**~~ (v13, re-checked v16, **sourced v17**) | `position_change` and `video_refs` were 0/1,606, and v16 declared `position_change` underivable. That was wrong in the same way as 1o: `lap_features` carried no position column, but FastF1's lap table — already read by the telemetry backfill — has always carried `Position`, and it was simply never selected. `video_refs` was underivable *as named*: **0 of 1,606 documents contain a URL**, so the column can never hold a video link. What the documents do carry is the stewards' evidence sentence. **`grid_positions` was wrongly counted with these two in v13–v16:** it holds 55 values, one for every `GRID` ruling (1, 2, 3, 5, 10 and 15 places), and is NULL on the other 1,551 because those rulings carry no grid drop. Nothing was ever wrong there. | ✅ Done, both from real sources fitting the existing tables, nothing invented. **`position_change`: 208 rows.** Migration `0020` adds `lap_features.position` from FastF1; `scripts/backfill_position_change.py` derives the per-incident delta across the incident lap. Validated against the rulings — the largest losses are collisions and pit-lane speeding (car 55 causing a collision → −10; car 27 pit-lane speeding → −8) and the large `+0` cluster is Safety Car Procedure infringements, where positions are frozen by rule. 47 incidents have no lap time to place them and 79 the timing cannot place; those stay NULL. **`video_refs`: 784 rows** (`video` 285, `video`+`in-car video` 401, `in-car video`+`cctv` 57, and four smaller shapes), parsed from the evidence clause by `extract_video_refs`. Only vision evidence is stored — telemetry, timing, GPS, positioning and team radio are deliberately excluded — and a reviewing verb is required, so a narrative mention of a camera does not count. NULL, not `[]`, when the document names none. |
| 1l | **Two tables have never held a row** (v16) | `embeddings` and `ingested_hashes` are 0 rows with no code path writing them — embeddings live on `incidents.embedding`, and the scraper de-duplicates against `data/ingested_hashes.json` rather than the table. Same trap as 1g, one level up. (`annotation_pairs` is also empty but that is by design — the 359 labelled pairs use the documented JSONL fallback; `push_subscriptions` is empty because nobody has subscribed yet.) | Drop the two dead tables in a migration, or point the code at them. Destructive, so it is your call. |
| 1m | **The ORM models 16 of the 22 live tables** (v16) | `lap_features`, `push_subscriptions`, `annotation_pairs` and `embeddings` are reached by raw SQL rather than through `packages/db/models.py`, and `incidents.embedding`/`embedded_at`/`embedding_model` plus `decisions.search_vector` are deliberately unmapped (pgvector / tsvector). Column-level drift across the 164 mapped columns is **0**. Not a defect — but v12's "0 mismatches, 158 columns" was checked in one direction only, and the unmapped surface is where a future schema change can drift unnoticed. | Either map them or leave a note in `models.py` saying they are intentionally raw-SQL. No action needed for launch. |
| 1n | **`race_control_messages.incident_id` is emptied but still present** (v17) | Migration `0018` moved the links to the `incident_race_control` join table and set the old column to NULL rather than dropping it — the interim Vercel deployment does not rebuild on push and still selects it, so dropping it now would 500 that build instead of degrading it to "no messages". | Drop the column in a follow-up migration **after the Fly cutover**, together with the `idx_rcm_incident` index. |
| 1o | ~~**`lap_features.time` was the session start on all 105,768 rows**~~ (found + fixed v17) | The column is the moment a lap began, and it is what places an incident on a lap. **Every one of the 182 sessions held exactly one distinct value** — its scheduled start — so a lap at the end of a two-hour race carried the same timestamp as lap 1. `scripts/_backfill_telemetry.py` reads FastF1's `LapStartDate` and falls back to the session start when it is NaT; FastF1 only computes `LapStartDate` during the **telemetry** load, and the backfill loads with `telemetry=False`, so it was NaT on *every* lap and the fallback — written for the occasional out-lap — fired for all of them. This is the third instance of the project's other recurring pattern: **a NOT NULL column filled with a fallback constant instead of the real value**, which reads as ordinary data and is wrong by up to two hours. It silently invalidated the first 262 `position_change` values, which were computed, checked, found to be 225 × `+0`, and cleared. | ✅ Done. `LapStartTime` was present on every lap the whole time; `t0_date` (= `max(Date - Time)`, reproduced exactly from the `car_data` stream alone, so no full telemetry download) turns it absolute. Migration `0021` drops NOT NULL — a column that cannot always be known is what forced the invented value — and narrows the PK to `(id)`, the composite `(id, time)` having existed only for a TimescaleDB hypertable that was never created. `scripts/backfill_lap_times.py` repairs it; the fallback is removed at source. |
| 1h | ~~**`session_key` is missing on 578 of 1,229 post-2023 incidents**~~ | ✅ **Resolved (v16).** The real problem was worse than coverage: the `sessions` table was empty, so the 651 keys that existed referenced nothing. 380 sessions loaded, incidents relinked on the event and session each document states, 23 cross-year mislinks caught. **1,027 / 1,229 post-2023 (83.6%), 0 dangling, 0 cross-event**, enforced by an FK (`0016`). The remaining 202 are events OpenF1 does not cover. | Done |
| 1i | ~~**Session type is wrong on 42.5% of the corpus**~~ | ✅ **Resolved (v16).** Practically every practice, qualifying and sprint ruling was filed as a *race* — the parser scanned the whole document and hit "Race Director" before reaching the `Session` field. 486 disagreements → **1**. | Done |
| 1j | ~~**`contact` restates the category label**~~ | ✅ **Resolved (v16).** Read from the Fact section; 689 rows corrected; known on 1,142 / 1,606. | Done |
| 1k | ~~**164 rulings are stored against no driver**~~ | ✅ **Resolved (v16).** Deleted-lap and multi-driver penalty tables are read; 1,127 driver entries recovered, 0 unresolved; driverless incidents 457 → 293, all genuinely driverless. | Done |

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
| 7 | ~~ASR / radio / telemetry backfills~~ | ✅ **Done (v8), corrected (v16)** — all run with real data (Section 4): 12,111 RC msgs, **673** weather (was 297, and those were keyed off publication time), 198 radio clips (192 transcribed + diarized), 105,768 lap rows / 182 sessions. **v17: the links themselves were wrong** — see Section 4A. |

### Post-launch deferrals (not bugs)

- ~~Plotly charts · D3 heatmaps · Mapbox · shadcn/ui · Web Push · TanStack~~ — ✅ **all built (v8)**, see Section 7. (Mapbox done as **MapLibre** — no token.)
- Still deferred: Mapbox per-corner telemetry overlay (needs real per-incident track coordinates) · F2/F3/Formula-E expansion.

---

## SECTION 11 — Data Status

| Season | Records | Status |
|---|---|---|
| 2026 | 178 | ✅ |
| 2025 | 386 | ✅ |
| 2024 | 367 | ✅ |
| 2023 | 298 | ✅ |
| 2022 | 125 | ✅ |
| 2021 | 81 | ✅ |
| 2020 | 79 | ✅ |
| 2019 | 92 | ✅ |
| **Total** | **1,606** | ✅ All seasons 2019–2026 |

Drivers: **42** · Teams: 17 active (43 rows) · Events: **158** · Sessions: **380** · Incidents extracted: 1,606 · Guidelines articles live: 45 (33 curated FIA + 12 empirical) · Precedent links: **27,133**

**Classification (v12, see Section 2C):** incidents with `infraction_category`: **1,181 / 1,606 (73.5%)** across **24** categories, up from 357 / 10 · incidents with `penalty_type`: **1,039**, across 11 values (NFA 396 · 5s 135 · FINE 118 · PIT 80 · 10s 70 · WARN 69 · REP 65 · GRID 55 · DSQ 31 · DT 10 · SG 10). **The remaining 425 are not all administrative — v12–v16 said they were and were wrong (corrected v17).** Of the 345 that are embedded and pass `decisions.is_precedent`, **249 record a real penalty** and only 96 decide neither an offence nor a penalty. They are excluded at query time by *decides something*, never deleted. See row 1c.

**Multimodal data (Phase 3 backfill, v8; corrected and extended in v16):** incidents with `session_key`: **1,027** (1,027 / 1,229 post-2023, 0 dangling, 0 cross-event) across a **380-row `sessions` table**, 182 of those sessions carrying telemetry · race-control messages: **16,260 across 268 sessions** (**3,293 incident links** across 712 incidents and 2,798 distinct messages, 427 shared between rulings, v17 — was 861 across 181 sessions) · incidents with weather: **673** (mean 21.9s from the incident) · incidents with a real `incident_time`: **642** · team-radio clips: 198 (192 transcribed + sentiment/urgency, 192 diarized) · FastF1 lap-feature rows: 105,768 / 182 sessions, of which **104,327 carry a real lap start time** (179 of 182 sessions varying — every row held its session's scheduled start until v17, see row 1o) and **58,556 carry a lap position** (new in v17, migration `0020`) · incidents with `position_change`: **208** · incidents with `video_refs`: **784**.

**Extraction fidelity (v16, measured against the documents rather than against coverage):** session type wrong on **1 / 1,144** documents that state one, down from 486 · `contact` read from the Fact section on 1,142 rows, 689 corrected · drivers named on **1,313 / 1,606** incidents, every extracted name resolving to a known driver · the 293 incidents with no driver are protests, team technical infringements, panel substitutions and promoter decisions, which name none.

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
| `test_steward_parser.py` (panel signature blocks) | ✅ |
| `test_steward_variance.py` (by-panel variance endpoint) | ✅ |
| `test_race_control_linker.py` (window, car agreement, deleted-lap offence match) | ✅ |
| `test_precedent_filter.py` (a ruling with a penalty but no category is precedent) | ✅ |
| `test_predictor_label_space.py` (a missing penalty class does not rename the others) | ✅ |
| `test_text_cleaner.py` (an ordinary word is not a cited article) | ✅ |
| `test_weather_linker.py` (weather needs a moment to be about) | ✅ |
| `test_published_at.py` (the FIA's "CET" is Paris local, and the day comes first) | ✅ |
| **Total collected** | **606 ✅** (**v18: +48** — every word that put a fragment in the column asserted to cite nothing, a bare `Articles` with no number citing nothing, enumerated citations recording every article and not just the first, a chapter written with and without its comma being one citation, a citation wrapped across a line break collapsing, and a paragraph letter being the same article however the dot falls while `B1.6.2b.i` keeps its own; v11: +42 — recovered ruling types, outcome fixes, penalty-type normalisation, and a completeness guard asserting every parser label has a category mapping; v12: +14 — route-shadowing invariant, driver-obligation/practice-start/safety-car regressions; **v16: +100** — the `Session` field beating "Race Director", `sprint_qualifying` never collapsing into `sprint`, a document with no stated session inventing none, contact read only from the Fact section with negations and "near collision" handled, the incident time distinguished from the publication time and impossible clock readings rejected, and both table layouts read while a numbered list without a table header is not; **v17: +37** — a race control message about another car not attaching itself to a nearby ruling, the measured asymmetric window, a turn disagreement rejecting, a deleted lap time belonging only to the offence it names, and an untimed ruling requiring the offence to agree unless race control has no word for it; **+26 more in v17** — the evidence clause read for vision evidence only and a named camera not double-counting as generic video, the precedent filter keeping a ruling that carries a penalty but no category and both retrieval legs applying the same one, and a penalty class missing from the training split keeping every other class under its own name) |

**v18's 48** break down as 21 on the citations (above), **11 on the weather linker** — which had no test file at all — and **16 on the publication date**. The weather ones fix the rule that let the 11 unanchored rows exist: no anchor means no weather, a reading beyond the gap ceiling is not this incident's weather, and the distance to the reading is reported alongside the value so a consumer can judge it. The date ones pin the two raw shapes, the day-before-month reading, the Paris-local timezone in both summer and winter, and the two ways a bad string must fail — text with no full date returns None, and an impossible date like `31.02` returns None rather than raising.

---

## SECTION 13 — CI / Quality Gates

**All re-run locally in v10 with true exit codes checked** — not inherited from a previous claim. The three Python gates were re-run again in v17.

| Check | Status |
|---|---|
| `ruff check packages/ apps/ scripts/ tests/` | ✅ All checks passed |
| `mypy --explicit-package-bases packages/ apps/ scripts/` | ✅ clean — **129 source files** (re-run v18) |
| `pytest tests/` | ✅ **606 passing** (re-run v18, 2.05s) |
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

*Report v16 — 18 August 2026 — Audited the extraction layer by measuring every stored field against what the document actually says, rather than against whether it was populated. Populated-but-wrong is what a coverage table hides, and the largest defect in the project was exactly that: **session type was wrong on 42.5% of the corpus** — practically every practice, qualifying and sprint ruling filed as a race, because the parser scanned the whole document and met "having received a report from the Race Director" before reaching the `Session` field. 486 disagreements → 1. The same whole-document-scan bug turned up four more times: `contact` restating the category label instead of reading the Fact section (689 rows corrected), the incident time never read at all so weather was being matched against the FIA's publication timestamp hours after the flag (673 rows now within a 10-minute ceiling, mean 21.9s), and **164 rulings that name their drivers in a table stored against nobody** (1,127 driver entries recovered, 0 unresolved, driverless incidents 457 → 293). Underneath all of it, `incidents.session_key` was an integer pointing into an **empty `sessions` table** — 380 sessions loaded, incidents relinked on the event and session each document states, catching 23 filed against the previous year's Canadian GP, now a real FK with 0 dangling and 0 cross-event keys. Migrations `0016` and `0017`. Three further suspected defects were checked and closed as **not** defects: `lap` and `corner` are NULL exactly where the document is silent, and `position_change` is not derivable from anything held — left empty rather than invented. Tests 395 → 495; ruff, mypy (117 files) and pytest all green. **One item now needs your decision:** the penalty predictor was trained on the pre-v16 values of `session_type` and `contact`, so a retrain is warranted — it costs money, so it waits on you.*

*Report v12 — 14 August 2026 — Acted on your two calls: fix the conflicting rows, and fix the `/consistency` 500 now rather than after the Fly migration. **The 500 was a route-declaration-order bug, not a hosting one** — `/incidents/{incident_id}` was declared above the literal `/incidents/consistency`, so Starlette captured the literal path as `incident_id="consistency"`; this corrects the v11 entry, which blamed the Vercel serverless layer on the strength of a plain-text error body that is in fact Starlette's own default. Every route on the app was then scanned for the same defect (0 others) and the ordering invariant is now a test. Adjudicating the 4 conflicting rows against the source documents found the v11 list was partly wrong — one row was the new code erring, not the database — and surfaced **three further pattern bugs, two of them introduced by v11**: a bare "drivers' briefing" match stealing unrelated rulings, "Practice Start **Area**" (a place) read as a practice start and pulling 6 pit-lane rulings out of their category, and Article 55.5 "near collision behind the safety car" matching nothing. **11 corrections applied, 0 rows deleted**; classified 1,181 / 1,606 across 24 categories. Every one of the 26 classifications lost to the tightened patterns was inspected: 8 were real rulings (recovered) and 16 are administrative documents that should never have carried a category — 0 non-administrative losses. Tests 309 → 323. Flagged for your call: `7caff04e`, where the stop-and-go is **suspended** and a reprimand also issued, so `SG` records the headline penalty rather than the one served.*

*Report v11 — 12 August 2026 — Closed v10's biggest open defect at its source. The v10 scan blamed a narrow category vocabulary; reading the extractor found **four** independent bugs, two of which would have defeated a vocabulary-only fix: parser labels that had no entry in the category map at all (the key read `start procedure`, the label was `starting procedure`), missing patterns for parc fermé / deleted lap times / SC2-SC1 / 107% / forcing off track / Race Director instructions, a `_layer1` that classified on the document body while ignoring the title the offence is usually named in, and a `penalty_type` schema with no value for warnings, fines or stop-go. **Classified incidents 357 → 1,180 (22.2% → 73.5%), categories 11 → 24, `penalty_type` recovered for 199 more rulings, 0 rows deleted, 0 stored values overwritten.** Migration `0010` widens `ck_incidents_penalty_type`. Writing tests against verbatim FIA text exposed two further latent bugs, both pre-existing: the fine regex expected `5,000 €` when the FIA writes `€5,000` (so no fine had ever matched), and substring matching meant `"5 second"` matched inside `"15 second penalty"` — audited, 0 stored rows affected. Corrected the downstream layers that still assumed 7 penalty values: three frontend maps, the driver-stats query that counted a warning as a sanction, and the consistency heat-map whose buckets no longer summed to 100% (now verified across all 108 rows). Tests 267 → 309, including a guard asserting every parser label has a category mapping. Left untouched and listed in Section 2C: 4 rows where the new code disagrees with a stored value. Remaining blockers unchanged and all 💳.*

*Report v10 — 12 August 2026 — Audited Section 2 by execution rather than inspection: every CI gate run with its true exit code checked, all 158 ORM columns diffed against live Neon. Five real defects found in a section that was fully marked ✅. Fixed: the `security-audit` job (red on both halves — npm `postcss`/`sharp`, Python `msgpack`), the silently-dead `/v1/precedents/{id}/similar` endpoint (materialised 32,120 precedent links from the real embeddings already in Neon), `steward_panels.created_at` missing from the DB (migration `0009`, applied), 22 naive-vs-`timestamptz` datetime columns, and a pyannote-4 `use_auth_token` runtime bug. Wrote `prefect.yaml` — the 3 flows had never been registered, so nothing had ever been scheduled. IP India trademark search completed (clear) — knock-out search now done in all four jurisdictions. **Then ran a full deep scan of all 1,249 unclassified incidents** (not a sample) to settle whether they were junk or extraction failures: **864 of them (69.2%) are genuine stewards' rulings the extractor failed to categorise**, validated against the FIA document signature with the 357 classified incidents as a 94%-matching control. Filtering them — the intuitive fix — would have destroyed 2.4× more real incidents than the corpus currently has classified. The real defect is the extractor's category vocabulary; recommended fix is taxonomy extension + re-extraction (Section 2B). Remaining blockers unchanged and all 💳: Fly billing, Clerk/Stripe live keys, domain + email, Anthropic key, lawyer clearance.*

*Report v9 — 12 August 2026 — Committed the v8 working tree (`1e009ed`, 34 files). Wired and live-verified Sentry (org `racejudge-if`). Introduced the 💳 symbol so card-gated items read as parked rather than outstanding. Established that `racejudge.com` is investor-held and recommended `racejudge.app` instead. Recorded the completed EUIPO/USPTO/UK trademark knock-out searches (exact mark clear) and opened the **IP India** search as the one remaining pre-work item needing no card. Remaining blockers unchanged and all now 💳: Fly billing, Clerk/Stripe live keys, domain + email, Anthropic key, lawyer clearance.*

*Report v8 — 21 June 2026 — Ran the full Phase-3 multimodal backfill with real data (race-control, weather, radio ASR + diarization, FastF1 telemetry — 105,768 lap rows / 182 sessions), fixed the ORM↔DB type drift that was silently zeroing those writes, built the deferred frontend libraries (Plotly · D3 · TanStack · shadcn · MapLibre · Web Push, `next build` green), configured Stripe billing in test mode, and ran two honest penalty-model retrains confirming the ship gate is structurally (not card-) blocked. Remaining blockers are unchanged: Fly billing (deploy) + Clerk/Stripe **live** keys + Anthropic key (all card-gated, parked at the user's request).*

*v7 — 16 June 2026 — Completed the retrieval ML pipeline (Pre-Work → Phase 4): 359-pair AI-adjudicated annotation campaign → LoRA fine-tune of BGE-M3 (held-out triplet acc 0.844→0.969) → all 1,606 incidents embedded → precedent search live. CI all-green.*
