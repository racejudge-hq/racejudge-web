"""
Penalty variance / steward consistency analysis — Phase 8.

GET /v1/incidents/variance
  Returns, per infraction category, how inconsistently stewards have applied
  penalties. High entropy = wildly varied outcomes for the same type of incident.

GET /v1/incidents/variance/{infraction_category}
  Deep-dive for a single category: per-season breakdown + penalty distribution.
"""

from __future__ import annotations

import logging
import math
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Query

log = logging.getLogger(__name__)
router = APIRouter(tags=["stewards"])

PENALTY_ORDER = {"NFA": 0, "REP": 1, "5s": 2, "10s": 3, "DT": 4, "GRID": 5, "DSQ": 6}


def _entropy(counts: dict[str, int]) -> float:
    """Shannon entropy over penalty distribution (0 = always same outcome)."""
    total = sum(counts.values())
    if total == 0:
        return 0.0
    return round(
        -sum((c / total) * math.log2(c / total) for c in counts.values() if c > 0),
        3,
    )


def _inconsistency_score(counts: dict[str, int]) -> float:
    """Normalise entropy to [0, 1] using max possible entropy for n categories."""
    n = len([c for c in counts.values() if c > 0])
    if n <= 1:
        return 0.0
    max_entropy = math.log2(n)
    return round(_entropy(counts) / max_entropy, 3) if max_entropy > 0 else 0.0


def _modal(counts: dict[str, int]) -> str:
    return max(counts, key=lambda k: counts[k]) if counts else "NFA"


def _mean_severity(counts: dict[str, int]) -> float:
    total = sum(counts.values())
    if total == 0:
        return 0.0
    weighted = sum(PENALTY_ORDER.get(k, 0) * v for k, v in counts.items())
    return round(weighted / total, 2)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _run_query(sql: str, params: dict[str, Any]) -> list[Any]:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        return []
    try:
        from sqlalchemy import text

        from packages.db.database import _get_session_factory

        factory = _get_session_factory()
        if factory is None:
            return []
        async with factory() as session:
            result = await session.execute(text(sql), params)
            return result.fetchall()
    except Exception as exc:
        log.error("variance query failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/incidents/variance")
async def list_variance(
    min_incidents: int = Query(5, ge=1, le=50, description="Minimum incidents per category to include"),
    season: int | None = Query(None, description="Restrict analysis to a single season"),
) -> dict[str, Any]:
    """
    Return penalty outcome entropy for every infraction category with
    enough data.  High inconsistency_score means stewards have imposed
    very different penalties for the same type of incident.
    """
    season_clause = "AND d.season = :season" if season else ""
    params: dict[str, Any] = {"min_cnt": min_incidents}
    if season:
        params["season"] = season

    rows = await _run_query(
        f"""
        SELECT
            i.infraction_category,
            i.penalty_type,
            COUNT(*) AS cnt,
            d.season
        FROM incidents i
        JOIN decisions d ON i.doc_id = d.doc_id
        WHERE i.infraction_category IS NOT NULL
          AND i.penalty_type      IS NOT NULL
          {season_clause}
        GROUP BY i.infraction_category, i.penalty_type, d.season
        ORDER BY i.infraction_category, d.season
        """,
        params,
    )

    # Aggregate by category
    by_cat: dict[str, dict[str, Any]] = {}
    for category, penalty, cnt, _season in rows:
        if category not in by_cat:
            by_cat[category] = {"counts": {}, "total": 0}
        by_cat[category]["counts"][penalty] = by_cat[category]["counts"].get(penalty, 0) + cnt
        by_cat[category]["total"] += cnt

    results = []
    for category, agg in sorted(by_cat.items(), key=lambda x: -x[1]["total"]):
        if agg["total"] < min_incidents:
            continue
        counts = agg["counts"]
        results.append(
            {
                "infraction_category": category,
                "total_incidents":     agg["total"],
                "penalty_distribution": counts,
                "modal_penalty":       _modal(counts),
                "mean_severity":       _mean_severity(counts),
                "entropy":             _entropy(counts),
                "inconsistency_score": _inconsistency_score(counts),
            }
        )

    # Sort by inconsistency (most inconsistent first)
    results.sort(key=lambda x: -x["inconsistency_score"])

    return {
        "season_filter": season,
        "min_incidents": min_incidents,
        "categories":    results,
    }


@router.get("/incidents/variance/{infraction_category}")
async def category_variance(
    infraction_category: str,
    seasons: int = Query(5, ge=1, le=10, description="Number of past seasons to include"),
) -> dict[str, Any]:
    """
    Deep-dive for a single infraction category.
    Returns season-by-season breakdown and penalty drift over time.
    """
    rows = await _run_query(
        """
        SELECT
            d.season,
            i.penalty_type,
            COUNT(*) AS cnt
        FROM incidents i
        JOIN decisions d ON i.doc_id = d.doc_id
        WHERE i.infraction_category ILIKE :cat
          AND i.penalty_type IS NOT NULL
          AND d.season >= (SELECT MAX(season) FROM decisions) - :seasons + 1
        GROUP BY d.season, i.penalty_type
        ORDER BY d.season
        """,
        {"cat": infraction_category, "seasons": seasons},
    )

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No incidents found for category {infraction_category!r}",
        )

    # Season breakdown
    by_season: dict[int, dict[str, int]] = {}
    for season_yr, penalty, cnt in rows:
        if season_yr not in by_season:
            by_season[season_yr] = {}
        by_season[season_yr][penalty] = cnt

    # All-time aggregation
    all_counts: dict[str, int] = {}
    for season_counts in by_season.values():
        for penalty, cnt in season_counts.items():
            all_counts[penalty] = all_counts.get(penalty, 0) + cnt

    # Severity trend: is penalty getting heavier or lighter over time?
    season_list = sorted(by_season.keys())
    severity_trend = [
        {
            "season":         yr,
            "counts":         by_season[yr],
            "modal":          _modal(by_season[yr]),
            "mean_severity":  _mean_severity(by_season[yr]),
            "inconsistency":  _inconsistency_score(by_season[yr]),
        }
        for yr in season_list
    ]

    # Slope of mean severity (positive = getting stricter)
    if len(season_list) >= 2:
        severities = [s["mean_severity"] for s in severity_trend]
        x_mean = sum(season_list) / len(season_list)
        y_mean = sum(severities) / len(severities)
        numerator   = sum((x - x_mean) * (y - y_mean) for x, y in zip(season_list, severities))
        denominator = sum((x - x_mean) ** 2 for x in season_list)
        slope = round(numerator / denominator, 4) if denominator else 0.0
    else:
        slope = 0.0

    return {
        "infraction_category": infraction_category,
        "total_incidents":     sum(all_counts.values()),
        "penalty_distribution": all_counts,
        "modal_penalty":       _modal(all_counts),
        "mean_severity":       _mean_severity(all_counts),
        "inconsistency_score": _inconsistency_score(all_counts),
        "severity_slope":      slope,
        "trend_interpretation": (
            "getting stricter" if slope > 0.05
            else "getting more lenient" if slope < -0.05
            else "broadly consistent"
        ),
        "season_breakdown":    severity_trend,
    }
