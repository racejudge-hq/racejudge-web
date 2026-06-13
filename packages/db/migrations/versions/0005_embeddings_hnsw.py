"""Add embedding vector column + HNSW index to incidents. Migration 005.

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-30
"""

from __future__ import annotations

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure pgvector extension is enabled
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # Add embedding column to incidents (1024-dim BGE-M3)
    op.execute("""
        ALTER TABLE incidents
            ADD COLUMN IF NOT EXISTS embedding vector(1024);
    """)

    # HNSW index for approximate nearest-neighbour search
    # m=16, ef_construction=200 per implementation plan
    # Plain CREATE INDEX: CONCURRENTLY cannot run inside Alembic's transaction,
    # and the table is empty at migration time anyway.
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_incidents_embedding
        ON incidents USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 200);
    """)

    # IVFFlat as fallback index (faster build, slightly lower recall)
    # Disabled by default — uncomment if HNSW build is too slow on first run
    # op.execute("""
    #     CREATE INDEX IF NOT EXISTS idx_incidents_embedding_ivf
    #     ON incidents USING ivfflat (embedding vector_cosine_ops)
    #     WITH (lists = 100);
    # """)

    # Add embedding metadata columns
    op.execute("""
        ALTER TABLE incidents
            ADD COLUMN IF NOT EXISTS embedding_model TEXT DEFAULT 'bge-m3-v1',
            ADD COLUMN IF NOT EXISTS embedded_at TIMESTAMPTZ;
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_incidents_embedding;")
    op.execute("ALTER TABLE incidents DROP COLUMN IF EXISTS embedding;")
    op.execute("ALTER TABLE incidents DROP COLUMN IF EXISTS embedding_model;")
    op.execute("ALTER TABLE incidents DROP COLUMN IF EXISTS embedded_at;")
