"""add bulk dealer/supplier onboarding states + new-party confirmation states

Adds the dealer/supplier equivalents of product_awaiting_mode/
product_awaiting_bulk (bulk-vs-one-by-one entry for dealers and suppliers,
see app/services/onboarding_flow.py), plus receivable/payable
new-party-confirmation states (asked when a receivable/payable's party name
matches no existing dealer/supplier, before silently creating one).

Revision ID: b1c4d8f27a53
Revises: a7f3e21c9b40
Create Date: 2026-07-19

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1c4d8f27a53"
down_revision: str | None = "a7f3e21c9b40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Autogenerate doesn't detect additions to a native Postgres enum type —
    # hand-written, per the project's migration playbook (see e.g.
    # 5e8b1c2d4f90_add_product_bulk_onboarding_states.py).
    op.execute("ALTER TYPE onboardingstate ADD VALUE IF NOT EXISTS 'dealer_awaiting_mode'")
    op.execute("ALTER TYPE onboardingstate ADD VALUE IF NOT EXISTS 'dealer_awaiting_bulk'")
    op.execute("ALTER TYPE onboardingstate ADD VALUE IF NOT EXISTS 'supplier_awaiting_mode'")
    op.execute("ALTER TYPE onboardingstate ADD VALUE IF NOT EXISTS 'supplier_awaiting_bulk'")
    op.execute(
        "ALTER TYPE onboardingstate ADD VALUE IF NOT EXISTS 'receivable_new_party_confirm'"
    )
    op.execute("ALTER TYPE onboardingstate ADD VALUE IF NOT EXISTS 'payable_new_party_confirm'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE; removing a value means
    # rebuilding the type. No-op for an additive, no-op-if-unused migration.
    pass
