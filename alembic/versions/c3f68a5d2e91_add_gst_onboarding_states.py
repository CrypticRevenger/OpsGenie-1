"""add_gst_onboarding_states

Revision ID: c3f68a5d2e91
Revises: a7d24b91c3e5
Create Date: 2026-07-17 18:03:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3f68a5d2e91"
down_revision: str | None = "a7d24b91c3e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Autogenerate doesn't detect additions to a native Postgres enum type —
    # same pattern as every earlier onboardingstate addition.
    op.execute("ALTER TYPE onboardingstate ADD VALUE 'gst_mode_ask'")
    op.execute("ALTER TYPE onboardingstate ADD VALUE 'gst_rate_same'")
    op.execute("ALTER TYPE onboardingstate ADD VALUE 'product_awaiting_gst_rate'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE; removing a value means
    # rebuilding the type. No-op for an additive, no-op-if-unused migration.
    pass
