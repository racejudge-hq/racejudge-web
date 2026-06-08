"""
Latency tracking middleware — Phase 8.

Maintains a rolling window of the last 1 000 request durations per endpoint.
Exposed at GET /v1/metrics/latency (internal; should be firewalled in prod).
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from fastapi import APIRouter
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# Rolling window: path → list of durations in ms (capped at 1 000 entries)
_latency: dict[str, list[float]] = defaultdict(list)
_WINDOW = 1_000

# Paths excluded from tracking (high-volume noise or health probes)
_SKIP = {"/health", "/docs", "/openapi.json", "/redoc", "/v1/metrics/latency"}


def _percentile(data: list[float], p: int) -> float:
    if not data:
        return 0.0
    s = sorted(data)
    idx = max(0, int(len(s) * p / 100) - 1)
    return round(s[idx], 2)


class LatencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        t0 = time.perf_counter()
        response = await call_next(request)

        if path not in _SKIP:
            ms = (time.perf_counter() - t0) * 1_000
            bucket = _latency[path]
            bucket.append(ms)
            if len(bucket) > _WINDOW:
                _latency[path] = bucket[-_WINDOW:]

        return response


# ---------------------------------------------------------------------------
# Metrics endpoint
# ---------------------------------------------------------------------------

router = APIRouter(tags=["metrics"])


@router.get("/metrics/latency")
async def latency_metrics() -> dict[str, Any]:
    """
    Return p50 / p95 / p99 latency (ms) per endpoint.
    Only endpoints with ≥10 samples are included.
    """
    out: dict[str, Any] = {}
    for path, times in _latency.items():
        if len(times) >= 10:
            out[path] = {
                "samples": len(times),
                "p50_ms":  _percentile(times, 50),
                "p95_ms":  _percentile(times, 95),
                "p99_ms":  _percentile(times, 99),
                "min_ms":  round(min(times), 2),
                "max_ms":  round(max(times), 2),
            }
    return out
