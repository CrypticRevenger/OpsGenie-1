"""add_invoice_document_sent_event_type

Revision ID: b6f83a1d90ce
Revises: a1e5c9f27d4b
Create Date: 2026-07-12 00:05:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b6f83a1d90ce"
down_revision: str | None = "a1e5c9f27d4b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Autogenerate doesn't detect additions to a native Postgres enum type —
    # hand-written, same as ce31a2f0e816_add_whatsapp_reply_sent_event_type.py.
    op.execute("ALTER TYPE businesseventtype ADD VALUE 'invoice_document_sent'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE — additive, no-op-if-unused,
    # not worth a full type rebuild.
    pass
