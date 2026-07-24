"""add_company_dealer_self_service_enabled

Adds Company.dealer_self_service_enabled (default False) — the founder's
opt-in to let a dealer text the company's own WhatsApp number directly and
get back their own outstanding balance / next due date / last payment (see
app/services/dealer_self_service.py). Opt-in, not opt-out, same precedent as
Dealer.marketing_opt_in/direct_reminders_enabled: no existing company is
retroactively exposed to inbound dealer queries by this migration.

Revision ID: 1fa7b5337be0
Revises: b7c1e9d43a52
Create Date: 2026-07-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1fa7b5337be0"
down_revision: str | None = "b7c1e9d43a52"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column(
            "dealer_self_service_enabled", sa.Boolean(), nullable=False, server_default="false"
        ),
    )


def downgrade() -> None:
    op.drop_column("companies", "dealer_self_service_enabled")
