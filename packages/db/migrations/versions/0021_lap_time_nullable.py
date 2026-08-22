"""Let an unknown lap start be unknown. Migration 0021.

`lap_features.time` is the moment a lap began, and it is what places an
incident on a lap. It was created NOT NULL in migration 0003, so
`scripts/_backfill_telemetry.py` had to put *something* in every row and fell
back to the session's scheduled start whenever FastF1's `LapStartDate` was NaT.

That fallback was written for the occasional out-lap. It fired on all 105,768
rows: FastF1 only computes `LapStartDate` during the telemetry load, and the
backfill loads with `telemetry=False`. Every session ended up with one distinct
`time` -- its scheduled start -- across all of its laps, which reads as a
perfectly ordinary timestamp and is wrong by up to two hours.

A NOT NULL column that cannot always be known is what forced the invented
value, so the constraint is what changes here. `scripts/backfill_lap_times.py`
computes the real values from FastF1's `LapStartTime` plus `t0_date`; a lap
FastF1 cannot place is now left NULL rather than given the session start.

Nothing reads the column but the `position_change` derivation, which already
skips laps it cannot place, so dropping NOT NULL breaks no reader.

`time` first has to come out of the primary key, which is `(id, "time")`.
Migration 0003 wrote that composite key so the table could become a TimescaleDB
hypertable, and guarded the `create_hypertable` call on the extension being
installed. It is not installed on this database, so the hypertable was never
created and the partitioning column in the key has no purpose. `id` is a UUID
and is already unique on its own -- 105,768 distinct values across 105,768
rows -- so the key narrows to `(id)` without any other change.

Revision ID: 0021
Revises: 0020
"""

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Guarded: on a database where the hypertable *was* created, the
    # partitioning column must stay in the key and NOT NULL, and the backfill
    # simply leaves those laps at whatever it can determine.
    hypertable = op.get_bind().exec_driver_sql(
        "SELECT count(*) FROM pg_extension WHERE extname = 'timescaledb'"
    ).scalar()
    if hypertable:
        return

    op.drop_constraint("lap_features_pkey", "lap_features", type_="primary")
    op.create_primary_key("lap_features_pkey", "lap_features", ["id"])
    op.alter_column("lap_features", "time", nullable=True)
    op.execute(
        "COMMENT ON COLUMN lap_features.time IS "
        "'Absolute UTC start of this lap, from FastF1 t0_date + LapStartTime. "
        "NULL where FastF1 does not place the lap — never the session start.'"
    )


def downgrade() -> None:
    # Only reversible while no row relies on the relaxed constraint.
    op.execute("DELETE FROM lap_features WHERE time IS NULL")
    op.alter_column("lap_features", "time", nullable=False)
    op.drop_constraint("lap_features_pkey", "lap_features", type_="primary")
    op.create_primary_key("lap_features_pkey", "lap_features", ["id", "time"])
