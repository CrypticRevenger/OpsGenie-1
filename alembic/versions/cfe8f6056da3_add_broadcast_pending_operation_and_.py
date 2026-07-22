"""add broadcast pending-operation and business-event enum values

Adds PendingOperationType.broadcast_dealers/bulk_opt_in_dealers and
BusinessEventType.marketing_broadcast_sent — the confirm-gate and audit-trail
enum members for the marketing broadcast feature (see
app/services/writes/broadcast.py, app/services/workflows/broadcast_flow.py).

Revision ID: cfe8f6056da3
Revises: 36f4c2126db2
Create Date: 2026-07-22

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cfe8f6056da3"
down_revision: str | None = "36f4c2126db2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Autogenerate doesn't detect additions to a native Postgres enum type —
    # hand-written, per the project's migration playbook.
    op.execute("ALTER TYPE pendingoperationtype ADD VALUE IF NOT EXISTS 'broadcast_dealers'")
    op.execute("ALTER TYPE pendingoperationtype ADD VALUE IF NOT EXISTS 'bulk_opt_in_dealers'")
    op.execute("ALTER TYPE businesseventtype ADD VALUE IF NOT EXISTS 'marketing_broadcast_sent'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE — additive, no-op-if-unused,
    # not worth a full type rebuild.
    pass
