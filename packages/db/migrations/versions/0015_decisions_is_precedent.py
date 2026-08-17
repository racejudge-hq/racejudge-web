"""Mark which documents are stewards' rulings and so usable as precedent.

Migration 015.

The corpus is not all rulings. 245 of 1,606 documents are administrative
sheets the FIA publishes through the same feed: power-unit element tallies,
RNC tallies, drivers' meeting notes, scrutineering reports. They argue nothing
and decide nothing, and returning them from a precedent search is a wrong
answer, not a weak one.

The signal is the signature block. A ruling is signed by the steward panel;
an administrative sheet is signed by a single delegate ("Jo Bauer / The FIA
Formula One Technical Delegate"). Two independent checks agree exactly on the
split: all 1,206 documents that carry a Decision section are panel-signed, and
not one document has a Decision section without a panel.

The obvious-looking filter — infraction_category IS NULL — is wrong and was
rejected. 425 incidents have no category, but 249 of them are genuine rulings
whose category the extractor could not name: a disqualification for physical
assistance, several fines, a 5-second penalty from a Right of Review. Dropping
those would lose real precedent.

Nullable rather than defaulting to false: a document whose signature block has
not been read yet is unknown, not administrative. Retrieval filters on
IS NOT FALSE, so an unread document stays in the corpus. Excluding is the
destructive direction and must be something we positively determined.

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "decisions", sa.Column("is_precedent", sa.Boolean(), nullable=True)
    )
    # Retrieval filters on this on every query, alongside the vector scan.
    op.create_index("idx_decisions_is_precedent", "decisions", ["is_precedent"])


def downgrade() -> None:
    op.drop_index("idx_decisions_is_precedent", table_name="decisions")
    op.drop_column("decisions", "is_precedent")
