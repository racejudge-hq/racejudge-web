"""Initial schema — decisions, incidents, embeddings, annotation_pairs, ingested_hashes

Revision ID: 0001
Revises:
Create Date: 2026-05-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("doc_id", sa.Text(), nullable=False, unique=True),
        sa.Column("sha256_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("pdf_url", sa.Text(), nullable=False),
        sa.Column("r2_key", sa.Text()),
        sa.Column("season", sa.SmallInteger(), nullable=False),
        sa.Column("published_at", sa.Text()),
        sa.Column("raw_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("char_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("needs_ocr", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("parser_version", sa.Text(), nullable=False, server_default="v1.0-pdfplumber"),
        sa.Column("parsed_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
        sa.CheckConstraint("season >= 2018", name="decisions_season_check"),
    )
    op.create_index("idx_decisions_season", "decisions", ["season"])
    op.create_index("idx_decisions_parsed_at", "decisions", [sa.text("parsed_at DESC")])

    op.create_table(
        "incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("decision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("car_number", sa.SmallInteger()),
        sa.Column("driver_name", sa.Text()),
        sa.Column("infraction_type", sa.Text()),
        sa.Column("outcome", sa.Text()),
        sa.Column("penalty_points", sa.SmallInteger()),
        sa.Column("lap_number", sa.SmallInteger()),
        sa.Column("session_type", sa.Text()),
        sa.Column("incident_text", sa.Text()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["decision_id"], ["decisions.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_incidents_decision_id", "incidents", ["decision_id"])
    op.create_index("idx_incidents_infraction", "incidents", ["infraction_type"])
    op.create_index("idx_incidents_outcome", "incidents", ["outcome"])

    op.create_table(
        "embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("decision_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("model_version", sa.Text(), nullable=False, server_default="bge-m3-v1"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["decision_id"], ["decisions.id"], ondelete="CASCADE"),
    )
    # embedding column added separately — vector type not in core SA types
    op.execute("ALTER TABLE embeddings ADD COLUMN IF NOT EXISTS embedding vector(1024)")

    op.create_table(
        "annotation_pairs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("anchor_id", sa.Text(), nullable=False),
        sa.Column("positive_id", sa.Text()),
        sa.Column("negative_id", sa.Text()),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("annotator", sa.Text(), nullable=False, server_default="human"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
        sa.CheckConstraint("label IN ('similar', 'dissimilar')", name="annotation_pairs_label_check"),
    )

    op.create_table(
        "ingested_hashes",
        sa.Column("sha256_hash", sa.Text(), primary_key=True),
        sa.Column("ingested_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
    )


def downgrade() -> None:
    op.drop_table("ingested_hashes")
    op.drop_table("annotation_pairs")
    op.drop_table("embeddings")
    op.drop_table("incidents")
    op.drop_table("decisions")
