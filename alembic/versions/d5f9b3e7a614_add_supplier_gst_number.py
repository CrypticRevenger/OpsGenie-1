"""add_supplier_gst_number

Supplier had no GSTIN column (Dealer already does) — needed so the new
edit-supplier WhatsApp workflow can collect/edit it symmetrically with
edit-dealer.

Revision ID: d5f9b3e7a614
Revises: c4e8a1d5f293
Create Date: 2026-07-19

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5f9b3e7a614"
down_revision: str | None = "c4e8a1d5f293"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("suppliers", sa.Column("gst_number", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("suppliers", "gst_number")
