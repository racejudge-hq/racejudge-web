"""Add incident_id FK to race_control_messages (schema-drift fix). Migration 007.

The RaceControlMessage ORM model + race_control_linker reference
race_control_messages.incident_id, but no prior migration created the column.
This adds it so the race-control backfill can link messages to incidents.

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-19
"""

from __future__ import annotations

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE race_control_messages
            ADD COLUMN IF NOT EXISTS incident_id TEXT
            REFERENCES incidents(incident_id);
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE race_control_messages DROP COLUMN IF EXISTS incident_id;")
