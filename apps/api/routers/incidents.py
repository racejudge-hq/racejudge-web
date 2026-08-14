"""
Incidents router — Phase 2.

GET  /v1/incidents          — list with full filter support
GET  /v1/incidents/:id      — full incident detail with linked RC messages + radio
POST /v1/incidents/extract  — on-demand extraction from a decision doc_id
"""

from __future__ import annotations

import os
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(tags=["incidents"])
_DB_AVAILABLE = bool(os.environ.get("DATABASE_URL"))


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class DriverRef(BaseModel):
    code: str | None = None
    full_name: str | None = None
    number: int | None = None


class RadioClipSummary(BaseModel):
    clip_id: str
    driver_number: int
    date: str
    transcript: str | None = None
    speaker_label: str | None = None


class RCMessageSummary(BaseModel):
    message_id: str
    date: str
    category: str | None = None
    message: str
    flag: str | None = None


class Incident(BaseModel):
    incident_id: str
    doc_id: str
    drivers: list[DriverRef] = []
    session_key: int | None = None
    lap: int | None = None
    corner: str | None = None
    article_cited: list[str] = []
    infraction_category: str | None = None
    penalty_type: str | None = None
    penalty_seconds: int | None = None
    penalty_points: int = 0
    contact: bool | None = None
    reasoning_text: str = ""
    weather_context: dict | None = None
    extractor_version: str = ""
    created_at: str = ""


class IncidentDetail(Incident):
    grid_positions: int | None = None
    position_change: int | None = None
    video_refs: list | None = None
    race_control_messages: list[RCMessageSummary] = []
    radio_clips: list[RadioClipSummary] = []


class ExtractRequest(BaseModel):
    doc_id: str
    force: bool = False


class ExtractResponse(BaseModel):
    incident_id: str | None
    doc_id: str
    penalty_type: str | None
    infraction_category: str | None
    confidence: float
    layer_used: int


# ---------------------------------------------------------------------------
# DB queries
# ---------------------------------------------------------------------------

async def _pg_list(
    season: int | None,
    penalty_type: str | None,
    infraction: str | None,
    driver: str | None,
    article: str | None,
    has_radio: bool | None,
    limit: int,
    offset: int,
) -> list[dict]:
    from sqlalchemy import select, text

    from packages.db.database import _get_session_factory
    from packages.db.models import Decision
    from packages.db.models import Incident as IncidentModel

    factory = _get_session_factory()
    if factory is None:
        return []

    async with factory() as db:
        stmt = select(IncidentModel).join(
            Decision, IncidentModel.doc_id == Decision.doc_id
        ).order_by(IncidentModel.created_at.desc())

        if season is not None:
            stmt = stmt.where(Decision.season == season)
        if penalty_type:
            stmt = stmt.where(IncidentModel.penalty_type == penalty_type.upper())
        if infraction:
            stmt = stmt.where(IncidentModel.infraction_category == infraction)
        if driver:
            stmt = stmt.where(
                text("drivers @> :d::jsonb").bindparams(d=f'[{{"code":"{driver.upper()}"}}]')
            )
        if article:
            stmt = stmt.where(
                text(":article = ANY(article_cited)").bindparams(article=article)
            )
        if has_radio is True:
            stmt = stmt.where(
                text("EXISTS (SELECT 1 FROM team_radio_clips rc "
                     "WHERE rc.incident_id = incidents.incident_id)")
            )

        stmt = stmt.offset(offset).limit(limit)
        result = await db.execute(stmt)
        rows = result.scalars().all()
        return [_incident_to_dict(r) for r in rows]


