"""A race control message can belong to more than one decision.

The stewards issue one decision per driver. A single race control message —
"TURN 17 INCIDENT INVOLVING CARS 44 (HAM) AND 55 (SAI) NOTED - CAUSING A
COLLISION" — is therefore the race control record behind two decisions, and
`race_control_messages.incident_id` could only ever name one of them. Which one
it named depended on the order the linker happened to iterate incidents in.

Measured on the corpus: **285 of 1,122 matching messages belong to more than
one incident**, so a quarter of the links were unrepresentable rather than
merely mis-assigned.

The old column is emptied rather than dropped. Nothing writes it any more and
the ORM no longer reads it, but the interim Vercel deployment does not rebuild
on push and still selects it; emptying leaves that build returning an incident
with no race control messages instead of failing outright. Drop it once the Fly
cutover is done.

Revision ID: 0018
Revises: 0017
"""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "incident_race_control",
        sa.Column(
            "incident_id",
            sa.Text(),
            sa.ForeignKey("incidents.incident_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "message_id",
            sa.Text(),
            sa.ForeignKey("race_control_messages.message_id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    # The incident side is the primary key's leading column and already indexed.
    # Going the other way — "which decisions does this message belong to" — is
    # what makes the many-to-many worth having, so index it explicitly.
    op.create_index(
        "idx_incident_rc_message",
        "incident_race_control",
        ["message_id"],
    )
    op.execute("UPDATE race_control_messages SET incident_id = NULL")


def downgrade() -> None:
    op.drop_index("idx_incident_rc_message", table_name="incident_race_control")
    op.drop_table("incident_race_control")
