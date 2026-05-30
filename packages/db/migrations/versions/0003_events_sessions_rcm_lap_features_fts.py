"""Add events, sessions, race_control_messages, lap_features, and FTS index.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-30
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # events
    # ------------------------------------------------------------------
    op.create_table(
        "events",
        sa.Column("event_id", sa.Text(), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("season", sa.SmallInteger(), nullable=False),
        sa.Column("round_number", sa.SmallInteger(), nullable=False),
        sa.Column("circuit", sa.Text(), nullable=False),
        sa.Column("country", sa.Text(), nullable=False),
        sa.Column("event_name", sa.Text(), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=True),
        sa.Column("openf1_meeting_key", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint("season >= 2018", name="ck_events_season"),
        sa.UniqueConstraint("season", "round_number", name="uq_events_season_round"),
    )
    op.create_index("idx_events_season", "events", ["season"])

    # ------------------------------------------------------------------
    # sessions
    # ------------------------------------------------------------------
    op.create_table(
        "sessions",
        sa.Column("session_id", sa.Text(), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("event_id", sa.Text(), nullable=False),
        sa.Column("session_type", sa.Text(), nullable=False),
        sa.Column("session_key", sa.Integer(), nullable=True, unique=True),
        sa.Column("start_time", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("end_time", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.event_id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "session_type IN ('practice_1','practice_2','practice_3',"
            "'qualifying','sprint_qualifying','sprint','race')",
            name="ck_sessions_type",
        ),
    )
    op.create_index("idx_sessions_event_id",    "sessions", ["event_id"])
    op.create_index("idx_sessions_session_key", "sessions", ["session_key"])

    # ------------------------------------------------------------------
    # race_control_messages
    # ------------------------------------------------------------------
    op.create_table(
        "race_control_messages",
        sa.Column("message_id", sa.Text(), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("session_key", sa.Integer(), nullable=False),
        sa.Column("date", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("flag", sa.Text(), nullable=True),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("sector", sa.SmallInteger(), nullable=True),
        sa.Column("driver_number", sa.SmallInteger(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("idx_rcm_session_key", "race_control_messages", ["session_key"])
    op.create_index("idx_rcm_date",        "race_control_messages", ["date"])
    op.create_index("idx_rcm_category",    "race_control_messages", ["category"])

    # ------------------------------------------------------------------
    # lap_features
    # ------------------------------------------------------------------
    op.create_table(
        "lap_features",
        sa.Column("id", sa.Text(), nullable=False,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("time", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("session_key", sa.Integer(), nullable=False),
        sa.Column("driver_number", sa.SmallInteger(), nullable=False),
        sa.Column("lap_number", sa.SmallInteger(), nullable=False),
        sa.Column("lap_time_ms", sa.Integer(), nullable=True),
        sa.Column("sector1_ms", sa.Integer(), nullable=True),
        sa.Column("sector2_ms", sa.Integer(), nullable=True),
        sa.Column("sector3_ms", sa.Integer(), nullable=True),
        sa.Column("speed_i1", sa.Float(), nullable=True),
        sa.Column("speed_i2", sa.Float(), nullable=True),
        sa.Column("speed_fl", sa.Float(), nullable=True),
        sa.Column("speed_st", sa.Float(), nullable=True),
        sa.Column("compound", sa.Text(), nullable=True),
        sa.Column("tyre_life_laps", sa.SmallInteger(), nullable=True),
        sa.Column("is_personal_best", sa.Boolean(), nullable=False,
                  server_default=sa.text("FALSE")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id", "time"),
    )
    op.create_index("idx_lap_features_session", "lap_features",
                    ["session_key", "driver_number"])
    op.create_index("idx_lap_features_time", "lap_features", ["time"])

    # Promote to TimescaleDB hypertable (no-op if TimescaleDB not installed)
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'
            ) THEN
                PERFORM create_hypertable(
                    'lap_features', 'time',
                    if_not_exists => TRUE,
                    migrate_data  => TRUE
                );
            END IF;
        END $$;
    """)

    # ------------------------------------------------------------------
    # Full-text search column + GIN index on decisions
    # ------------------------------------------------------------------
    op.execute("""
        ALTER TABLE decisions
            ADD COLUMN IF NOT EXISTS search_vector tsvector
            GENERATED ALWAYS AS (
                setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
                setweight(to_tsvector('english', coalesce(raw_text, '')), 'B')
            ) STORED;
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_decisions_fts
            ON decisions USING gin(search_vector);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_decisions_fts;")
    op.execute("ALTER TABLE decisions DROP COLUMN IF EXISTS search_vector;")
    op.drop_table("lap_features")
    op.drop_table("race_control_messages")
    op.drop_table("sessions")
    op.drop_table("events")
