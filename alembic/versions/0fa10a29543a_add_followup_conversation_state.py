"""add_followup_conversation_state

Revision ID: 0fa10a29543a
Revises: ce31a2f0e816
Create Date: 2026-07-04 17:30:52.484140

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0fa10a29543a"
down_revision: str | None = "ce31a2f0e816"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FOLLOWUP_STATE_ENUM = sa.Enum(
    "awaiting_confirmation",
    "awaiting_partial_amount",
    "awaiting_expected_date",
    name="followupstate",
    create_constraint=True,
)


def upgrade() -> None:
    _FOLLOWUP_STATE_ENUM.create(op.get_bind(), checkfirst=True)
    op.add_column("companies", sa.Column("pending_follow_up_invoice_id", sa.Uuid(), nullable=True))
    op.add_column(
        "companies", sa.Column("pending_follow_up_state", _FOLLOWUP_STATE_ENUM, nullable=True)
    )
    op.add_column(
        "companies",
        sa.Column("pending_follow_up_created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_companies_pending_follow_up_invoice_id",
        "companies",
        "invoices",
        ["pending_follow_up_invoice_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column("invoices", sa.Column("expected_payment_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("invoices", "expected_payment_date")
    op.drop_constraint("fk_companies_pending_follow_up_invoice_id", "companies", type_="foreignkey")
    op.drop_column("companies", "pending_follow_up_created_at")
    op.drop_column("companies", "pending_follow_up_state")
    op.drop_column("companies", "pending_follow_up_invoice_id")
    sa.Enum(name="followupstate").drop(op.get_bind(), checkfirst=True)
