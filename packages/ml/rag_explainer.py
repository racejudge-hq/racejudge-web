"""
RAG reasoning explainer — Phase 5.

Generates a natural-language explanation for a predicted penalty outcome,
citing top-3 precedents and the relevant FIA article text.

Uses Anthropic API (claude-haiku-4-5) with a structured prompt.
Falls back to a template string when API key is absent.

Usage:
    from packages.ml.rag_explainer import explain_prediction
    explanation = await explain_prediction(
        incident_description="VER overtook HAM outside track limits at T1",
        predicted_class="5s",
        precedents=[...],  # list of PrecedentResult dicts
        article_text="Art 38.1 — A driver must make every reasonable effort..."
    )
"""

from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
DEFAULT_MODEL     = "claude-haiku-4-5-20251001"
MAX_TOKENS        = 400


def _build_prompt(
    incident_description: str,
    predicted_class: str,
    confidence: float,
    precedents: list[dict[str, Any]],
    article_text: str | None,
) -> str:
    prec_block = ""
    for i, p in enumerate(precedents[:3], 1):
        drivers = ", ".join(d.get("code", "") for d in (p.get("drivers") or []))
        prec_block += (
            f"\nPrecedent {i}: {p.get('title', 'Unknown')} "
            f"({p.get('season', '')}) — {p.get('penalty_type', 'N/A')}\n"
            f"  Drivers: {drivers or 'N/A'}\n"
            f"  Reasoning: {(p.get('reasoning_snippet') or '')[:200]}\n"
        )

    article_block = f"\nApplicable article:\n{article_text}\n" if article_text else ""

    return f"""You are an F1 stewards' assistant. Explain in 3-4 sentences why the predicted penalty for this incident is {predicted_class} ({confidence:.0%} confidence).

Incident: {incident_description}
{article_block}
Top precedents:{prec_block}

Write a concise explanation that:
1. States why {predicted_class} is the most likely outcome
2. References 1-2 of the most relevant precedents by name
3. Notes any factors that could push toward a lighter or heavier penalty

Explanation:"""


def _template_fallback(
    incident_description: str,
    predicted_class: str,
    confidence: float,
    precedents: list[dict[str, Any]],
) -> str:
    prec_names = [p.get("title", "Unknown") for p in precedents[:2]]
    prec_str   = " and ".join(f'"{n}"' for n in prec_names) if prec_names else "historical decisions"

    severity = {
        "NFA":  "minor with insufficient evidence for a penalty",
        "REP":  "a minor infraction warranting a formal reprimand",
        "5s":   "a moderately serious infraction",
        "10s":  "a significant infraction with clear responsibility",
        "DT":   "a serious infraction requiring a drive-through penalty",
        "GRID": "a serious infraction warranting a grid penalty",
        "DSQ":  "an extremely serious infraction warranting disqualification",
    }.get(predicted_class, "an infraction")

    return (
        f"Based on {confidence:.0%} model confidence, the incident appears to be {severity}. "
        f"This aligns with precedents such as {prec_str}, where stewards applied similar penalties "
        f"under comparable circumstances. The outcome could be influenced by factors such as "
        f"track position impact, whether the move was avoidable, and the driver's penalty history."
    )


async def explain_prediction(
    incident_description: str,
    predicted_class: str,
    confidence: float,
    precedents: list[dict[str, Any]],
    article_text: str | None = None,
) -> str:
    """
    Generate a RAG-based explanation for a prediction.

    Returns explanation text. Uses Anthropic API if key is set,
    otherwise falls back to a template.
    """
    if not ANTHROPIC_API_KEY:
        log.debug("ANTHROPIC_API_KEY not set — using template fallback")
        return _template_fallback(incident_description, predicted_class, confidence, precedents)

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        prompt = _build_prompt(
            incident_description=incident_description,
            predicted_class=predicted_class,
            confidence=confidence,
            precedents=precedents,
            article_text=article_text,
        )

        message = client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        return getattr(message.content[0], "text", "").strip()

    except ImportError:
        log.warning("anthropic SDK not installed — using template fallback")
        return _template_fallback(incident_description, predicted_class, confidence, precedents)
    except Exception as exc:
        log.error("RAG explainer API call failed: %s", exc)
        return _template_fallback(incident_description, predicted_class, confidence, precedents)
