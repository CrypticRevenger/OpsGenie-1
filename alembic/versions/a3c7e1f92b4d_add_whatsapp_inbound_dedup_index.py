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
    # The exact race this index prevents already happened in production
    # before this migration existed — the old dedup check (a plain SELECT)
    # let concurrent Meta retries slip past each other and each insert its
    # own whatsapp_message_received row for the same (company_id,
    # message_id). Those pre-existing duplicates must be collapsed before
    # the unique index can be created, or CREATE UNIQUE INDEX itself fails.
    # Keeps the earliest row per (company_id, message_id) — the one whose id
    # any whatsapp_reply_sent event's correlation_id is most likely to
    # reference — and drops the rest. Business events are otherwise
    # append-only/immutable (see app/models/business_event.py); this is a
    # one-time corrective exception, not a precedent.
    op.execute(
        """
        DELETE FROM business_events
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY company_id, (payload->>'message_id')
                           ORDER BY created_at ASC, id ASC
                       ) AS rn
                FROM business_events
                WHERE event_type = 'whatsapp_message_received'
                  AND payload->>'message_id' IS NOT NULL
            ) ranked
            WHERE rn > 1
        )
        """
    )

    # Inbound WhatsApp dedup (app/api/webhooks/whatsapp.py's
    # _find_inbound_event) was previously a plain SELECT with no DB-level
    # guarantee — two concurrent requests for the same Meta message id (e.g.
    # Meta's retries while a cold Render instance is still waking up) could
    # both pass the check before either commits, each generating and sending
    # its own reply. A partial unique index makes the second INSERT block on
    # the first (same index entry) and then fail with a real IntegrityError
    # once the first commits, so the handler can detect the race atomically
    # instead of racing on a SELECT.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_business_events_wa_inbound_msg
        ON business_events (company_id, (payload->>'message_id'))
        WHERE event_type = 'whatsapp_message_received'
        """
    )


def downgrade() -> None:
    # The DELETE above is not reversible — same convention as
    # f7a2b9d4c6e1's downgrade being a no-op for an irreversible change.
    op.execute("DROP INDEX uq_business_events_wa_inbound_msg")
