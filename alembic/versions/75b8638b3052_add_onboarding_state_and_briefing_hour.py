"""add_onboarding_state_and_briefing_hour

Revision ID: 75b8638b3052
Revises: d7c2e4a1b8f3
Create Date: 2026-07-05 03:48:46.244894

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "75b8638b3052"
down_revision: str | None = "d7c2e4a1b8f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ONBOARDING_STATE = sa.Enum(
    "not_started",
    "awaiting_business_type",
    "product_awaiting_name",
    "dealer_awaiting_name",
    "dealer_awaiting_phone",
    "dealer_awaiting_credit",
    "supplier_awaiting_name",
    "supplier_awaiting_phone",
    "supplier_awaiting_credit",
    "awaiting_opening_balance",
    "receivable_ask",
    "receivable_dealer",
    "receivable_amount",
    "receivable_date",
    "payable_ask",
    "payable_supplier",
    "payable_amount",
    "payable_date",
    "awaiting_briefing_hour",
    "completed",
    name="onboardingstate",
    create_constraint=True,
)


def upgrade() -> None:
    # Create the native enum type explicitly before it's referenced by the
    # column add (same pattern as the followupstate migration).
    _ONBOARDING_STATE.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "companies",
        sa.Column(
            "onboarding_state", _ONBOARDING_STATE, server_default="completed", nullable=False
        ),
    )
    op.add_column(
        "companies",
        sa.Column("onboarding_scratch", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("companies", sa.Column("briefing_hour", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("companies", "briefing_hour")
    op.drop_column("companies", "onboarding_scratch")
    op.drop_column("companies", "onboarding_state")
    sa.Enum(name="onboardingstate").drop(op.get_bind(), checkfirst=True)
