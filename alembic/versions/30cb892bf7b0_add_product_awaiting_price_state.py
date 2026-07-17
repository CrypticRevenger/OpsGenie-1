"""add_product_awaiting_price_state

Revision ID: 30cb892bf7b0
Revises: a3c7e1f92b4d
Create Date: 2026-07-17 16:18:39.138316

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "30cb892bf7b0"
down_revision: str | None = "a3c7e1f92b4d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Autogenerate doesn't detect additions to a native Postgres enum type.
    # Safe inside a transaction on Postgres 12+ as long as the new value isn't
    # also *used* in the same transaction (same pattern as the earlier
    # onboardingstate additions).
    op.execute("ALTER TYPE onboardingstate ADD VALUE 'product_awaiting_price'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE; removing a value means
    # rebuilding the type. No-op for an additive, no-op-if-unused migration.
    pass
