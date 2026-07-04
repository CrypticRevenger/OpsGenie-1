"""add_whatsapp_reply_sent_event_type

Revision ID: ce31a2f0e816
Revises: bb45c43cbb7f
Create Date: 2026-07-04 16:50:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ce31a2f0e816"
down_revision: str | None = "bb45c43cbb7f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Autogenerate doesn't detect additions to a native Postgres enum type —
    # hand-written, same as 146a970a5954_add_whatsapp_business_event_types.py.
    op.execute("ALTER TYPE businesseventtype ADD VALUE 'whatsapp_reply_sent'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE — same rationale as
    # 146a970a5954's downgrade: additive, no-op-if-unused, not worth a full
    # type rebuild.
    pass
