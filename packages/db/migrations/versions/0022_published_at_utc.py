"""Give the publication date a type. Migration 0022.

`decisions.published_at` is TEXT holding whatever the FIA's listing page had in
its date element -- 1,447 rows read `Published on08.10.23 20:58CET`, the other
159 read `07.12.25 15:59`. As text it cannot be compared, filtered or ordered:
`packages/ml/predictor_v2.py` does `ORDER BY d.season, d.published_at`, which
sorts the literal string, so every `Published on...` row sorts after every bare
one and within each group the ordering is by day-of-month before month.

This adds `published_at_utc TIMESTAMPTZ` beside it rather than converting in
place. The raw string stays: it is what the source said, and a parse that later
turns out to be wrong should be re-derivable from it.

The zone is the part worth recording. The page labels every row `CET`, in July
as well as January, so the label alone cannot say whether it means a fixed
UTC+1 or Paris local time. Measured against the 642 incidents whose UTC time is
known and validated, publication lag behaves like this:

                        winter    summer
    read as fixed UTC+1   114 min   192 min
    read as Paris local   114 min   132 min

Winter is identical under both, as it must be. Only the summer reading
separates them, and the fixed-UTC+1 reading inflates it by almost exactly the
hour that a missed DST change would add. Paris local brings summer to within 18
minutes of winter, so that is what the label means and what is stored. No row
comes out published before the incident it describes under either reading, so
that check alone could not have decided it.

Revision ID: 0022
Revises: 0021
"""

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "decisions",
        sa.Column("published_at_utc", sa.DateTime(timezone=True), nullable=True),
    )
    # Ordering and season/date filtering are what the column is for.
    op.create_index(
        "ix_decisions_published_at_utc", "decisions", ["published_at_utc"]
    )


def downgrade() -> None:
    op.drop_index("ix_decisions_published_at_utc", table_name="decisions")
    op.drop_column("decisions", "published_at_utc")
