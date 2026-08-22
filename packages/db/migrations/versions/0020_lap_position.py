"""Store the position FastF1 already reports on every lap. Migration 0020.

`incidents.position_change` has been read by the API and by the penalty
predictor since Phase 5 and has never held a value, because nothing in the
database recorded where a car was running. Reports up to v17 concluded it was
"not derivable from anything held" and recommended dropping the column.

That was true of the database and false of the source. `lap_features` is built
from FastF1's lap table in `scripts/_backfill_telemetry.py`, and that table
carries a `Position` column alongside the lap and sector times the script
already stores — it was simply not selected. On the 2024 Mexico City race it is
present on 1,213 of 1,215 laps.

So this adds the column rather than dropping `position_change`, and
`scripts/backfill_lap_positions.py` fills it from the same FastF1 session load
the telemetry backfill uses.

Sign convention, since nothing previously fixed one: `incidents.position_change`
is **places gained by the car the ruling is against**, positive meaning it
moved forward across the incident. A driver who fell from 4th to 7th scores -3.

Revision ID: 0020
Revises: 0019
"""

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("lap_features", sa.Column("position", sa.SmallInteger(), nullable=True))
    op.execute(
        "COMMENT ON COLUMN lap_features.position IS "
        "'Classified position at the end of this lap, from FastF1. "
        "NULL where FastF1 reports none.'"
    )
    op.execute(
        "COMMENT ON COLUMN incidents.position_change IS "
        "'Places gained by the car the ruling is against, across the incident. "
        "Positive means it moved forward. Derived from lap_features.position.'"
    )


def downgrade() -> None:
    op.drop_column("lap_features", "position")
