"""
RACEJUDGE FastAPI application — Phases 1-7.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.core.config import settings
from apps.api.middleware.rate_limit import RateLimitMiddleware
from apps.api.routers import (
    annotations as annotations_router,
)
from apps.api.routers import (
    apikeys,
    billing,
    decisions,
    guidelines,
    health,
    incidents,
    live,
    mcp,
    precedents,
    predict,
    review,
    search,
    telemetry,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.environ.get("DATABASE_URL"):
        try:
            from packages.db.database import _get_engine
            _get_engine()
        except Exception:
            pass
    yield


app = FastAPI(
    title="RACEJUDGE API",
    version="0.2.0",
    description=(
        "F1 stewards' decision precedent search, penalty prediction, "
        "and Right-of-Review builder. Phase 7: API keys, billing, MCP server."
    ),
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
    lifespan=lifespan,
)

# CORS must be added before rate-limit middleware so preflight requests pass
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware)

# Core routes (Phases 1–6)
app.include_router(health.router)
app.include_router(decisions.router,              prefix="/v1")
app.include_router(search.router,                 prefix="/v1")
app.include_router(incidents.router,              prefix="/v1")
app.include_router(annotations_router.router,     prefix="/v1")
app.include_router(telemetry.router,              prefix="/v1")
app.include_router(predict.router,                prefix="/v1")
app.include_router(precedents.router,             prefix="/v1")
app.include_router(guidelines.router,             prefix="/v1")
app.include_router(live.router,                   prefix="/v1")

# Phase 7 routes
app.include_router(billing.router,                prefix="/v1")
app.include_router(apikeys.router,                prefix="/v1")
app.include_router(review.router,                 prefix="/v1")
app.include_router(mcp.router,                    prefix="/mcp/v1")
