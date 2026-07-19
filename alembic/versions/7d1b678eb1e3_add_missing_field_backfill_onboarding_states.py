"""add missing-field backfill onboarding states (GST + dealer/supplier phone/credit)

Adds the states behind the import-path "only ask for what's missing" feature:
gst_missing_rate_ask (some, not all, imported products lack a GST rate), and the
dealer_missing_*/supplier_missing_* set (imported dealers/suppliers with only a
name, no phone/credit days — ask/mode/bulk/phone/credit, mirrored for both
parties). See app/services/onboarding_flow.py.

Revision ID: 7d1b678eb1e3
Revises: a1c4e8d05b7f
Create Date: 2026-07-20

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7d1b678eb1e3"
down_revision: str | None = "a1c4e8d05b7f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_STATES = (
    "gst_missing_rate_ask",
    "dealer_missing_ask",
    "dealer_missing_mode",
    "dealer_missing_bulk",
    "dealer_missing_phone",
    "dealer_missing_credit",
    "supplier_missing_ask",
    "supplier_missing_mode",
    "supplier_missing_bulk",
    "supplier_missing_phone",
    "supplier_missing_credit",
)


def upgrade() -> None:
    # Autogenerate doesn't detect additions to a native Postgres enum type —
    # same pattern as every earlier onboardingstate addition.
    for state in _NEW_STATES:
        op.execute(f"ALTER TYPE onboardingstate ADD VALUE IF NOT EXISTS '{state}'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE; removing a value means
    # rebuilding the type. No-op for an additive, no-op-if-unused migration.
    pass
