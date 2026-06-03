"""
RACEJUDGE FastAPI application — Phase 1-3.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.core.config import settings
from apps.api.routers import (
    annotations as annotations_router,
)
from apps.api.routers import (
    decisions,
    guidelines,
    health,
    incidents,
    live,
    precedents,
    predict,
    search,
    telemetry,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm up DB engine if DATABASE_URL is set
    if os.environ.get("DATABASE_URL"):
        try:
            from packages.db.database import _get_engine
            _get_engine()
        except Exception:
            pass
    yield


app = FastAPI(
    title="RACEJUDGE API",
    version="0.1.0",
    description="F1 stewards' decision precedent search and penalty prediction engine.",
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(decisions.router,   prefix="/v1")
app.include_router(search.router,      prefix="/v1")
app.include_router(incidents.router,   prefix="/v1")
app.include_router(annotations_router.router, prefix="/v1")
app.include_router(telemetry.router,   prefix="/v1")
app.include_router(predict.router,     prefix="/v1")
app.include_router(precedents.router,  prefix="/v1")
app.include_router(guidelines.router,  prefix="/v1")
app.include_router(live.router,        prefix="/v1")
