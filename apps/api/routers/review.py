"""
Right-of-Review Builder router — Phase 7 (Team tier).

POST /v1/review/generate

Given an incident ID, driver code, and optional new evidence, generates a
structured FIA Right-of-Review request document.

The document:
  1. States the original decision being contested
  2. Asserts the new significant element of evidence (Art. 14.1.1 ISC)
  3. Provides precedent analysis (similar incidents with more lenient outcomes)
  4. Drafts the formal argument using RAG (Anthropic claude-haiku)

The endpoint is available to all tiers pre-Stripe-launch; once billing is
live it will be gated to Team tier via the rate-limit middleware's tier state.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)
router = APIRouter(tags=["review"])

_REVIEW_TEMPLATE = """\
RIGHT OF REVIEW REQUEST
FIA International Sporting Code — Article 14.1.1

Submitted by: {team_name}
Driver:       {driver_code}
Decision ref: {decision_title} ({published_at})
Generated:    {generated_at}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SECTION 1 — INCIDENT UNDER REVIEW
{incident_summary}

Original penalty: {penalty_type}
Incident category: {infraction_category}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SECTION 2 — GROUNDS FOR REVIEW
New significant element of evidence not available to the Stewards at the
time of the original decision:

{new_evidence}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SECTION 3 — PRECEDENT ANALYSIS
The following comparable decisions demonstrate inconsistent application
of the relevant sporting regulations:

