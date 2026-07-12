"""add_whatsapp_inbound_dedup_index

Revision ID: a3c7e1f92b4d
Revises: f7a2b9d4c6e1
Create Date: 2026-07-12 19:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3c7e1f92b4d"
down_revision: str | None = "f7a2b9d4c6e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Inbound WhatsApp dedup (app/api/webhooks/whatsapp.py's
    # _already_processed) was a plain SELECT with no DB-level guarantee — two
    # concurrent requests for the same Meta message id (e.g. Meta's retries
    # while a cold Render instance is still waking up) could both pass the
    # check before either commits, each generating and sending its own reply.
    # A partial unique index makes the second INSERT block on the first (same
    # index entry) and then fail with a real IntegrityError once the first
    # commits, so the handler can detect the race atomically instead of
    # racing on a SELECT.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_business_events_wa_inbound_msg
        ON business_events (company_id, (payload->>'message_id'))
        WHERE event_type = 'whatsapp_message_received'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX uq_business_events_wa_inbound_msg")
