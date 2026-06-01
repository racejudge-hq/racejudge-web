"""Add incidents, drivers, teams, precedent_links, predictions_log tables.

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # drivers reference table
    # ------------------------------------------------------------------
    op.create_table(
        "drivers",
        sa.Column("driver_id", sa.Text(), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("code", sa.Text(), nullable=False, unique=True),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("abbreviation", sa.Text(), nullable=True),
        sa.Column("nationality", sa.Text(), nullable=True),
        sa.Column("number", sa.SmallInteger(), nullable=True),
        sa.Column("jolpica_id", sa.Integer(), nullable=True, unique=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )

    # ------------------------------------------------------------------
    # teams reference table
    # ------------------------------------------------------------------
    op.create_table(
        "teams",
        sa.Column("team_id", sa.Text(), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("short_name", sa.Text(), nullable=True),
        sa.Column("jolpica_id", sa.Integer(), nullable=True, unique=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )

    # ------------------------------------------------------------------
    # incidents — full Phase 2 schema
    # ------------------------------------------------------------------
    op.create_table(
        "incidents",
        sa.Column("incident_id", sa.Text(), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("doc_id", sa.Text(), nullable=False),
        sa.Column("drivers", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("session_key", sa.Integer(), nullable=True),
        sa.Column("lap", sa.SmallInteger(), nullable=True),
        sa.Column("corner", sa.Text(), nullable=True),
        sa.Column("article_cited", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("infraction_category", sa.Text(), nullable=True),
        sa.Column("penalty_type", sa.Text(), nullable=True),
        sa.Column("penalty_seconds", sa.SmallInteger(), nullable=True),
        sa.Column("penalty_points", sa.SmallInteger(), nullable=False,
                  server_default=sa.text("0")),
        sa.Column("grid_positions", sa.SmallInteger(), nullable=True),
        sa.Column("contact", sa.Boolean(), nullable=True),
        sa.Column("position_change", sa.SmallInteger(), nullable=True),
        sa.Column("reasoning_text", sa.Text(), nullable=False,
                  server_default=sa.text("''")),
        sa.Column("weather_context", postgresql.JSONB(), nullable=True),
        sa.Column("video_refs", postgresql.JSONB(), nullable=True),
        sa.Column("extractor_version", sa.Text(), nullable=False,
                  server_default=sa.text("'v1.0-regex'")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.ForeignKeyConstraint(["doc_id"], ["decisions.doc_id"],
                                name="fk_incidents_decision"),
        sa.CheckConstraint(
            "penalty_type IS NULL OR penalty_type IN "
            "('NFA','REP','5s','10s','DT','GRID','DSQ')",
            name="ck_incidents_penalty_type",
        ),
    )
    op.create_index("idx_incidents_doc_id",   "incidents", ["doc_id"])
    op.create_index("idx_incidents_penalty",   "incidents", ["penalty_type"])
    op.create_index("idx_incidents_infraction","incidents", ["infraction_category"])
    op.create_index("idx_incidents_session",   "incidents", ["session_key"])
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_incidents_article
        ON incidents USING GIN(article_cited);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_incidents_drivers
        ON incidents USING GIN(drivers);
    """)

    # ------------------------------------------------------------------
    # precedent_links
    # ------------------------------------------------------------------
    op.create_table(
        "precedent_links",
        sa.Column("incident_id", sa.Text(), nullable=False),
        sa.Column("similar_incident_id", sa.Text(), nullable=False),
        sa.Column("similarity_score", sa.Float(), nullable=False),
        sa.Column("link_type", sa.Text(), nullable=False,
                  server_default=sa.text("'semantic'")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.incident_id"]),
        sa.ForeignKeyConstraint(["similar_incident_id"], ["incidents.incident_id"]),
        sa.PrimaryKeyConstraint("incident_id", "similar_incident_id"),
    )
    op.create_index("idx_precedent_score", "precedent_links",
                    ["incident_id", "similarity_score"])

    # ------------------------------------------------------------------
    # predictions_log
    # ------------------------------------------------------------------
    op.create_table(
        "predictions_log",
        sa.Column("prediction_id", sa.Text(), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("query_features", postgresql.JSONB(), nullable=True),
        sa.Column("predicted_dist", postgresql.JSONB(), nullable=False),
        sa.Column("ground_truth", sa.Text(), nullable=True),
        sa.Column("model_version", sa.Text(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )

    # ------------------------------------------------------------------
    # steward_panels
    # ------------------------------------------------------------------
    op.create_table(
        "steward_panels",
        sa.Column("panel_id", sa.Text(), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("event_id", sa.Text(), nullable=False),
        sa.Column("chair", sa.Text(), nullable=False),
        sa.Column("members", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("driver_steward", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["event_id"], ["events.event_id"]),
    )


def downgrade() -> None:
    op.drop_table("steward_panels")
    op.drop_table("predictions_log")
    op.drop_table("precedent_links")
    op.drop_table("incidents")
    op.drop_table("teams")
    op.drop_table("drivers")
