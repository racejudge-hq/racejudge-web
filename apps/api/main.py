"""
RACEJUDGE FastAPI application — Phases 1-8.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.core.config import settings
from apps.api.middleware.latency import LatencyMiddleware
from apps.api.middleware.latency import router as metrics_router
from apps.api.middleware.rate_limit import RateLimitMiddleware
from apps.api.middleware.security_headers import SecurityHeadersMiddleware
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
    stewards,
    telemetry,
)

log = logging.getLogger(__name__)


def _init_sentry() -> None:
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        sentry_sdk.init(
            dsn=dsn,
            integrations=[StarletteIntegration(), FastApiIntegration()],
            traces_sample_rate=float(os.environ.get("SENTRY_TRACES_RATE", "0.05")),
            environment=settings.environment,
            release=os.environ.get("FLY_IMAGE_REF", "local"),
        )
        log.info("Sentry initialised (environment=%s)", settings.environment)
    except ImportError:
        log.warning("SENTRY_DSN set but sentry-sdk not installed — pip install sentry-sdk[fastapi]")
    except Exception as exc:
        log.warning("Sentry init failed: %s", exc)


async def _warm_hnsw() -> None:
    """Run a cheap query on app start so Postgres loads the HNSW index into memory."""
    try:
        from sqlalchemy import text

        from packages.db.database import _get_session_factory

        factory = _get_session_factory()
        if factory is None:
            return
        async with factory() as db:
            row = (await db.execute(
                text("SELECT COUNT(*) FROM incidents WHERE embedding IS NOT NULL"),
            )).fetchone()
            count = row[0] if row else 0
            log.info("HNSW pre-warm: %d embedded incidents", count)
    except Exception as exc:
        log.debug("HNSW pre-warm skipped: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _init_sentry()
    if os.environ.get("DATABASE_URL"):
        try:
            from packages.db.database import _get_engine
            _get_engine()
        except Exception:
            pass
        await _warm_hnsw()
    yield


app = FastAPI(
    title="RACEJUDGE API",
    version="0.3.0",
    description=(
        "F1 stewards' decision precedent search, penalty prediction, "
        "Right-of-Review builder, and consistency analysis. "
        "Phase 8: latency metrics, variance analysis, Sentry monitoring."
    ),
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
    lifespan=lifespan,
)

# CORS first — preflight must pass before rate limiting
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(LatencyMiddleware)
app.add_middleware(RateLimitMiddleware)

# Phase 1–6 core routes
app.include_router(health.router)
app.include_router(decisions.router,              prefix="/v1")
app.include_router(search.router,                 prefix="/v1")
# stewards must be before incidents — its /incidents/variance routes are more
# specific than incidents' /incidents/{incident_id} wildcard
app.include_router(stewards.router,               prefix="/v1")
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

# Phase 8 routes
app.include_router(metrics_router,                prefix="/v1")
