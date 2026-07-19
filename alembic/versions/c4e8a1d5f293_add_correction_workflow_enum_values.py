"""add correction-workflow enum values (void, edit, party-edit, stock-take)

Adds the PendingOperationType and BusinessEventType members needed for the
four new correction/edit guided workflows: undo/void a payment or order,
edit an invoice/payment (safe cases only), edit a dealer/supplier's details,
and bulk stock-take. Batched into one migration since they land together,
same convention as b1c4d8f27a53.

Revision ID: c4e8a1d5f293
Revises: b1c4d8f27a53
Create Date: 2026-07-19

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4e8a1d5f293"
down_revision: str | None = "b1c4d8f27a53"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Autogenerate doesn't detect additions to a native Postgres enum type —
    # hand-written, per the project's migration playbook.
    op.execute("ALTER TYPE pendingoperationtype ADD VALUE IF NOT EXISTS 'void_payment'")
    op.execute("ALTER TYPE pendingoperationtype ADD VALUE IF NOT EXISTS 'void_order'")
    op.execute("ALTER TYPE pendingoperationtype ADD VALUE IF NOT EXISTS 'edit_invoice'")
    op.execute("ALTER TYPE pendingoperationtype ADD VALUE IF NOT EXISTS 'edit_payment'")
    op.execute("ALTER TYPE businesseventtype ADD VALUE IF NOT EXISTS 'payment_voided'")
    op.execute("ALTER TYPE businesseventtype ADD VALUE IF NOT EXISTS 'invoice_voided'")
    op.execute("ALTER TYPE businesseventtype ADD VALUE IF NOT EXISTS 'invoice_edited'")
    op.execute("ALTER TYPE businesseventtype ADD VALUE IF NOT EXISTS 'payment_edited'")
    op.execute("ALTER TYPE businesseventtype ADD VALUE IF NOT EXISTS 'party_edited'")
    op.execute("ALTER TYPE businesseventtype ADD VALUE IF NOT EXISTS 'stock_adjusted'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE — additive, no-op-if-unused,
    # not worth a full type rebuild.
    pass
