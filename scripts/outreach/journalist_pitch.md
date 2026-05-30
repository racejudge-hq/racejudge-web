# RACEJUDGE — Journalist Design Partner Outreach

Action 3 of the 72-hour pre-work plan.
Target: 5 F1 journalists as design partners before public launch.

---

## Contact List — Exact Names, Emails, and Handles

### 1. The Race

| Field | Detail |
|---|---|
| **Primary contact** | Scott Mitchell-Malm |
| **Role** | F1 reporter — covers stewards, regulations, technical directives |
| **X/Twitter** | @ScottMitchell_Ml |
| **Email** | `editorial@therace.com` (DM on X first — higher open rate) |
| **Why him** | He wrote the stewarding deep-dives that had to rely on hand-disclosed FIA figures; would immediately understand RACEJUDGE's value |
| **Tone** | Data-forward. Responds well to "here's what the numbers actually say" |

| Field | Detail |
|---|---|
| **Secondary contact** | Mark Hughes |
| **Role** | F1 technical analyst |
| **X/Twitter** | @HughesF1 |
| **Email** | `editorial@therace.com` |

---

### 2. Autosport

| Field | Detail |
|---|---|
| **Primary contact** | Lawrence Barretto |
| **Role** | F1 Editor |
| **X/Twitter** | @LawroBarretto |
| **Email** | `tips@autosport.com` |
| **Why him** | Runs editorial direction; strong on driver/team stories — use GPDA angle |

| Field | Detail |
|---|---|
| **Secondary contact** | Edd Straw |
| **Role** | Senior F1 journalist |
| **X/Twitter** | @EddStraw |
| **Email** | `tips@autosport.com` |
| **Why him** | Covers regulation and steward decisions closely |

---

### 3. RaceFans

| Field | Detail |
|---|---|
| **Primary contact** | Keith Collantine |
| **Role** | Founder & editor |
| **X/Twitter** | @KeithCollantine |
| **Email** | `keith@racefans.net` (publicly listed on site — direct contact) |
| **Why him** | He ran the reader poll showing 84% of fans found the Sainz/Lawson Zandvoort penalty too harsh. Perfect hook. He loves data and is accessible to direct email. |

---

### 4. RacingNews365

| Field | Detail |
|---|---|
| **Primary contact** | Editorial team |
| **X/Twitter** | @RacingNews365 |
| **Email** | `info@racingnews365.com` |
| **Why them** | High-volume F1 news; quick to test new tools; good for broad launch coverage |

---

### 5. PlanetF1

| Field | Detail |
|---|---|
| **Primary contact** | Sam Cooper |
| **Role** | F1 correspondent |
| **X/Twitter** | @SamCooper_F1 |
| **Email** | `editorial@planetf1.com` |
| **Why him** | Large fan-facing readership; strong social amplification on controversy stories |

---

## Exact Send Instructions (step by step)

### When to send

- **Best**: Wednesday or Thursday of a European GP week (British, Spanish, Belgian, Monaco, Italian)
- **Why**: Journalists are already thinking about stewarding — especially after qualifying controversies
- **Avoid**: Monday–Tuesday post-race (inbox chaos), Friday (too busy)
- **Right now**: Send this week — Canadian GP is live. Thursday is optimal.

### Step-by-step process

1. **Send X/Twitter DM first** (higher open rate than cold email):
   Copy-paste the DM template below. Wait 3 days.

2. **If no DM reply in 3 days**: Send Email Template A or B (pick based on outlet above)

3. **Follow up once** after 7 days using the follow-up template

4. **Fill in the tracker table** at the bottom with dates

---

## DM Template (send on X first)

> Hi [Name], I'm building RACEJUDGE — every FIA stewards' decision since 2018, structured and searchable. 1,039 decisions parsed already. Penalty predictor, precedent search, live race integration. Looking for 3–5 journalist design partners before public launch. Would you want early access + advance data export? [your-email@gmail.com]

---

## Email Template A — Data angle (The Race, RaceFans)

