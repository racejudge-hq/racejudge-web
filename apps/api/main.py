"""
RACEJUDGE FastAPI application — Phase 1 skeleton.

Endpoints live here initially; routers are split into sub-modules as they grow.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.core.config import settings
from apps.api.routers import decisions, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Phase 1: nothing to set up yet (DB pool added in Phase 1 week 2)
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
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(decisions.router, prefix="/v1")
