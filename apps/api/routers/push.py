"""
Web Push router — Phase 6.

Browser push notifications for new stewards' decisions (VAPID / Web Push).

  GET  /v1/push/vapid-public-key  — the applicationServerKey for PushManager
  POST /v1/push/subscribe         — store a browser PushSubscription
  POST /v1/push/test              — send a test notification to all subscribers

Sending uses pywebpush with the VAPID keypair in env (VAPID_PUBLIC_KEY /
VAPID_PRIVATE_KEY / VAPID_SUBJECT). Stale (410/404) subscriptions are pruned.
"""
from __future__ import annotations

import json
import logging
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

log = logging.getLogger(__name__)
router = APIRouter(prefix="/push", tags=["push"])

VAPID_PUBLIC = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "mailto:admin@racejudge.app")


class SubKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscription(BaseModel):
    endpoint: str
    keys: SubKeys


@router.get("/vapid-public-key")
async def vapid_public_key() -> dict:
    if not VAPID_PUBLIC:
        raise HTTPException(503, "Push notifications are not configured")
    return {"publicKey": VAPID_PUBLIC}


@router.post("/subscribe")
async def subscribe(sub: PushSubscription) -> dict:
    from sqlalchemy import text

    from packages.db.database import _get_session_factory

    factory = _get_session_factory()
    if factory is None:
        raise HTTPException(503, "Database unavailable")

    async with factory() as db:
        await db.execute(
            text(
                "INSERT INTO push_subscriptions (endpoint, p256dh, auth) "
                "VALUES (:e, :p, :a) "
                "ON CONFLICT (endpoint) DO UPDATE SET p256dh = EXCLUDED.p256dh, auth = EXCLUDED.auth"
            ),
            {"e": sub.endpoint, "p": sub.keys.p256dh, "a": sub.keys.auth},
        )
        await db.commit()
    return {"ok": True}


def _send_one(endpoint: str, p256dh: str, auth: str, payload: dict) -> tuple[bool, str | None]:
    from pywebpush import WebPushException, webpush

    try:
        webpush(
            subscription_info={"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}},
            data=json.dumps(payload),
            vapid_private_key=VAPID_PRIVATE,
            vapid_claims={"sub": VAPID_SUBJECT},
            timeout=10,
        )
        return True, None
    except WebPushException as exc:
        return False, str(exc)


async def send_to_all(title: str, body: str, url: str = "/decisions") -> dict:
    """Push a notification to every stored subscription; prune dead ones."""
    if not VAPID_PRIVATE:
        return {"sent": 0, "error": "push not configured"}

    from sqlalchemy import text

    from packages.db.database import _get_session_factory

    factory = _get_session_factory()
    if factory is None:
        return {"sent": 0, "error": "db unavailable"}

    payload = {"title": title, "body": body, "url": url}
    sent, stale = 0, []
    async with factory() as db:
        rows = (await db.execute(text("SELECT endpoint, p256dh, auth FROM push_subscriptions"))).all()
        for endpoint, p256dh, auth in rows:
            ok, err = _send_one(endpoint, p256dh, auth, payload)
            if ok:
                sent += 1
            elif err and ("410" in err or "404" in err):
                stale.append(endpoint)
        for endpoint in stale:
            await db.execute(
                text("DELETE FROM push_subscriptions WHERE endpoint = :e"), {"e": endpoint}
            )
        if stale:
            await db.commit()
    return {"sent": sent, "removed_stale": len(stale)}


@router.post("/test")
async def test_push() -> dict:
    if not VAPID_PRIVATE:
        raise HTTPException(503, "Push notifications are not configured")
    return await send_to_all("RaceJudge", "🏁 Push notifications are working.")
