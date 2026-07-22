"""add_notification_log_batch_id

Adds NotificationLog.batch_id (nullable, indexed) — groups the rows written by
one multi-recipient send so a partially-completed marketing broadcast can be
resumed instead of re-sent.

Why it's needed: app/services/writes/broadcast.py commits after every
recipient (so the audit trail survives a mid-loop failure), but the
PendingOperation delete and the webhook's reply event commit only at the end of
the request. If that final commit fails, Meta redelivers the inbound message,
the still-present PendingOperation re-executes, and every dealer receives the
broadcast a second time. batch_id carries the PendingOperation id — stable
across exactly that redelivery — so the send loop can skip recipients already
logged for it.

Nullable with no backfill: every existing row is a single-recipient
notification that was never part of a batch.

Revision ID: b7c1e9d43a52
Revises: 23d94554f26f
Create Date: 2026-07-23

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7c1e9d43a52"
down_revision: str | None = "23d94554f26f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "notification_logs",
        sa.Column("batch_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_notification_logs_batch_id",
        "notification_logs",
        ["batch_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_notification_logs_batch_id", table_name="notification_logs")
    op.drop_column("notification_logs", "batch_id")
