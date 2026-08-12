"""Widen ck_incidents_penalty_type to cover warnings, fines and stop-and-go.

Migration 010.

The original constraint allowed only NFA/REP/5s/10s/DT/GRID/DSQ. That set does
not cover three outcomes the stewards issue routinely:

  WARN  standalone warning        (77 rulings in the current corpus)
  FINE  monetary fine             (113 rulings)
  SG    stop-and-go penalty       (9 rulings; distinct from a drive-through)

Those rulings had a clearly stated decision but no representable penalty_type,
so they stored NULL. The regex arm additionally admits any "Ns" time penalty —
the FIA issues 15s, 20s and 30s penalties as well as 5s and 10s, and those fell
through to NULL for the same reason.

Widening a CHECK constraint cannot invalidate existing rows: every value the old
constraint permitted is still permitted.

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-12
"""

from __future__ import annotations

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

_NEW = (
    "penalty_type IN ('NFA','REP','WARN','FINE','SG','DT','GRID','DSQ')"
    " OR penalty_type ~ '^[0-9]{1,2}s$'"
)
_OLD = "penalty_type IN ('NFA','REP','5s','10s','DT','GRID','DSQ')"


def upgrade() -> None:
    op.drop_constraint("ck_incidents_penalty_type", "incidents", type_="check")
    op.create_check_constraint("ck_incidents_penalty_type", "incidents", _NEW)


def downgrade() -> None:
    # Values outside the old set must be cleared first, or the narrower
    # constraint cannot be created.
    op.execute(
        "UPDATE incidents SET penalty_type = NULL "
        "WHERE penalty_type IS NOT NULL "
        "AND penalty_type NOT IN ('NFA','REP','5s','10s','DT','GRID','DSQ')"
    )
    op.drop_constraint("ck_incidents_penalty_type", "incidents", type_="check")
    op.create_check_constraint("ck_incidents_penalty_type", "incidents", _OLD)
