"""add_export_downloaded_event_type

Revision ID: f7a2b9d4c6e1
Revises: e4f16d8a37b9
Create Date: 2026-07-12 03:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f7a2b9d4c6e1"
down_revision: str | None = "e4f16d8a37b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Autogenerate doesn't detect additions to a native Postgres enum type —
    # hand-written, same as ce31a2f0e816_add_whatsapp_reply_sent_event_type.py.
    op.execute("ALTER TYPE businesseventtype ADD VALUE 'export_downloaded'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE — additive, no-op-if-unused,
    # not worth a full type rebuild.
    pass
