"""
Live session router — Phase 6.

WebSocket endpoint: WS /v1/live
  Streams real-time incident alerts pushed via Redis Pub/Sub.
  Falls back to polling the OpenF1 API when Redis is unavailable.

HTTP endpoint: GET /v1/live/sessions
  Returns active/recent sessions for the session selector.

Redis channel: racejudge:live:incidents
  Publisher: packages/pipeline/workers/live_publisher.py
  Message schema:
    {
        "type": "incident_alert",
        "session_key": 9158,
        "incident_id": "uuid",
        "drivers": [{"code": "VER", "full_name": "Max Verstappen"}],
        "infraction": "causing_a_collision",
        "message": "Race control message text",
        "timestamp": "2026-05-26T15:32:10Z"
    }
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

log = logging.getLogger(__name__)
router = APIRouter(tags=["live"])

REDIS_URL    = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
LIVE_CHANNEL = "racejudge:live:incidents"
PING_INTERVAL = 25  # seconds


# ---------------------------------------------------------------------------
# Redis helper (lazy, optional)
# ---------------------------------------------------------------------------

async def _get_redis():
    """Return async Redis client or None if redis package isn't installed."""
    try:
        import redis.asyncio as aioredis
        client = aioredis.from_url(REDIS_URL, decode_responses=True)
        await client.ping()
        return client
    except ImportError:
        return None
    except Exception as exc:
        log.warning("Redis unavailable: %s — live mode degraded", exc)
        return None


# ---------------------------------------------------------------------------
# OpenF1 polling fallback
# ---------------------------------------------------------------------------

async def _poll_openf1(session_key: int) -> list[dict[str, Any]]:
    """Poll OpenF1 race control messages for a session."""
    try:
        import httpx
        url = f"https://api.openf1.org/v1/race_control?session_key={session_key}&category=SafetyCar,Flag"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                return [
                    {
                        "type":        "race_control",
                        "session_key": session_key,
                        "message":     msg.get("message", ""),
                        "flag":        msg.get("flag"),
                        "timestamp":   msg.get("date", datetime.now(UTC).isoformat()),
                    }
                    for msg in data[-10:]  # last 10 messages
                ]
    except Exception:
        pass
    return []


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@router.websocket("/live")
async def live_websocket(websocket: WebSocket):
    """
    Stream live incident alerts to the client.

    Query params:
        session_key (int, optional): filter to a specific session.

    Message types:
        {"type": "connected", "channel": "...", "timestamp": "..."}
        {"type": "incident_alert", ...}
        {"type": "ping", "timestamp": "..."}
        {"type": "error", "detail": "..."}
    """
    await websocket.accept()
    session_key: int | None = None

    try:
        qs = dict(websocket.query_params)
        if sk := qs.get("session_key"):
            session_key = int(sk)
    except (ValueError, AttributeError):
        pass

    await websocket.send_json({
        "type":        "connected",
        "channel":     LIVE_CHANNEL,
        "session_key": session_key,
        "timestamp":   datetime.now(UTC).isoformat(),
    })

    redis = await _get_redis()

    if redis:
        await _serve_from_redis(websocket, redis, session_key)
    else:
        await _serve_from_polling(websocket, session_key)


async def _serve_from_redis(
    websocket: WebSocket,
    redis,
    session_key: int | None,
) -> None:
    pubsub = redis.pubsub()
    await pubsub.subscribe(LIVE_CHANNEL)
    last_ping = asyncio.get_event_loop().time()

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue

            try:
                data = json.loads(message["data"])
            except (json.JSONDecodeError, TypeError):
                continue

            # Filter by session if requested
            if session_key and data.get("session_key") != session_key:
                continue

            await websocket.send_json(data)

            # Keepalive ping every PING_INTERVAL seconds
            now = asyncio.get_event_loop().time()
            if now - last_ping > PING_INTERVAL:
                await websocket.send_json({
                    "type": "ping",
                    "timestamp": datetime.now(UTC).isoformat(),
                })
                last_ping = now

    except WebSocketDisconnect:
        log.info("WebSocket client disconnected")
    except Exception as exc:
        log.error("WebSocket error: %s", exc)
        with contextlib.suppress(Exception):
            await websocket.send_json({"type": "error", "detail": str(exc)})
    finally:
        await pubsub.unsubscribe(LIVE_CHANNEL)
        await redis.aclose()


async def _serve_from_polling(
    websocket: WebSocket,
    session_key: int | None,
) -> None:
    """Fallback: poll OpenF1 every 5s when Redis isn't available."""
    await websocket.send_json({
        "type":   "warning",
        "detail": "Redis unavailable — polling OpenF1 API (5s interval)",
    })

    seen: set[str] = set()
    try:
        while True:
            if session_key:
                messages = await _poll_openf1(session_key)
                for msg in messages:
                    key = f"{msg.get('timestamp')}-{msg.get('message', '')}"
                    if key not in seen:
                        seen.add(key)
                        await websocket.send_json(msg)

            await websocket.send_json({
                "type":      "ping",
                "timestamp": datetime.now(UTC).isoformat(),
            })
            await asyncio.sleep(5)

    except WebSocketDisconnect:
        log.info("WebSocket client disconnected (polling mode)")
    except Exception as exc:
        log.error("Polling error: %s", exc)


# ---------------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------------

@router.get("/live/sessions")
async def get_live_sessions() -> list[dict[str, Any]]:
    """
    Return recent/active sessions from OpenF1.
    Used by the frontend session selector.
    """
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                "https://api.openf1.org/v1/sessions?session_type=Race&limit=5"
            )
            if resp.status_code == 200:
                sessions = resp.json()
                return [
                    {
                        "session_key":  s.get("session_key"),
                        "session_name": s.get("session_name"),
                        "date_start":   s.get("date_start"),
                        "circuit":      s.get("circuit_short_name"),
                        "country":      s.get("country_name"),
                    }
                    for s in sessions
                ]
    except Exception as exc:
        log.warning("Failed to fetch sessions from OpenF1: %s", exc)

    return []
