"""De-duplicate race_control_messages and stop it happening again. Migration 0019.

`fetch_and_store_rc_messages` skipped a message it already held by building a
key from `str(row.date)` on one side and OpenF1's raw `date` string on the
other. The stored value renders as "2024-05-26 14:30:00+00:00" and OpenF1 sends
"2024-05-26T14:30:00+00:00", so the key never matched and every re-run of
`scripts/backfill_race_control.py` inserted the whole session again.

The linker code is fixed, but nothing in the schema said the row was supposed
to be unique, so the next writer could reintroduce it. This deletes the
surplus copies — keeping the lowest `message_id` of each group, so the
`incident_race_control` rows pointing at the copies cascade away and are then
rebuilt by the linker — and adds the constraint that should have been there.

Revision ID: 0019
Revises: 0018
"""

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DELETE FROM race_control_messages
        WHERE message_id NOT IN (
            SELECT min(message_id) FROM race_control_messages
            GROUP BY session_key, date, message
        )
    """)
    op.create_unique_constraint(
        "uq_rcm_session_date_message",
        "race_control_messages",
        ["session_key", "date", "message"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_rcm_session_date_message", "race_control_messages", type_="unique"
    )
