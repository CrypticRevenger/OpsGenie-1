"""add_invoice_item_gst_fields

Revision ID: a7d24b91c3e5
Revises: f1b7c25e9a48
Create Date: 2026-07-17 18:02:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7d24b91c3e5"
down_revision: str | None = "f1b7c25e9a48"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Snapshot of the rate/amount actually applied to this line at invoice
    # time — never rewritten by a later change to the product's or company's
    # gst_rate, so historical invoices stay accurate. server_default "0"
    # backfills existing rows (which predate per-line GST) as untaxed.
    op.add_column(
        "invoice_items",
        sa.Column("gst_rate", sa.Numeric(5, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "invoice_items",
        sa.Column("gst_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("invoice_items", "gst_amount")
    op.drop_column("invoice_items", "gst_rate")
