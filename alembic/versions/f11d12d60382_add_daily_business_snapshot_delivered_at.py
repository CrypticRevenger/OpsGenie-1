"""add_daily_business_snapshot_delivered_at

Adds DailyBusinessSnapshot.delivered_at (nullable) — an atomic claim marker
for the evening WhatsApp brief, closing a real production bug: three
duplicate evening briefs sent minutes apart to the same distributor.

Why: send_evening_brief's only race guard was a "read NotificationLog, then
decide, then send" check plus a session-scoped Postgres advisory lock around
the whole scheduler tick (app/core/scheduler.py::run_scheduled_tick). That
lock protects against two tick *invocations* racing each other, but not
against any other path to genuine concurrent execution, and a plain
check-then-act has an inherent race window regardless. This column turns
"has today's brief been claimed for delivery" into a single atomic
conditional UPDATE (WHERE delivered_at IS NULL) against the row's existing
unique (company_id, business_date) constraint — Postgres's own row lock
serializes two overlapping attempts, which a session-scoped advisory lock
cannot guarantee under every possible connection-pooling configuration.
Mirrors the same atomic-claim shape app/services/followup.py::
send_due_today_follow_up already uses for its own single-slot pointer.

Revision ID: f11d12d60382
Revises: 1fa7b5337be0
Create Date: 2026-07-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f11d12d60382"
down_revision: str | None = "1fa7b5337be0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "daily_business_snapshots",
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("daily_business_snapshots", "delivered_at")
