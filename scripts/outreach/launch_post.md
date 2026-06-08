# RACEJUDGE Launch Post — Draft

## Twitter / X (primary thread)

**Tweet 1 (hook)**
Every time F1 stewards hand down a penalty, fans argue about consistency.
They're usually right to.

I built RACEJUDGE to find out how inconsistent stewards actually are — and now it's live.

[link] 🧵

---

**Tweet 2 (what it is)**
RACEJUDGE indexes every FIA stewards' decision going back to 2010.

Search by incident type, driver, season, or circuit.
See the penalty. See the precedent. See the pattern.

---

**Tweet 3 (the consistency angle)**
The steward variance page ranks infraction categories by Shannon entropy —
how spread out the penalty outcomes are for the same type of incident.

Spoiler: "unsafe pit lane entry" is all over the place.

---

**Tweet 4 (the prediction feature)**
You can also predict what penalty a hypothetical incident would get —
based on XGBoost trained on ~3,000 historical decisions.

P(penalty_type | infraction, driver, circuit, session, repeat_offender)

---

**Tweet 5 (right-of-review)**
And if you think a penalty was wrong, the Right-of-Review Builder
drafts a full Art. 14.1.1 ISC request document for you:

- Fetches the original decision
- Finds similar incidents where a lighter penalty was given
- RAG-generates the legal argument
- Formats the document ready to submit

---

**Tweet 6 (the API)**
Everything has an API: decisions, precedent search, prediction, variance analysis.

Free tier: 100 req/day
Pro: 10k/day
MCP server for AI agent access

---

**Tweet 7 (CTA)**
racejudge.com

If you work in motorsport, cover it, or just get into arguments about it —
I'd love to know what you'd add.

---

## LinkedIn (longer form)

**Title:** I built a search engine for F1 stewards' decisions

For the past six months I've been scraping, parsing, and analysing every FIA stewards' decision document going back to 2010 — roughly 3,000 PDF files, 300+ race weekends.

The result is RACEJUDGE: a precedent engine for F1 sporting decisions.

**What it does:**

**Search** — semantic search across 3,000 decisions using BGE-M3 embeddings and pgvector HNSW indexing. Ask "unsafe release in pit lane" and get every incident that matches, ranked by similarity.

**Penalty prediction** — an XGBoost model trained on historical decisions predicts the most likely penalty given infraction type, driver, circuit, session type, and repeat-offender status.

**Consistency analysis** — Shannon entropy over penalty distributions shows which infraction categories are applied inconsistently. Turns out stewards agree on some things (DSQ for technical violations) and wildly disagree on others.

**Right-of-Review Builder** — generates a complete Art. 14.1.1 ISC review request document, including precedent analysis and RAG-generated legal argument, for a given incident.

**For developers** — full REST API with rate limiting and an MCP server for AI agent access.

Tech stack: Next.js 16, FastAPI, PostgreSQL + pgvector, XGBoost, Anthropic claude-haiku for RAG, deployed on Fly.io.

The data pipeline runs on Playwright (JS-rendered FIA pages), pdfplumber + Tesseract OCR for the PDFs, and Prefect for orchestration.

Everything is built with the idea that sporting decisions should be transparent, searchable, and comparable — not buried in PDF archives.

Try it at racejudge.com. Feedback welcome.

---

## Reddit r/formula1 post

**Title:** I built a search engine + consistency analyser for F1 stewards' decisions — racejudge.com

**Body:**

Long-time lurker, first time poster with a project.

I got frustrated with the recurring "stewards are inconsistent" arguments where nobody had actual data, so I spent the last six months building RACEJUDGE.

**What it is:**
- Every FIA stewards' decision from 2010–2025, parsed from the PDF archives
- Semantic search so you can find all "unsafe release" incidents or "track limits gained advantage" cases
- Penalty prediction (what would the stewards likely do for X incident?)
- Consistency analysis — Shannon entropy over penalty distributions per infraction type
- Right-of-Review document generator (for the very dedicated)

The consistency page is the main thing I want feedback on. Some categories are genuinely all over the place.

**What I found:**
- The same track limits infraction gets NFA, a 5s penalty, or a drive-through depending on... something
- DSQ for technical violations is by far the most consistent category (makes sense — it's usually pass/fail)
- The "impeding" category has the highest entropy of anything with >20 incidents

racejudge.com — free to use. There's also an API if you want to build on the data.

Happy to answer questions about how it works or what I found in the data.
