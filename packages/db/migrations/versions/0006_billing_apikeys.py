"""Add api_keys, subscriptions, usage_logs tables. Migration 006.

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-08
"""

from __future__ import annotations

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE api_keys (
            key_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id         TEXT NOT NULL,
            key_hash        TEXT NOT NULL,
            key_prefix      TEXT NOT NULL,
            name            TEXT,
            tier            TEXT NOT NULL DEFAULT 'free',
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            requests_today  INTEGER NOT NULL DEFAULT 0,
            requests_total  BIGINT NOT NULL DEFAULT 0,
            last_used_at    TIMESTAMPTZ,
            revoked_at      TIMESTAMPTZ,
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT uq_api_keys_hash UNIQUE (key_hash),
            CONSTRAINT ck_api_keys_tier CHECK (tier IN ('free', 'pro', 'team'))
        );
        CREATE INDEX idx_api_keys_user_id ON api_keys(user_id);
        CREATE INDEX idx_api_keys_hash    ON api_keys(key_hash);
    """)

    op.execute("""
        CREATE TABLE subscriptions (
            subscription_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id               TEXT NOT NULL,
            stripe_customer_id    TEXT,
            stripe_subscription_id TEXT,
            tier                  TEXT NOT NULL DEFAULT 'free',
            status                TEXT NOT NULL DEFAULT 'active',
            current_period_end    TIMESTAMPTZ,
            cancel_at_period_end  BOOLEAN NOT NULL DEFAULT FALSE,
            created_at            TIMESTAMPTZ DEFAULT NOW(),
            updated_at            TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT uq_subscriptions_user        UNIQUE (user_id),
            CONSTRAINT uq_subscriptions_stripe_cus  UNIQUE (stripe_customer_id),
            CONSTRAINT uq_subscriptions_stripe_sub  UNIQUE (stripe_subscription_id),
            CONSTRAINT ck_subscriptions_tier   CHECK (tier   IN ('free', 'pro', 'team')),
            CONSTRAINT ck_subscriptions_status CHECK (status IN ('active', 'canceled', 'past_due', 'trialing'))
        );
        CREATE INDEX idx_subscriptions_stripe_cus ON subscriptions(stripe_customer_id);
    """)

    op.execute("""
        CREATE TABLE usage_logs (
            log_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            key_id       UUID REFERENCES api_keys(key_id) ON DELETE SET NULL,
            user_id      TEXT,
            endpoint     TEXT NOT NULL,
            method       TEXT NOT NULL DEFAULT 'GET',
            status_code  SMALLINT,
            latency_ms   INTEGER,
            ip_address   TEXT,
            created_at   TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX idx_usage_logs_key_id  ON usage_logs(key_id,  created_at DESC);
        CREATE INDEX idx_usage_logs_user_id ON usage_logs(user_id, created_at DESC);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS usage_logs;")
    op.execute("DROP TABLE IF EXISTS subscriptions;")
    op.execute("DROP TABLE IF EXISTS api_keys;")
