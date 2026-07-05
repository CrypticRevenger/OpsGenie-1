"""add_awaiting_language_onboarding_state

Revision ID: 209dbc094424
Revises: 31af3de3158a
Create Date: 2026-07-05 18:39:56.740704

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "209dbc094424"
down_revision: str | None = "31af3de3158a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Autogenerate doesn't detect additions to a native Postgres enum type.
    # Safe inside a transaction on Postgres 12+ as long as the new value isn't
    # also *used* in the same transaction (same pattern as the businesseventtype
    # additions). Ordering in the enum doesn't matter for correctness.
    op.execute("ALTER TYPE onboardingstate ADD VALUE 'awaiting_language'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE; removing a value means
    # rebuilding the type. No-op for an additive, no-op-if-unused migration.
    pass
