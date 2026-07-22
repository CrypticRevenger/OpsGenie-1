"""add_dealer_marketing_opt_in

Adds Dealer.marketing_opt_in (default False) — the consent flag gating the
marketing broadcast feature (see app/services/writes/broadcast.py). Opt-in,
not opt-out: no existing dealer is retroactively consented by this migration.

Revision ID: 36f4c2126db2
Revises: e2a5f8c14d76
Create Date: 2026-07-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "36f4c2126db2"
down_revision: str | None = "e2a5f8c14d76"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "dealers",
        sa.Column("marketing_opt_in", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("dealers", "marketing_opt_in")
