"""add_product_purchase_price_onboarding_states

Revision ID: e4f16d8a37b9
Revises: d3e05c7f26a8
Create Date: 2026-07-12 02:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4f16d8a37b9"
down_revision: str | None = "d3e05c7f26a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Autogenerate doesn't detect additions to a native Postgres enum type —
    # hand-written, same as 5e8b1c2d4f90_add_product_bulk_onboarding_states.py.
    op.execute("ALTER TYPE onboardingstate ADD VALUE 'product_awaiting_bulk_purchase_price'")
    op.execute("ALTER TYPE onboardingstate ADD VALUE 'product_awaiting_purchase_price'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE; removing a value means
    # rebuilding the type. No-op for an additive, no-op-if-unused migration.
    pass
