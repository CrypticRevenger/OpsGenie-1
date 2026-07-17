"""add_update_gst_pending_operation_type

Revision ID: 9b2e57d1a4c8
Revises: c3f68a5d2e91
Create Date: 2026-07-17 18:04:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9b2e57d1a4c8"
down_revision: str | None = "c3f68a5d2e91"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE pendingoperationtype ADD VALUE 'update_gst'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE; removing a value means
    # rebuilding the type. No-op for an additive, no-op-if-unused migration.
    pass
