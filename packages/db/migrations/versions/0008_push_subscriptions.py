"""Add push_subscriptions table for Web Push notifications. Migration 008.

Stores browser PushManager subscriptions (endpoint + p256dh/auth keys) so the
API can notify subscribers when new stewards' decisions are published.

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-21
"""

from __future__ import annotations

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS push_subscriptions (
            id         TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
            endpoint   TEXT NOT NULL UNIQUE,
            p256dh     TEXT NOT NULL,
            auth       TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS push_subscriptions;")