**Subject:** A tool that answers "Is this penalty consistent?" — design partner invite

Hi [Name],

I'm building RACEJUDGE — a searchable, structured database of every FIA Stewards' Decision from 2018 to today, cross-linked to race control messages and telemetry.

I have 1,039 decisions parsed already (2021–2025, all sessions). Here's what it does:

**Precedent search** — natural-language queries like "Show me every 10-second penalty for forcing a car off track on corner exit since 2022" — results in under a second, with the full original PDF linked.

**Penalty predictor** — given an incident description + telemetry window, returns a probability distribution over outcomes (No Further Action through DSQ) with cited guideline articles from the FIA's June 2025 Penalty Guidelines.

**Consistency analysis** — statistical breakdown of penalty severity by infraction type, season, steward panel, and circuit. It flags decisions that are statistically anomalous vs. precedent.

**Live mode** — during a race, when OpenF1 emits "UNDER INVESTIGATION", it auto-pushes the top-5 most similar historical incidents within ~5 seconds.

The tool is not public yet. I'm looking for 3 journalists as design partners — people who would give me honest feedback on what would actually be useful at the trackside.

In exchange:

- Private preview access before launch
- The full 2024–25 structured incident dataset as CSV (every incident, penalty, driver, circuit, lap number)
- First notification at launch

No commitment required. Are you open to a 30-minute call or async email exchange?

[Your name]
[Your email]

---

## Email Template B — GPDA/transparency angle (Autosport, PlanetF1, RacingNews365)

**Subject:** Building the transparency tool the GPDA has been demanding

Hi [Name],

George Russell and Carlos Sainz have publicly demanded stewarding consistency improvements. The FIA published its Penalty Guidelines for the first time in June 2025. The Zandvoort Right of Review succeeded partly because no one had an easy way to cite precedent at decision time.

I'm building RACEJUDGE: a structured, searchable database of every FIA Stewards' Decision from 2018 to today.

Not a PDF viewer — a precedent engine. Every decision is parsed (driver, infraction type, outcome, lap, session), cross-linked to race control and telemetry, and indexed for semantic search.

The core question it answers in real-time: "Is this penalty consistent with what happened at [circuit] in [year] when [driver] did the same thing?"

No equivalent public tool exists. The FIA's internal system is proprietary. RACEJUDGE uses only public FIA PDFs and OpenF1 data.

I'm looking for 2–3 journalists as design partners — honest feedback before launch. In return: early access, advance data exports, credit in the launch post.

Are you open to 20 minutes in the next few weeks?

[Your name]

---

## Follow-up Template (send 7 days after original, once only)

**Subject:** Re: RACEJUDGE — quick follow-up

Hi [Name],

Following up from last week — race weekends fill up fast, I understand.

Short version: I've built a tool that makes every F1 stewards' decision since 2018 searchable and comparable. 1,039 decisions parsed. Penalty predictor, precedent search, live race integration.

Happy to send a 2-minute screen recording if easier than a call.

[Your name]

---

## Data you can reference in pitch emails

Run this before sending to get the latest numbers:

```bash
source .venv/bin/activate
python scripts/eda_decisions.py
```

Hardcoded talking points (from current dataset):

- **1,039 decisions** parsed across 2021–2025 (more being added)
- **Most common infractions**: track limits, causing a collision, unsafe release, impeding
- **Penalty severity varies significantly year-on-year** — no public analysis of this exists
- **2024 had 40+ collision decisions** — the most in the dataset
- The FIA Penalty Guidelines published June 2025 are now the backbone taxonomy — RACEJUDGE is the first tool to cross-reference all historical decisions against them

---

## Outreach Tracker

Fill this in as you send:

| Contact | Outlet | DM sent | Email sent | Replied | Notes |
|---|---|---|---|---|---|
| Scott Mitchell-Malm | The Race | | | | |
| Lawrence Barretto | Autosport | | | | |
| Keith Collantine | RaceFans | | | | |
| RacingNews365 editorial | RacingNews365 | | | | |
| Sam Cooper | PlanetF1 | | | | |
