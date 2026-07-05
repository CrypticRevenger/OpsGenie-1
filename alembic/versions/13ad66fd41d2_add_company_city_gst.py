"""add_company_city_gst

Revision ID: 13ad66fd41d2
Revises: 209dbc094424
Create Date: 2026-07-05 22:39:00.230719

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "13ad66fd41d2"
down_revision: str | None = "209dbc094424"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("city", sa.String(), nullable=True))
    op.add_column("companies", sa.Column("gst_number", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("companies", "gst_number")
    op.drop_column("companies", "city")
