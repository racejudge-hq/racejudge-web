"""Point incidents.session_key at a real session.

The column has been a bare integer since 0001, and the sessions table it names
was never populated, so for the whole life of the schema it referenced nothing.
When sessions was finally loaded, 23 incidents from the 2026 Canadian Grand
Prix turned out to be pointing at the 2025 Canadian Grand Prix's sessions — an
earlier backfill had matched on the circuit and taken the wrong year, and
nothing in the database could tell.

The foreign key makes that class of mistake fail at write time instead of
sitting in the data. ON DELETE SET NULL, not CASCADE: if a session row goes
away the incident is still a real ruling, it just loses its timing context.

Revision ID: 0016
Revises: 0015
"""

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Anything still dangling would block the constraint. Nothing should be —
    # the backfill left zero — but a key that names no session is not a fact
    # worth keeping, so clear it rather than fail.
    op.execute("""
        UPDATE incidents i SET session_key = NULL
        WHERE i.session_key IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM sessions s WHERE s.session_key = i.session_key
          )
    """)
    op.create_foreign_key(
        "fk_incidents_session_key",
        "incidents", "sessions",
        ["session_key"], ["session_key"],
        ondelete="SET NULL",
    )
    op.create_index("idx_incidents_session_key", "incidents", ["session_key"])


def downgrade() -> None:
    op.drop_index("idx_incidents_session_key", table_name="incidents")
    op.drop_constraint("fk_incidents_session_key", "incidents", type_="foreignkey")
