"""add_whatsapp_business_event_types

Revision ID: 146a970a5954
Revises: 783d8c755929
Create Date: 2026-07-04 03:44:08.431653

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "146a970a5954"
down_revision: str | None = "783d8c755929"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Autogenerate doesn't detect additions to a native Postgres enum type —
    # hand-written, per the project's own migration-playbook note. Safe
    # inside a transaction on Postgres 12+ (this project runs 16), as long as
    # the new value isn't also *used* within the same transaction.
    op.execute("ALTER TYPE businesseventtype ADD VALUE 'whatsapp_message_received'")
    op.execute("ALTER TYPE businesseventtype ADD VALUE 'whatsapp_status_received'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE. Removing an enum value
    # requires rebuilding the type (rename old, create new, cast every
    # column, drop old) — not worth it for an additive, no-op-if-unused
    # migration. No-op: safe because nothing will have written rows using
    # these values before this migration ever ran.
    pass
