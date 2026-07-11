"""add_daily_business_snapshot

Revision ID: c2d94b6e15f7
Revises: b6f83a1d90ce
Create Date: 2026-07-12 01:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c2d94b6e15f7"
down_revision: str | None = "b6f83a1d90ce"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "companies", sa.Column("evening_brief_hour", sa.Integer(), nullable=True)
    )

    op.create_table(
        "daily_business_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("sales_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("sales_margin", sa.Numeric(14, 2), nullable=False),
        sa.Column("items_missing_cost_data", sa.Integer(), nullable=False),
        sa.Column("revenue_excluded_no_cost_data", sa.Numeric(14, 2), nullable=False),
        sa.Column("collections_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("supplier_payments_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("net_cash_movement", sa.Numeric(14, 2), nullable=False),
        sa.Column("outstanding_receivables", sa.Numeric(14, 2), nullable=False),
        sa.Column("invoices_created", sa.Integer(), nullable=False),
        sa.Column("payments_recorded", sa.Integer(), nullable=False),
        sa.Column("orders_created", sa.Integer(), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "business_date", name="uq_daily_business_snapshots_company_date"
        ),
    )


def downgrade() -> None:
    op.drop_table("daily_business_snapshots")
    op.drop_column("companies", "evening_brief_hour")
