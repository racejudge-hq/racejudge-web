"""Allow an event to exist without a sourced venue.

Migration 014.

`events.circuit` and `events.country` were NOT NULL. Every event in the corpus
is recovered from the decision headers, which name the event but not the
circuit — the venue has to come from OpenF1, and OpenF1's meetings endpoint
returns 404 for 2019 through 2022. That leaves 82 of 158 events with no
sourced venue: the whole of 2019-2022, plus nothing else (all 76 events from
2023 onward match a meeting).

The alternative was to fill the gap from memory, which would put invented
data in the table and no way to tell it apart later. A NULL says what is
actually true: we do not have it yet. If a source for the older seasons turns
up, the column fills in with no schema change.

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("events", "circuit", existing_type=sa.Text(), nullable=True)
    op.alter_column("events", "country", existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    # Rows with no sourced venue cannot satisfy NOT NULL and have nothing
    # truthful to fall back on; drop them rather than invent a circuit.
    op.execute("DELETE FROM events WHERE circuit IS NULL OR country IS NULL")
    op.alter_column("events", "circuit", existing_type=sa.Text(), nullable=False)
    op.alter_column("events", "country", existing_type=sa.Text(), nullable=False)
