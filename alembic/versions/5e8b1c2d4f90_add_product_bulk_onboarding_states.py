"""add_product_bulk_onboarding_states

Revision ID: 5e8b1c2d4f90
Revises: 4a7c1d6e9f21
Create Date: 2026-07-10 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5e8b1c2d4f90"
down_revision: str | None = "4a7c1d6e9f21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Autogenerate doesn't detect additions to a native Postgres enum type.
    # Safe inside a transaction on Postgres 12+ as long as the new value isn't
    # also *used* in the same transaction (same pattern as the
    # product_awaiting_quantity/awaiting_language additions).
    op.execute("ALTER TYPE onboardingstate ADD VALUE 'product_awaiting_mode'")
    op.execute("ALTER TYPE onboardingstate ADD VALUE 'product_awaiting_bulk'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE; removing a value means
    # rebuilding the type. No-op for an additive, no-op-if-unused migration.
    pass
