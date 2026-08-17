"""Store when the incident happened, and the offset needed to know it.

Every decision prints the time of the incident, in a Time field directly above
the Session field and distinct from the publication time in the letterhead.
Nothing read it, so the only timestamp an incident had was the moment the FIA
published the document — typically hours later, and on the wrong side of the
chequered flag. The weather linker fell back to exactly that when no race
control message was attached, which would have picked a weather reading from
outside the session.

The printed time is local circuit time. OpenF1 gives the offset per session and
it was being thrown away, so it is stored alongside the session; without it the
printed time cannot be turned into an instant.

Revision ID: 0017
Revises: 0016
"""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        # "02:00:00" as OpenF1 sends it. An interval, because that is what it
        # is, and because subtracting it from a timestamp is then the whole job.
        sa.Column("gmt_offset", sa.Interval(), nullable=True),
    )
    op.add_column(
        "incidents",
        sa.Column("incident_time", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("idx_incidents_incident_time", "incidents", ["incident_time"])


def downgrade() -> None:
    op.drop_index("idx_incidents_incident_time", table_name="incidents")
    op.drop_column("incidents", "incident_time")
    op.drop_column("sessions", "gmt_offset")