{precedent_analysis}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SECTION 4 — LEGAL ARGUMENT
{legal_argument}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Additional notes:
{notes}
"""

_RAG_SYSTEM = (
    "You are a specialist FIA sporting regulations lawyer drafting a Right of Review "
    "request under Article 14.1.1 of the FIA International Sporting Code. "
    "Write formally and precisely. Reference specific articles where relevant. "
    "Do not fabricate regulations or precedents — only use what is provided."
)


# ---------------------------------------------------------------------------
# Request / response
# ---------------------------------------------------------------------------

class ReviewRequest(BaseModel):
    incident_id:  str = Field(..., description="UUID of the incident being contested")
    driver_code:  str = Field(..., description="3-letter FIA driver code (e.g. VER)")
    team_name:    str = Field(..., description="Constructors' team name")
    new_evidence: str = Field(
        ...,
        min_length=20,
        description="New significant element of evidence not available to the stewards",
    )
    notes: str = Field(default="", description="Additional notes to include in the document")


class ReviewResponse(BaseModel):
    incident_id:    str
    driver_code:    str
    document:       str = Field(..., description="Full formatted Right-of-Review document")
    precedents_used: int
    rag_used:       bool
    generated_at:   str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _fetch_incident(incident_id: str) -> dict[str, Any] | None:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        return None
    try:
        from sqlalchemy import text

        from packages.db.database import _get_session_factory

        factory = _get_session_factory()
        if factory is None:
            return None
        async with factory() as session:
            row = (await session.execute(
                text("""
                    SELECT i.incident_id, i.drivers, i.lap, i.infraction_category,
                           i.penalty_type, i.penalty_points, i.reasoning_text,
                           i.article_cited, d.title, d.published_at, d.season
                    FROM incidents i
                    JOIN decisions d ON i.doc_id = d.doc_id
                    WHERE i.incident_id = :iid
                """),
                {"iid": incident_id},
            )).fetchone()

        if row is None:
            return None
        return {
            "incident_id":        str(row[0]),
            "drivers":            row[1] or [],
            "lap":                row[2],
            "infraction_category": row[3],
            "penalty_type":       row[4],
            "penalty_points":     row[5],
            "reasoning_text":     row[6],
            "article_cited":      row[7] or [],
            "decision_title":     row[8],
            "published_at":       str(row[9]) if row[9] else "Unknown date",
            "season":             row[10],
        }
    except Exception as exc:
        log.error("fetch_incident error: %s", exc)
        return None


async def _fetch_lenient_precedents(incident: dict[str, Any], limit: int = 4) -> list[dict[str, Any]]:
    """Find similar incidents where a MORE LENIENT penalty was given."""
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        return []

    penalty_order = {"NFA": 0, "REP": 1, "5s": 2, "10s": 3, "DT": 4, "GRID": 5, "DSQ": 6}
    current_rank  = penalty_order.get(incident.get("penalty_type", "NFA"), 0)

    if current_rank == 0:
        return []

    more_lenient = [k for k, v in penalty_order.items() if v < current_rank]
    if not more_lenient:
        return []

    try:
        from sqlalchemy import text

        from packages.db.database import _get_session_factory

        factory = _get_session_factory()
        if factory is None:
            return []

        category = incident.get("infraction_category") or ""

        async with factory() as session:
            rows = (await session.execute(
                text("""
                    SELECT i.incident_id, i.infraction_category, i.penalty_type,
                           i.penalty_points, left(i.reasoning_text, 250) AS summary,
                           d.season, d.title
                    FROM incidents i
                    JOIN decisions d ON i.doc_id = d.doc_id
                    WHERE i.penalty_type = ANY(:lenient)
                      AND i.infraction_category = :cat
                      AND i.incident_id != :iid
                    ORDER BY d.season DESC
                    LIMIT :lim
                """),
                {
                    "lenient": more_lenient,
                    "cat":     category,
                    "iid":     incident["incident_id"],
                    "lim":     limit,
                },
            )).fetchall()

        return [
            {
                "incident_id":        str(r[0]),
                "infraction_category": r[1],
                "penalty_type":       r[2],
                "penalty_points":     r[3],
                "summary":            r[4],
                "season":             r[5],
                "decision_title":     r[6],
            }
            for r in rows
        ]
    except Exception as exc:
        log.warning("Precedent fetch failed: %s", exc)
        return []


def _format_precedent_analysis(precedents: list[dict[str, Any]], current_penalty: str) -> str:
    if not precedents:
        return (
            "No directly comparable precedents with more lenient outcomes were found "
            "in the RACEJUDGE dataset. The Stewards are invited to consider whether "
            "the current decision is consistent with the general principles of "
            "proportionality under the FIA Penalty Guidelines 2025."
        )
    lines = []
    for i, p in enumerate(precedents, 1):
        lines.append(
            f"{i}. {p['decision_title']} (Season {p['season']})\n"
            f"   Infraction: {p['infraction_category']}\n"
            f"   Outcome: {p['penalty_type']} (vs. {current_penalty} in the contested decision)\n"
            f"   Summary: {p['summary']}"
        )
    return "\n\n".join(lines)


async def _rag_legal_argument(
    incident: dict[str, Any],
    new_evidence: str,
    precedents: list[dict[str, Any]],
) -> tuple[str, bool]:
    """Generate the legal argument section via Anthropic RAG. Falls back to template."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return _template_argument(incident, new_evidence, precedents), False

    prec_text = "\n".join(
        f"- {p['decision_title']} ({p['season']}): {p['penalty_type']} for {p['infraction_category']}"
        for p in precedents
    ) or "No comparable precedents available."

    prompt = (
        f"Incident: {incident.get('reasoning_text', '')[:600]}\n"
        f"Original penalty: {incident.get('penalty_type')}\n"
        f"Articles cited: {', '.join(incident.get('article_cited') or [])}\n\n"
        f"New evidence: {new_evidence}\n\n"
        f"Comparable precedents with more lenient outcomes:\n{prec_text}\n\n"
        "Draft the legal argument section (Section 4) of the Right of Review request. "
        "Argue that: (a) the new evidence is significant and was unavailable to the Stewards; "
        "(b) the penalty applied is inconsistent with the precedents listed; "
        "(c) on the correct application of the regulations a more lenient penalty is warranted. "
        "Be concise — 3–5 paragraphs."
    )

    try:
        import anthropic  # type: ignore[import]

        client = anthropic.AsyncAnthropic(api_key=api_key)
        msg = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            system=_RAG_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        return getattr(msg.content[0], "text", "").strip(), True
    except Exception as exc:
        log.warning("RAG legal argument failed: %s", exc)
        return _template_argument(incident, new_evidence, precedents), False


