"""add_stock_faq_and_create_order

Revision ID: 39f306e554a0
Revises: 8524a9dbfe0c
Create Date: 2026-07-06 04:10:52.902980

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "39f306e554a0"
down_revision: str | None = "8524a9dbfe0c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column(
            "stock_quantity",
            sa.Numeric(14, 4),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    op.create_table(
        "faqs",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("question", sa.String(), nullable=False),
        sa.Column("answer", sa.String(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_faqs_company_id", "faqs", ["company_id"], unique=False)

    # Autogenerate doesn't detect additions to a native Postgres enum type —
    # hand-written, per the project's own migration-playbook note. Safe inside
    # a transaction on Postgres 12+ (this project runs 16), as long as the new
    # value isn't also *used* within the same transaction.
    op.execute("ALTER TYPE pendingoperationtype ADD VALUE 'create_order'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE — see the same note in
    # 146a970a5954_add_whatsapp_business_event_types.py. No-op: safe because
    # nothing will have written rows using 'create_order' before this
    # migration ever ran.

    op.drop_index("ix_faqs_company_id", table_name="faqs")
    op.drop_table("faqs")

    op.drop_column("products", "stock_quantity")
