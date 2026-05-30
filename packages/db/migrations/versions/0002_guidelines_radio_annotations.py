"""Add guidelines, team_radio_clips, and annotations tables.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-30
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # guidelines
    op.create_table(
        "guidelines",
        sa.Column("article_id", sa.Text(), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("document_name", sa.Text(), nullable=False),
        sa.Column("section", sa.Text(), nullable=True),
        sa.Column("article_number", sa.Text(), nullable=False),
        sa.Column("article_text", sa.Text(), nullable=False),
        sa.Column("recommended_penalty", sa.Text(), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("document_name", "article_number",
                            name="uq_guidelines_doc_article"),
    )
    op.create_index("idx_guidelines_document", "guidelines", ["document_name"])
    op.create_index("idx_guidelines_article", "guidelines", ["article_number"])

    # team_radio_clips
    op.create_table(
        "team_radio_clips",
        sa.Column("clip_id", sa.Text(), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("session_key", sa.Integer(), nullable=False),
        sa.Column("driver_number", sa.SmallInteger(), nullable=False),
        sa.Column("date", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("recording_url", sa.Text(), nullable=False, unique=True),
        sa.Column("r2_key", sa.Text(), nullable=True),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("speaker_label", sa.Text(), nullable=True),
        sa.Column("sentiment_score", sa.Float(), nullable=True),
        sa.Column("urgency_score", sa.Float(), nullable=True),
        sa.Column("incident_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("idx_radio_session", "team_radio_clips", ["session_key"])
    op.create_index("idx_radio_driver", "team_radio_clips", ["driver_number"])
    op.create_index("idx_radio_date", "team_radio_clips", ["date"])

    # annotations
    op.create_table(
        "annotations",
        sa.Column("annotation_id", sa.Text(), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("doc_id", sa.Text(), nullable=False),
        sa.Column("annotator", sa.Text(), nullable=False, server_default="anonymous"),
        sa.Column("infraction_type", sa.Text(), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=True),
        sa.Column("penalty_class", sa.Text(), nullable=True),
        sa.Column("penalty_points", sa.SmallInteger(), nullable=True),
        sa.Column("article_cited", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("positive_doc_id", sa.Text(), nullable=True),
        sa.Column("negative_doc_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint(
            "penalty_class IN ('NFA','REP','5s','10s','DT','GRID','DSQ')",
            name="ck_annotations_penalty_class",
        ),
    )
    op.create_index("idx_annotations_doc_id", "annotations", ["doc_id"])
    op.create_index("idx_annotations_annotator", "annotations", ["annotator"])


def downgrade() -> None:
    op.drop_table("annotations")
    op.drop_table("team_radio_clips")
    op.drop_table("guidelines")
