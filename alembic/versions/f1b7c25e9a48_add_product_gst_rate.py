"""add_product_gst_rate

Revision ID: f1b7c25e9a48
Revises: d8e1a4c93f26
Create Date: 2026-07-17 18:01:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1b7c25e9a48"
down_revision: str | None = "d8e1a4c93f26"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable — NULL means "no override, inherit Company.gst_rate", unlike
    # companies.gst_rate which is non-nullable with a 0 default.
    op.add_column(
        "products",
        sa.Column("gst_rate", sa.Numeric(5, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("products", "gst_rate")
