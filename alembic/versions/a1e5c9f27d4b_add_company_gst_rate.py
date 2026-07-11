"""add_company_gst_rate

Revision ID: a1e5c9f27d4b
Revises: 7f2a4c9e1b3d
Create Date: 2026-07-12 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1e5c9f27d4b"
down_revision: str | None = "7f2a4c9e1b3d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column("gst_rate", sa.Numeric(5, 2), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("companies", "gst_rate")
