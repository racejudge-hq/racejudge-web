"""Distinguish a suspended penalty from one that was actually served.

Migration 012.

`penalty_type` records what the stewards imposed, with no way to say it was
never enforced. Hulkenberg's 2026 Canadian Grand Prix stop-and-go (document 99)
was suspended for the rest of the season and never served, but was stored as a
bare 'SG' — identical to a driver who served one. For a precedent engine that is
the most important fact in the ruling.

22 decisions in the current corpus carry a suspended penalty, not the handful it
first appeared to be. Only 6 are suspended in full; the other 16 are part-fines
("fined €50,000, €25,000 of which is suspended"), where half the penalty really
was paid. A boolean would have to claim one of those two things about both, so
the column is three-state: 'full', 'partial', or NULL for a penalty served in
the ordinary way.

NULL rather than a 'none' sentinel because the overwhelming majority of rulings
are not suspended, and the partial index keeps the common case free.

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("incidents", sa.Column("penalty_suspended", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_incidents_penalty_suspended",
        "incidents",
        "penalty_suspended IS NULL OR penalty_suspended IN ('full','partial')",
    )
    # Partial: suspended penalties are rare, and the queries that care about them
    # ask for the ones that exist.
    op.create_index(
        "idx_incidents_penalty_suspended",
        "incidents",
        ["penalty_suspended"],
        postgresql_where=sa.text("penalty_suspended IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_incidents_penalty_suspended", table_name="incidents")
    op.drop_constraint("ck_incidents_penalty_suspended", "incidents", type_="check")
    op.drop_column("incidents", "penalty_suspended")
