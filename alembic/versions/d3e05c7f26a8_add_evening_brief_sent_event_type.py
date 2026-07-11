"""add_evening_brief_sent_event_type

Revision ID: d3e05c7f26a8
Revises: c2d94b6e15f7
Create Date: 2026-07-12 01:35:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3e05c7f26a8"
down_revision: str | None = "c2d94b6e15f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Autogenerate doesn't detect additions to a native Postgres enum type —
    # hand-written, same as ce31a2f0e816_add_whatsapp_reply_sent_event_type.py.
    op.execute("ALTER TYPE businesseventtype ADD VALUE 'evening_brief_sent'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE — additive, no-op-if-unused,
    # not worth a full type rebuild.
    pass
