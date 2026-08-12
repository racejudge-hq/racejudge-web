"""Add the missing steward_panels.created_at column. Migration 009.

Migration 0004 created steward_panels without a created_at column, but the
StewardPanel ORM model declares one. Any ORM read or write against that table
therefore fails with UndefinedColumn. The bug stayed latent only because the
table is not yet populated (0 rows) and nothing queries it.

Every other table in the schema carries created_at TIMESTAMPTZ DEFAULT now(),
so the DB is brought in line with the model rather than the column being
dropped from the model.

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-12
"""

from __future__ import annotations

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE steward_panels
        ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE steward_panels DROP COLUMN IF EXISTS created_at;")
