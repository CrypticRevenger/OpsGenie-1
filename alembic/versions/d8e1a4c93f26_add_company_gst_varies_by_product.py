"""add_company_gst_varies_by_product

Revision ID: d8e1a4c93f26
Revises: 30cb892bf7b0
Create Date: 2026-07-17 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8e1a4c93f26"
down_revision: str | None = "30cb892bf7b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column(
            "gst_varies_by_product", sa.Boolean(), nullable=False, server_default="false"
        ),
    )


def downgrade() -> None:
    op.drop_column("companies", "gst_varies_by_product")
