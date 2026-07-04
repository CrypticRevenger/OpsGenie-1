"""add_founder_alert_event_type

Revision ID: d7c2e4a1b8f3
Revises: 0fa10a29543a
Create Date: 2026-07-04 19:15:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7c2e4a1b8f3"
down_revision: str | None = "0fa10a29543a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Autogenerate doesn't detect additions to a native Postgres enum type —
    # hand-written, same as 146a970a5954 / ce31a2f0e816.
    op.execute("ALTER TYPE businesseventtype ADD VALUE 'founder_alert_sent'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE — same rationale as the other
    # additive enum migrations: not worth a full type rebuild.
    pass
