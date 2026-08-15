"""Attach every decision to the race weekend it was issued at, and admit the
pit lane start as a penalty type.

Migration 013.

Two changes, both needed to make per-panel analysis possible.

1. `decisions.event_id`.

   A decision knew only its season. That is far too coarse to attribute a
   ruling to the panel that issued it, because a season has two dozen panels.
   `/v1/incidents/variance/by-panel` tried to bridge the gap by joining
   `decisions.season = events.season`, which matches every event of the season
   at once: with a populated `events` table that join multiplies each ruling by
   the number of events in its season, and every chair is credited with every
   other chair's decisions. The endpoint returned nothing only because `events`
   was empty, which concealed the fault.

   The link is drawn from the document's own header ("2024 AUSTRIAN GRAND PRIX
   / 28 - 30 June 2024"), which every decision in the corpus carries.

   ON DELETE SET NULL: losing an event's metadata must not delete the rulings
   issued at it.

2. 'PIT' added to the penalty-type check constraint.

   A pit lane start is the standard sanction for a parc fermé breach or an
   out-of-allocation power unit. It is neither a grid drop nor a drive-through,
   and had no code, so 71 of the 81 rulings that impose one stored no penalty
   type at all.

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

_OLD_PENALTY_TYPES = "'NFA','REP','WARN','FINE','SG','DT','GRID','DSQ'"
_NEW_PENALTY_TYPES = "'NFA','REP','WARN','FINE','SG','DT','GRID','DSQ','PIT'"


def _penalty_check(types: str) -> str:
    return f"penalty_type IN ({types}) OR penalty_type ~ '^[0-9]{{1,2}}s$'"


def upgrade() -> None:
    op.add_column("decisions", sa.Column("event_id", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_decisions_event_id",
        "decisions",
        "events",
        ["event_id"],
        ["event_id"],
        ondelete="SET NULL",
    )
    # Every per-panel and per-event query starts by grouping decisions by event.
    op.create_index("idx_decisions_event_id", "decisions", ["event_id"])

    op.drop_constraint("ck_incidents_penalty_type", "incidents", type_="check")
    op.create_check_constraint(
        "ck_incidents_penalty_type", "incidents", _penalty_check(_NEW_PENALTY_TYPES)
    )


def downgrade() -> None:
    # Rulings recorded as a pit lane start have no older code to fall back to;
    # clear them rather than let the narrowed constraint fail.
    op.execute("UPDATE incidents SET penalty_type = NULL WHERE penalty_type = 'PIT'")
    op.drop_constraint("ck_incidents_penalty_type", "incidents", type_="check")
    op.create_check_constraint(
        "ck_incidents_penalty_type", "incidents", _penalty_check(_OLD_PENALTY_TYPES)
    )

    op.drop_index("idx_decisions_event_id", table_name="decisions")
    op.drop_constraint("fk_decisions_event_id", "decisions", type_="foreignkey")
    op.drop_column("decisions", "event_id")
