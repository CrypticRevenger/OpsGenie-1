"""add_dealer_direct_reminders_enabled

Adds Dealer.direct_reminders_enabled (default False) — the distributor's
per-dealer consent flag gating direct overdue-reminder delivery to that
dealer's own WhatsApp (see app/services/notifications.py's
check_dealer_overdue_alerts). Opt-in, not opt-out: no existing dealer is
retroactively enabled by this migration.

Revision ID: 23d94554f26f
Revises: cfe8f6056da3
Create Date: 2026-07-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "23d94554f26f"
down_revision: str | None = "cfe8f6056da3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "dealers",
        sa.Column("direct_reminders_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("dealers", "direct_reminders_enabled")