async def _pg_get(incident_id: str) -> dict | None:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from packages.db.database import _get_session_factory
    from packages.db.models import Incident as IncidentModel

    factory = _get_session_factory()
    if factory is None:
        return None

    async with factory() as db:
        result = await db.execute(
            select(IncidentModel)
            .options(
                selectinload(IncidentModel.race_control_messages),
                selectinload(IncidentModel.radio_clips),
            )
            .where(IncidentModel.incident_id == incident_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        d = _incident_to_dict(row, detail=True)
        d["race_control_messages"] = [
            {
                "message_id": rc.message_id,
                "date":       str(rc.date),
                "category":   rc.category,
                "message":    rc.message,
                "flag":       rc.flag,
            }
            for rc in row.race_control_messages
        ]
        d["radio_clips"] = [
            {
                "clip_id":       clip.clip_id,
                "driver_number": clip.driver_number,
                "date":          str(clip.date),
                "transcript":    clip.transcript,
                "speaker_label": clip.speaker_label,
            }
            for clip in row.radio_clips
        ]
        return d


def _incident_to_dict(row: Any, detail: bool = False) -> dict:
    drivers = row.drivers or []
    if isinstance(drivers, list):
        driver_list = [
            {"code": d.get("code"), "full_name": d.get("full_name"), "number": d.get("number")}
            for d in drivers
        ]
    else:
        driver_list = []

    d = {
        "incident_id":         row.incident_id,
        "doc_id":              row.doc_id,
        "drivers":             driver_list,
        "session_key":         row.session_key,
        "lap":                 row.lap,
        "corner":              row.corner,
        "article_cited":       row.article_cited or [],
        "infraction_category": row.infraction_category,
        "penalty_type":        row.penalty_type,
        "penalty_seconds":     row.penalty_seconds,
        "penalty_points":      row.penalty_points or 0,
        "contact":             row.contact,
        "reasoning_text":      row.reasoning_text or "",
        "weather_context":     row.weather_context,
        "extractor_version":   row.extractor_version or "",
        "created_at":          str(row.created_at) if row.created_at else "",
    }
    if detail:
        d.update({
            "grid_positions":  row.grid_positions,
            "position_change": row.position_change,
            "video_refs":      row.video_refs,
        })
    return d


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/incidents", response_model=list[Incident])
async def list_incidents(
    season:       Annotated[int | None,  Query()] = None,
    penalty_type: Annotated[str | None,  Query(description="NFA|REP|5s|10s|DT|GRID|DSQ")] = None,
    infraction:   Annotated[str | None,  Query(description="infraction_category slug")] = None,
    driver:       Annotated[str | None,  Query(description="Driver code e.g. VER")] = None,
    article:      Annotated[str | None,  Query(description="Article number e.g. 48.1")] = None,
    has_radio:    Annotated[bool | None, Query()] = None,
    limit:        Annotated[int,         Query(ge=1, le=200)] = 50,
    offset:       Annotated[int,         Query(ge=0)] = 0,
) -> list[dict]:
    if not _DB_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Incidents endpoint requires DATABASE_URL. Set it in .env.",
        )
    return await _pg_list(season, penalty_type, infraction, driver, article, has_radio, limit, offset)


# NOTE: this literal route MUST stay above "/incidents/{incident_id}". Starlette
# matches in declaration order, so with the parameterised route first, a request
# for /incidents/consistency was captured as incident_id="consistency" and never
# reached this handler — which is why the /consistency page was failing in
# production. Do not reorder.
@router.get("/incidents/consistency")
async def get_consistency_heatmap(
    season: Annotated[int | None, Query(ge=2018, le=2030)] = None,
) -> list[dict]:
    """
    Penalty outcome distribution by infraction_category × season.
    Powers the /consistency heat-map page.
    """
    if not _DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="DATABASE_URL required")

    from sqlalchemy import text

    from packages.db.database import _get_session_factory

    factory = _get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="DB session unavailable")

    season_clause = "AND d.season = :season" if season else ""
    sql = text(f"""
        SELECT
            i.infraction_category,
            d.season,
            COUNT(*)                                                          AS total,
            ROUND(100.0 * COUNT(*) FILTER (WHERE i.penalty_type = 'NFA')  / COUNT(*), 1) AS nfa_pct,
            ROUND(100.0 * COUNT(*) FILTER (WHERE i.penalty_type = 'WARN') / COUNT(*), 1) AS warn_pct,
            ROUND(100.0 * COUNT(*) FILTER (WHERE i.penalty_type = 'REP')  / COUNT(*), 1) AS rep_pct,
            ROUND(100.0 * COUNT(*) FILTER (WHERE i.penalty_type = 'FINE') / COUNT(*), 1) AS fine_pct,
            -- Regex, not IN ('5s','10s'): 15s/20s/30s penalties exist too and
            -- were falling outside every bucket, so the row failed to sum to 100.
            ROUND(100.0 * COUNT(*) FILTER (WHERE i.penalty_type ~ '^[0-9]{{1,2}}s$') / COUNT(*), 1) AS time_penalty_pct,
            -- SG groups with DT/GRID: all three are served rather than added.
            ROUND(100.0 * COUNT(*) FILTER (WHERE i.penalty_type IN ('DT','GRID','SG')) / COUNT(*), 1) AS grid_dt_pct,
            ROUND(100.0 * COUNT(*) FILTER (WHERE i.penalty_type = 'DSQ')  / COUNT(*), 1) AS dsq_pct,
            ROUND(AVG(i.penalty_points)::numeric, 2)                         AS avg_penalty_points
        FROM incidents i
        JOIN decisions d ON i.doc_id = d.doc_id
        WHERE i.infraction_category IS NOT NULL
          AND i.penalty_type IS NOT NULL
          {season_clause}
        GROUP BY i.infraction_category, d.season
        ORDER BY d.season DESC, total DESC
    """)

    params: dict = {}
    if season:
        params["season"] = season

    async with factory() as db:
        result = await db.execute(sql, params)
        rows = result.mappings().all()

    return [
        {
            "infraction_category": r["infraction_category"],
            "season":              r["season"],
            "total":               r["total"],
            "nfa_pct":             float(r["nfa_pct"] or 0),
            "warn_pct":            float(r["warn_pct"] or 0),
            "rep_pct":             float(r["rep_pct"] or 0),
            "fine_pct":            float(r["fine_pct"] or 0),
            "time_penalty_pct":    float(r["time_penalty_pct"] or 0),
            "grid_dt_pct":         float(r["grid_dt_pct"] or 0),
            "dsq_pct":             float(r["dsq_pct"] or 0),
            "avg_penalty_points":  float(r["avg_penalty_points"] or 0),
        }
        for r in rows
    ]


