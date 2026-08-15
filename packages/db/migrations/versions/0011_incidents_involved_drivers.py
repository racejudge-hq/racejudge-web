"""Record the other cars in an incident, separately from the accused.

Migration 011.

An incident row could name exactly one driver, so a collision was stored as a
ruling against a car with no trace of the car it hit. 297 rulings in the current
corpus state a counterparty in their Fact section — every impeding, unsafe
release, forcing-off and collision decision — and all of it was being discarded.

`involved_drivers` holds those cars. They are kept out of `drivers` on purpose:
every driver-scoped query in the API (`/v1/drivers/{code}/stats`, the incident
list filter, both search paths) reads `drivers @> [{"code": ...}]` and means by
it "was penalised". A counterparty stored there would add someone else's penalty
to the record of the driver they drove into.

The GIN index mirrors the one on `drivers` — the point of the column is to be
able to ask who else was involved, which is a containment query.

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "incidents",
        sa.Column(
            "involved_drivers",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.create_index(
        "idx_incidents_involved_drivers",
        "incidents",
        ["involved_drivers"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("idx_incidents_involved_drivers", table_name="incidents")
    op.drop_column("incidents", "involved_drivers")
