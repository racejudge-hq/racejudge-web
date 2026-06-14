"""
Billing router — Phase 7.

Endpoints:
  POST /v1/billing/webhook        — Stripe webhook (raw body, signature-verified)
  GET  /v1/billing/subscription   — current subscription status for a user
  POST /v1/billing/portal         — create a Stripe Customer Portal session

All endpoints degrade gracefully when STRIPE_SECRET_KEY is not set.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from apps.api.core.auth import ensure_user_match, get_verified_user_id
from apps.api.core.config import settings

log = logging.getLogger(__name__)
router = APIRouter(tags=["billing"])


# ---------------------------------------------------------------------------
# Stripe webhook
# ---------------------------------------------------------------------------

@router.post("/billing/webhook", include_in_schema=False)
async def stripe_webhook(request: Request) -> JSONResponse:
    """
    Receives Stripe events and keeps the `subscriptions` table in sync.

    Handled events:
      customer.subscription.created / updated / deleted
      invoice.payment_succeeded / invoice.payment_failed
    """
    if not settings.stripe_enabled:
        return JSONResponse({"received": True})

    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")

    try:
        import stripe  # type: ignore[import]
        stripe.api_key = settings.stripe_secret_key
        event = stripe.Webhook.construct_event(
            payload, sig, settings.stripe_webhook_secret
        )
    except Exception as exc:
        log.warning("Stripe webhook signature verification failed: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid Stripe signature") from exc

    event_type: str = event["type"]
    data_obj: dict[str, Any] = event["data"]["object"]

    log.info("Stripe event: %s", event_type)

    if event_type in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        await _upsert_subscription(data_obj)

    elif event_type == "invoice.payment_failed":
        await _mark_past_due(data_obj.get("customer"))

    return JSONResponse({"received": True})


async def _upsert_subscription(sub_obj: dict[str, Any]) -> None:
    from datetime import UTC, datetime

    import stripe  # type: ignore[import]

    stripe_sub_id = sub_obj.get("id", "")
    customer_id   = sub_obj.get("customer", "")
    status        = sub_obj.get("status", "active")
    period_end    = sub_obj.get("current_period_end")
    cancel_at_eop = sub_obj.get("cancel_at_period_end", False)

    # Derive tier from price IDs in line items
    tier = "free"
    items = (sub_obj.get("items") or {}).get("data", [])
    for item in items:
        price_id = (item.get("price") or {}).get("id", "")
        if price_id == settings.stripe_team_price_id:
            tier = "team"
            break
        if price_id == settings.stripe_pro_price_id:
            tier = "pro"

    # Resolve Clerk user_id from Stripe customer metadata
    stripe.api_key = settings.stripe_secret_key
    try:
        customer = stripe.Customer.retrieve(customer_id)
        user_id  = (getattr(customer, "metadata", None) or {}).get("clerk_user_id", "")
    except Exception as exc:
        log.warning("Could not retrieve Stripe customer %s: %s", customer_id, exc)
        user_id = ""

    if not user_id:
        log.warning("No clerk_user_id in Stripe customer %s metadata — skipping upsert", customer_id)
        return

    db_url = __import__("os").environ.get("DATABASE_URL")
    if not db_url:
        return

    try:
        from sqlalchemy import text

        from packages.db.database import _get_session_factory

        factory = _get_session_factory()
        if factory is None:
            return

        pe_ts = (
            datetime.fromtimestamp(period_end, tz=UTC).isoformat()
            if period_end else None
        )

        async with factory() as session:
            await session.execute(
                text("""
                    INSERT INTO subscriptions
                        (user_id, stripe_customer_id, stripe_subscription_id,
                         tier, status, current_period_end, cancel_at_period_end, updated_at)
                    VALUES
                        (:uid, :cid, :sid, :tier, :status, :pe, :cae, NOW())
                    ON CONFLICT (user_id) DO UPDATE SET
                        stripe_customer_id     = EXCLUDED.stripe_customer_id,
                        stripe_subscription_id = EXCLUDED.stripe_subscription_id,
                        tier                   = EXCLUDED.tier,
                        status                 = EXCLUDED.status,
                        current_period_end     = EXCLUDED.current_period_end,
                        cancel_at_period_end   = EXCLUDED.cancel_at_period_end,
                        updated_at             = NOW()
                """),
                {
                    "uid":    user_id,
                    "cid":    customer_id,
                    "sid":    stripe_sub_id,
                    "tier":   tier,
                    "status": status,
                    "pe":     pe_ts,
                    "cae":    cancel_at_eop,
                },
            )
            await session.commit()
            log.info("Subscription upserted: user=%s tier=%s status=%s", user_id, tier, status)
    except Exception as exc:
        log.error("Failed to upsert subscription: %s", exc)


async def _mark_past_due(customer_id: str | None) -> None:
    if not customer_id:
        return
    db_url = __import__("os").environ.get("DATABASE_URL")
    if not db_url:
        return
    try:
        from sqlalchemy import text

        from packages.db.database import _get_session_factory

        factory = _get_session_factory()
        if factory is None:
            return
        async with factory() as session:
            await session.execute(
                text("UPDATE subscriptions SET status='past_due', updated_at=NOW() WHERE stripe_customer_id=:cid"),
                {"cid": customer_id},
            )
            await session.commit()
    except Exception as exc:
        log.error("Failed to mark subscription past_due: %s", exc)


# ---------------------------------------------------------------------------
# Subscription status
# ---------------------------------------------------------------------------

class SubscriptionStatus(BaseModel):
    user_id:              str
    tier:                 str
    status:               str
    current_period_end:   str | None = None
    cancel_at_period_end: bool = False
    stripe_enabled:       bool


@router.get("/billing/subscription", response_model=SubscriptionStatus)
async def get_subscription(
    user_id: str = Query(..., description="Clerk user_id"),
    verified_user: str | None = Depends(get_verified_user_id),
) -> dict[str, Any]:
    """Return the current subscription tier and status for a user."""
    ensure_user_match(verified_user, user_id)
    db_url = __import__("os").environ.get("DATABASE_URL")
    if db_url:
        try:
            from sqlalchemy import text

            from packages.db.database import _get_session_factory

            factory = _get_session_factory()
            if factory is not None:
                async with factory() as session:
                    row = (await session.execute(
                        text("SELECT tier, status, current_period_end, cancel_at_period_end FROM subscriptions WHERE user_id=:uid"),
                        {"uid": user_id},
                    )).fetchone()
                    if row:
                        return {
                            "user_id":              user_id,
                            "tier":                 row[0],
                            "status":               row[1],
                            "current_period_end":   row[2].isoformat() if row[2] else None,
                            "cancel_at_period_end": row[3],
                            "stripe_enabled":       settings.stripe_enabled,
                        }
        except Exception as exc:
            log.warning("Subscription lookup failed: %s", exc)

    # Default: free tier
    return {
        "user_id":              user_id,
        "tier":                 "free",
        "status":               "active",
        "current_period_end":   None,
        "cancel_at_period_end": False,
        "stripe_enabled":       settings.stripe_enabled,
    }


# ---------------------------------------------------------------------------
# Customer portal
# ---------------------------------------------------------------------------

class PortalRequest(BaseModel):
    user_id:    str
    return_url: str = "http://localhost:3000/api"


class PortalResponse(BaseModel):
    url: str


@router.post("/billing/portal", response_model=PortalResponse)
async def create_portal_session(
    body: PortalRequest,
    verified_user: str | None = Depends(get_verified_user_id),
) -> dict[str, Any]:
    """Create a Stripe Customer Portal session so the user can manage billing."""
    ensure_user_match(verified_user, body.user_id)
    if not settings.stripe_enabled:
        raise HTTPException(
            status_code=503,
            detail="Billing not configured. Add STRIPE_SECRET_KEY to enable subscriptions.",
        )

    # Only allow return URLs back to our own frontend
    allowed = {o.rstrip("/") for o in settings.allowed_origins}
    if not any(body.return_url.rstrip("/").startswith(o) for o in allowed):
        raise HTTPException(status_code=400, detail="return_url must point to an allowed origin.")

    db_url = __import__("os").environ.get("DATABASE_URL")
    customer_id: str | None = None

    if db_url:
        try:
            from sqlalchemy import text

            from packages.db.database import _get_session_factory

            factory = _get_session_factory()
            if factory is not None:
                async with factory() as session:
                    row = (await session.execute(
                        text("SELECT stripe_customer_id FROM subscriptions WHERE user_id=:uid"),
                        {"uid": body.user_id},
                    )).fetchone()
                    if row:
                        customer_id = row[0]
        except Exception as exc:
            log.warning("Portal customer_id lookup failed: %s", exc)

    if not customer_id:
        raise HTTPException(status_code=404, detail="No Stripe customer found for this user. Subscribe first.")

    try:
        import stripe  # type: ignore[import]
        stripe.api_key = settings.stripe_secret_key
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=body.return_url,
        )
        return {"url": session.url}
    except Exception as exc:
        log.error("Stripe portal creation failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Stripe error: {exc}") from exc