def _template_argument(
    incident: dict[str, Any],
    new_evidence: str,
    precedents: list[dict[str, Any]],
) -> str:
    penalty = incident.get("penalty_type", "the imposed penalty")
    category = incident.get("infraction_category", "the infraction")
    n_prec = len(precedents)

    return (
        f"The {team_placeholder} submits that {new_evidence.strip()} constitutes a "
        f"new significant element of evidence within the meaning of Article 14.1.1 of "
        f"the FIA International Sporting Code, being evidence that was not available "
        f"to the Stewards at the time of the original decision.\n\n"
        f"The {penalty} penalty imposed for {category} is disproportionate in light of "
        f"the new evidence. On proper application of the FIA Penalty Guidelines 2025, "
        f"a lesser penalty or no further action should have been imposed.\n\n"
        + (
            f"This submission is further supported by {n_prec} comparable precedent(s) "
            f"identified in the RACEJUDGE dataset, as detailed in Section 3 above, in which "
            f"analogous incidents attracted materially more lenient penalties. The disparity "
            f"between those decisions and the contested decision cannot be justified on the facts."
            if n_prec > 0 else
            "The applicant reserves the right to submit further evidence in support of this "
            "request at the hearing."
        )
    )


team_placeholder = "{team_name}"


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/review/generate", response_model=ReviewResponse)
async def generate_review(body: ReviewRequest) -> dict[str, Any]:
    """
    Generate a Right-of-Review request document for a contested FIA decision.

    Fetches the incident, finds comparable lenient precedents, and drafts
    the legal argument section using RAG (falls back to template if no
    ANTHROPIC_API_KEY is set).
    """
    incident = await _fetch_incident(body.incident_id)
    if incident is None:
        db_set = bool(os.environ.get("DATABASE_URL"))
        if not db_set:
            raise HTTPException(
                status_code=503,
                detail="DATABASE_URL is not set. Connect a Postgres database to use this feature.",
            )
        raise HTTPException(status_code=404, detail=f"Incident {body.incident_id!r} not found.")

    precedents = await _fetch_lenient_precedents(incident)
    legal_arg, rag_used = await _rag_legal_argument(incident, body.new_evidence, precedents)

    drivers_str = ", ".join(
        d.get("code") or d.get("full_name", "Unknown")
        for d in (incident.get("drivers") or [])
    )
    incident_summary = (
        f"Driver(s): {drivers_str or body.driver_code}\n"
        f"Lap: {incident.get('lap') or 'N/A'}\n"
        f"Category: {incident.get('infraction_category') or 'N/A'}\n"
        f"Articles: {', '.join(incident.get('article_cited') or []) or 'N/A'}\n\n"
        f"{(incident.get('reasoning_text') or '')[:600]}"
    )

    document = _REVIEW_TEMPLATE.format(
        team_name=body.team_name,
        driver_code=body.driver_code.upper(),
        decision_title=incident["decision_title"],
        published_at=incident["published_at"],
        generated_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        incident_summary=incident_summary,
        penalty_type=incident.get("penalty_type") or "N/A",
        infraction_category=incident.get("infraction_category") or "N/A",
        new_evidence=body.new_evidence.strip(),
        precedent_analysis=_format_precedent_analysis(precedents, incident.get("penalty_type", "")),
        legal_argument=legal_arg.replace("{team_name}", body.team_name),
        notes=body.notes.strip() or "None.",
    )

    return {
        "incident_id":     body.incident_id,
        "driver_code":     body.driver_code.upper(),
        "document":        document,
        "precedents_used": len(precedents),
        "rag_used":        rag_used,
        "generated_at":    datetime.now(UTC).isoformat(),
    }
