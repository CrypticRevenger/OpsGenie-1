"""add_import_confirm_onboarding_state

Revision ID: a1c4e8d05b7f
Revises: f3a9c1d7b268
Create Date: 2026-07-19 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1c4e8d05b7f"
down_revision: str | None = "f3a9c1d7b268"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Autogenerate doesn't detect additions to a native Postgres enum type —
    # same pattern as every earlier onboardingstate addition.
    op.execute("ALTER TYPE onboardingstate ADD VALUE 'import_confirm'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE; removing a value means
    # rebuilding the type. No-op for an additive, no-op-if-unused migration.
    pass