# Declared after every literal /incidents/... route above, so those are matched
# first rather than being swallowed as an incident_id.
@router.get("/incidents/{incident_id}", response_model=IncidentDetail)
async def get_incident(incident_id: str) -> dict:
    if not _DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="DATABASE_URL required")
    result = await _pg_get(incident_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id!r} not found")
    return result


@router.get("/drivers/{driver_code}/stats")
async def get_driver_stats(driver_code: str) -> dict:
    """
    Driver penalty cockpit — incident history, points breakdown, ban-risk score.
    Powers the /drivers/[code] page.
    """
    if not _DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="DATABASE_URL required")

    from sqlalchemy import text

    from packages.db.database import _get_session_factory

    code = driver_code.upper()
    factory = _get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="DB session unavailable")

    sql_incidents = text("""
        SELECT
            i.incident_id,
            d.title,
            d.season,
            d.published_at::text   AS published_at,
            i.penalty_type,
            i.penalty_points,
            i.infraction_category,
            i.article_cited,
            LEFT(i.reasoning_text, 300) AS reasoning_snippet
        FROM incidents i
        JOIN decisions d ON i.doc_id = d.doc_id
        WHERE i.drivers @> CAST(:driver_filter AS jsonb)
        ORDER BY d.season DESC, d.published_at DESC
        LIMIT 200
    """)

    async with factory() as db:
        result = await db.execute(
            sql_incidents, {"driver_filter": f'[{{"code":"{code}"}}]'}
        )
        rows = result.mappings().all()
        # The drivers table is seeded now, so the name no longer has to fall
        # back to the three-letter code.
        name_row = await db.execute(
            text("SELECT full_name FROM drivers WHERE code = :code LIMIT 1"),
            {"code": code},
        )
        full_name = name_row.scalar()

    if not rows:
        raise HTTPException(status_code=404, detail=f"No incidents found for driver {code!r}")

    incidents_list = [dict(r) for r in rows]

    # Aggregate stats
    total_pts = sum(r["penalty_points"] or 0 for r in incidents_list)
    # Superlicence points are counted over a rolling season, so this has to
    # follow the calendar rather than sit pinned to the year the endpoint was
    # written — pinned at 2025 it reported every 2026 driver as being on zero.
    # Taking the newest season present in the driver's own rows keeps it right
    # through the winter, when the latest season in the corpus is still the one
    # that just finished.
    current_year = max((r["season"] for r in incidents_list if r["season"]), default=None)
    season_pts = sum(
        r["penalty_points"] or 0
        for r in incidents_list
        if r["season"] == current_year
    )

    by_penalty: dict[str, int] = {}
    for r in incidents_list:
        pt = r["penalty_type"] or "NFA"
        by_penalty[pt] = by_penalty.get(pt, 0) + 1

    # Simple ban-risk heuristic: based on season points so far
    ban_risk: str
    if season_pts >= 10:
        ban_risk = "high"
    elif season_pts >= 7:
        ban_risk = "medium"
    elif season_pts >= 4:
        ban_risk = "low"
    else:
        ban_risk = "none"

    return {
        "code":                   code,
        "full_name":              full_name or code,
        "total_incidents":        len(incidents_list),
        "total_penalty_points":   total_pts,
        "current_season_points":  season_pts,
        "ban_risk":               ban_risk,
        "by_penalty":             by_penalty,
        "incidents":              incidents_list,
    }


