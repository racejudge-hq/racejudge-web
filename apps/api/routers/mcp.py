"""
MCP (Model Context Protocol) server — Phase 7.

Exposes RACEJUDGE data to AI assistants (Claude, ChatGPT, etc.) via the
standard MCP tool-call interface.

Endpoints:
  GET  /mcp/v1/manifest  — tool definitions (no auth required)
  POST /mcp/v1/query     — execute a tool call (API key required for Pro/Team)

Available tools:
  search_precedents  — full-text + semantic search over incidents
  get_incident       — fetch a single incident by ID
  get_driver_stats   — driver penalty history and ban-risk score
  predict_penalty    — XGBoost penalty prediction (requires ENABLE_PREDICTIONS)
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)
router = APIRouter(tags=["mcp"])

_MCP_VERSION = "2024-11-05"


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

_TOOLS: list[dict[str, Any]] = [
    {
        "name":        "search_precedents",
        "description": (
            "Search F1 stewards' incident precedents by natural language query. "
            "Returns ranked incident summaries with penalty outcomes and similarity scores."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query":    {"type": "string",  "description": "Incident description or search terms"},
                "top_k":    {"type": "integer", "description": "Number of results (1–20)", "default": 5},
                "season":   {"type": "integer", "description": "Filter by season year (e.g. 2024)"},
                "penalty":  {"type": "string",  "description": "Filter by penalty class: NFA, REP, 5s, 10s, DT, GRID, DSQ"},
            },
            "required": ["query"],
        },
    },
    {
        "name":        "get_incident",
        "description": "Fetch full details for a specific FIA stewards' incident by its UUID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "incident_id": {"type": "string", "description": "UUID of the incident"},
            },
            "required": ["incident_id"],
        },
    },
    {
        "name":        "get_driver_stats",
        "description": (
            "Return penalty history and ban-risk analysis for an F1 driver. "
            "Includes total incidents, penalty points, ban-risk score, and recent infractions."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "driver_code": {"type": "string", "description": "3-letter FIA driver code (e.g. VER, HAM, NOR)"},
                "season":      {"type": "integer", "description": "Season year filter (omit for all-time)"},
            },
            "required": ["driver_code"],
        },
    },
    {
        "name":        "predict_penalty",
        "description": (
            "Predict the most likely FIA penalty outcome for a described incident. "
            "Returns probability distribution over 7 classes: NFA, REP, 5s, 10s, DT, GRID, DSQ."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "incident_description": {"type": "string",  "description": "Plain-text incident description"},
                "infraction_type":      {"type": "string",  "description": "e.g. 'forcing_off_track', 'unsafe_pit_release'"},
                "session_type":         {"type": "string",  "description": "'Race', 'Qualifying', 'Practice'"},
                "contact":              {"type": "boolean", "description": "Whether physical contact occurred"},
            },
            "required": ["incident_description"],
        },
    },
]


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

@router.get("/manifest")
async def mcp_manifest() -> dict[str, Any]:
    """Return the MCP tool manifest. No authentication required."""
    return {
        "schema_version": _MCP_VERSION,
        "name":           "racejudge",
        "display_name":   "RACEJUDGE",
        "description":    (
            "Every FIA stewards' decision since 2019 — searchable, comparable, "
            "and explainable. Search precedents, fetch incident details, analyse "
            "driver penalty history, and predict penalty outcomes."
        ),
        "vendor":         "RACEJUDGE",
        "tools":          _TOOLS,
    }


# ---------------------------------------------------------------------------
# Query execution
# ---------------------------------------------------------------------------

class McpQueryRequest(BaseModel):
    tool:   str = Field(..., description="Tool name from manifest")
    params: dict[str, Any] = Field(default_factory=dict)


class McpQueryResponse(BaseModel):
    tool:   str
    result: Any
    error:  str | None = None


def _require_api_key(request: Request) -> None:
    """Dependency: require a valid API key for MCP tool calls."""
    key_info = getattr(request.state, "api_key", None)
    if key_info is None:
        raise HTTPException(
            status_code=401,
            detail=(
                "MCP queries require an API key. "
                "Create one at https://racejudge.com/api"
            ),
        )


@router.post("/query", response_model=McpQueryResponse)
async def mcp_query(
    body:    McpQueryRequest,
    request: Request,
    _auth:   None = Depends(_require_api_key),
) -> dict[str, Any]:
    """Execute a tool call. Requires a valid API key."""
    tool = body.tool
    p    = body.params

    result: Any
    try:
        if tool == "search_precedents":
            result = await _tool_search_precedents(p)
        elif tool == "get_incident":
            result = await _tool_get_incident(p)
        elif tool == "get_driver_stats":
            result = await _tool_get_driver_stats(p)
        elif tool == "predict_penalty":
            result = await _tool_predict_penalty(p)
        else:
            raise ValueError(f"Unknown tool: {tool!r}")
    except HTTPException:
        raise
    except Exception as exc:
        log.error("MCP tool %r failed: %s", tool, exc)
        return {"tool": tool, "result": None, "error": str(exc)}

    return {"tool": tool, "result": result, "error": None}


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

async def _tool_search_precedents(p: dict[str, Any]) -> list[dict[str, Any]]:
    query   = str(p.get("query", ""))
    top_k   = min(int(p.get("top_k", 5)), 20)
    season  = p.get("season")
    penalty = p.get("penalty")

    if not query:
        raise ValueError("query is required")

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        return []

    from sqlalchemy import text

    from packages.db.database import _get_session_factory

    factory = _get_session_factory()
    if factory is None:
        return []

    where_clauses = ["i.reasoning_text IS NOT NULL"]
    params: dict[str, Any] = {"q": query, "top_k": top_k}

    if season:
        where_clauses.append("d.season = :season")
        params["season"] = int(season)
    if penalty:
        where_clauses.append("i.penalty_type = :penalty")
        params["penalty"] = penalty

    where_sql = " AND ".join(where_clauses)

    async with factory() as session:
        rows = (await session.execute(
            text(f"""
                SELECT i.incident_id,
                       i.penalty_type,
                       i.infraction_category,
                       i.penalty_points,
                       left(i.reasoning_text, 300) AS summary,
                       d.season,
                       d.title,
                       ts_rank_cd(
                           to_tsvector('english', coalesce(i.reasoning_text,'')),
                           plainto_tsquery('english', :q)
                       ) AS rank
                FROM incidents i
                JOIN decisions d ON i.doc_id = d.doc_id
                WHERE {where_sql}
                  AND to_tsvector('english', coalesce(i.reasoning_text,'')) @@ plainto_tsquery('english', :q)
                ORDER BY rank DESC
                LIMIT :top_k
            """),
            params,
        )).fetchall()

    return [
        {
            "incident_id":        str(r[0]),
            "penalty_type":       r[1],
            "infraction_category": r[2],
            "penalty_points":     r[3],
            "summary":            r[4],
            "season":             r[5],
            "decision_title":     r[6],
            "relevance_score":    round(float(r[7]), 4),
        }
        for r in rows
    ]


async def _tool_get_incident(p: dict[str, Any]) -> dict[str, Any]:
    incident_id = str(p.get("incident_id", ""))
    if not incident_id:
        raise ValueError("incident_id is required")

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise HTTPException(status_code=503, detail="Database not configured.")

    from sqlalchemy import text

    from packages.db.database import _get_session_factory

    factory = _get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="Database unavailable.")

    async with factory() as session:
        row = (await session.execute(
            text("""
                SELECT i.incident_id, i.drivers, i.lap, i.corner,
                       i.article_cited, i.infraction_category, i.penalty_type,
                       i.penalty_seconds, i.penalty_points, i.contact,
                       i.reasoning_text, d.season, d.title, d.published_at,
                       d.pdf_url
                FROM incidents i
                JOIN decisions d ON i.doc_id = d.doc_id
                WHERE i.incident_id = :iid
            """),
            {"iid": incident_id},
        )).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found.")

    return {
        "incident_id":        str(row[0]),
        "drivers":            row[1] or [],
        "lap":                row[2],
        "corner":             row[3],
        "article_cited":      row[4] or [],
        "infraction_category": row[5],
        "penalty_type":       row[6],
        "penalty_seconds":    row[7],
        "penalty_points":     row[8],
        "contact":            row[9],
        "reasoning_text":     row[10],
        "season":             row[11],
        "decision_title":     row[12],
        "published_at":       row[13],
        "pdf_url":            row[14],
    }


async def _tool_get_driver_stats(p: dict[str, Any]) -> dict[str, Any]:
    code   = str(p.get("driver_code", "")).upper()
    season = p.get("season")

    if not code:
        raise ValueError("driver_code is required")

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        return {"driver_code": code, "error": "Database not configured"}

    from sqlalchemy import text

    from packages.db.database import _get_session_factory

    factory = _get_session_factory()
    if factory is None:
        return {"driver_code": code, "error": "Database unavailable"}

    params: dict[str, Any] = {"code": f'%"code": "{code}"%'}
    season_filter = "AND d.season = :season" if season else ""
    if season:
        params["season"] = int(season)

    async with factory() as session:
        row = (await session.execute(
            text(f"""
                SELECT
                    COUNT(*)                    AS total_incidents,
                    COALESCE(SUM(i.penalty_points), 0) AS total_points,
                    -- NFA, a warning and a reprimand are all non-sanctions;
                    -- WARN was added in migration 0010 and would otherwise have
                    -- inflated every driver's sanctioned count.
                    COUNT(*) FILTER (WHERE i.penalty_type NOT IN ('NFA','WARN','REP')) AS sanctioned,
                    MAX(d.season)               AS latest_season
                FROM incidents i
                JOIN decisions d ON i.doc_id = d.doc_id
                WHERE i.drivers::text ILIKE :code
                  {season_filter}
            """),
            params,
        )).fetchone()

    total   = int(row[0])
    points  = int(row[1])
    sanc    = int(row[2])

    # Ban-risk heuristic: 12 penalty points → 1-race ban
    ban_risk = min(round(points / 12, 2), 1.0)

    return {
        "driver_code":       code,
        "total_incidents":   total,
        "total_penalty_pts": points,
        "sanctioned_count":  sanc,
        "ban_risk_score":    ban_risk,
        "latest_season":     row[3],
    }


async def _tool_predict_penalty(p: dict[str, Any]) -> dict[str, Any]:
    if os.environ.get("ENABLE_PREDICTIONS", "false").lower() != "true":
        return {
            "error": "Penalty prediction not yet enabled (ENABLE_PREDICTIONS not set).",
        }

    infraction_type = p.get("infraction_type")
    session_type    = p.get("session_type")
    contact         = bool(p.get("contact", False))

    try:
        from pathlib import Path

        from packages.ml.predictor import PenaltyPredictor

        model_path = Path(__file__).resolve().parents[3] / "models" / "penalty_v1.pkl"
        if not model_path.exists():
            return {"error": "Model not trained yet."}

        model = PenaltyPredictor.load(model_path)
        record = {
            "parsed":             {"infraction_type": infraction_type, "session_type": session_type},
            "telemetry_features": {},
            "openf1":             {},
            "driver_history":     {},
            "contact":            contact,
        }
        result = model.predict(record)
        result["disclaimer"] = (
            "Probabilistic model output for research only. "
            "Does not represent an official FIA determination."
        )
        return result
    except Exception as exc:
        return {"error": str(exc)}
