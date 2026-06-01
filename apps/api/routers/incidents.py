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


@router.get("/incidents/{incident_id}", response_model=IncidentDetail)
async def get_incident(incident_id: str) -> dict:
    if not _DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="DATABASE_URL required")
    result = await _pg_get(incident_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id!r} not found")
    return result


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