@router.post("/incidents/extract", response_model=ExtractResponse, status_code=201)
async def extract_incident(body: ExtractRequest) -> dict:
    """
    On-demand: extract structured fields from a decision doc_id and store in incidents table.
    Idempotent: returns existing incident_id if already extracted (unless force=True).
    """
    if not _DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="DATABASE_URL required")

    from sqlalchemy import select

    from packages.db.database import _get_session_factory
    from packages.db.models import Decision
    from packages.db.models import Incident as IncidentModel
    from packages.pipeline.extractors.incident_extractor import IncidentExtractor

    factory = _get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="DB session unavailable")

    async with factory() as db:
        # Check existing
        if not body.force:
            existing = await db.execute(
                select(IncidentModel.incident_id, IncidentModel.penalty_type,
                       IncidentModel.infraction_category, IncidentModel.extractor_version)
                .where(IncidentModel.doc_id == body.doc_id)
            )
            row = existing.first()
            if row:
                return {
                    "incident_id":        row.incident_id,
                    "doc_id":             body.doc_id,
                    "penalty_type":       row.penalty_type,
                    "infraction_category": row.infraction_category,
                    "confidence":         1.0,
                    "layer_used":         0,
                }

        # Fetch decision
        dec_result = await db.execute(
            select(Decision).where(Decision.doc_id == body.doc_id)
        )
        decision = dec_result.scalar_one_or_none()
        if decision is None:
            raise HTTPException(status_code=404, detail=f"Decision {body.doc_id!r} not found")

        # Extract
        record = {
            "doc_id":    decision.doc_id,
            "season":    decision.season,
            "raw_text":  decision.raw_text or "",
            "char_count": decision.char_count,
        }
        extractor = IncidentExtractor()
        result    = extractor.extract(record)

        # Upsert incident
        incident = IncidentModel(
            doc_id              = body.doc_id,
            drivers             = result.drivers,
            lap                 = result.lap_number,
            corner              = result.corner,
            article_cited       = result.article_cited,
            infraction_category = result.infraction_category,
            penalty_type        = result.penalty_type,
            penalty_seconds     = result.penalty_seconds,
            penalty_points      = result.penalty_points,
            contact             = result.contact,
            reasoning_text      = result.reasoning_text,
            extractor_version   = result.extractor_version,
        )
        db.add(incident)
        await db.flush()

        return {
            "incident_id":        incident.incident_id,
            "doc_id":             body.doc_id,
            "penalty_type":       result.penalty_type,
            "infraction_category": result.infraction_category,
            "confidence":         result.confidence,
            "layer_used":         result.layer_used,
        }
