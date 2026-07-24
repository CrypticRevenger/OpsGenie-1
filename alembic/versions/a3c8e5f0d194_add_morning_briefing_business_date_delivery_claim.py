"""add_morning_briefing_business_date_delivery_claim

Adds MorningBriefing.business_date (nullable) + a unique (company_id,
business_date) constraint, and MorningBriefing.delivery_claimed_at (nullable)
— the same atomic-claim shape migration f11d12d60382 added to
DailyBusinessSnapshot.delivered_at for the evening brief, applied here to the
morning briefing.

Why: generate_briefing's only race guard was "read latest_briefing_today,
then decide, then generate+INSERT" — and MorningBriefing had no unique
constraint at all, so two genuinely concurrent callers could each pass the
check and insert a real duplicate row (a second real LLM call and a second
real WhatsApp send). Unlike the evening brief, this can happen without any
scheduler overlap: app/api/admin/briefing.py's POST /briefing and
app/api/webhooks/whatsapp.py's on-demand "give me my briefing" reply both
call generate_briefing() directly, with no lock of any kind — either one
racing the scheduler's own tick (or each other) hits the exact same gap.
business_date turns "has today's briefing been claimed" into a single
atomic INSERT against a real unique constraint. delivery_claimed_at gives
the send step (app/core/scheduler.py::_deliver_briefing) the same
delivered_at-style atomic claim the evening brief already has, closing the
narrower "two overlapping ticks" send-side race too.

Revision ID: a3c8e5f0d194
Revises: f11d12d60382
Create Date: 2026-07-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3c8e5f0d194"
down_revision: str | None = "f11d12d60382"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "morning_briefings",
        sa.Column("business_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "morning_briefings",
        sa.Column("delivery_claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint(
        "uq_morning_briefings_company_business_date",
        "morning_briefings",
        ["company_id", "business_date"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_morning_briefings_company_business_date",
        "morning_briefings",
        type_="unique",
    )
    op.drop_column("morning_briefings", "delivery_claimed_at")
    op.drop_column("morning_briefings", "business_date")
