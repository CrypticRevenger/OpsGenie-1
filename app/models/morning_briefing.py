"""MorningBriefing ORM model.

Stores every generated briefing with its full snapshot payload for auditability.
Every number in a delivered briefing must trace back to this record.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._mixins import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.company import Company


class MorningBriefing(UUIDMixin, TimestampMixin, Base):
    """A generated morning briefing delivered to a distributor.

    created_at (via TimestampMixin) added in Phase 5B: sent_at was meant to be
    the primary timestamp per the original TDD, but stays None until a
    delivery layer exists (not built yet — no WhatsApp integration). Without
    it there was no way to order "most recent" for the read endpoint. The
    Phase 1 audit already flagged this as safe to add later "without
    consequence" once querying by creation time became necessary.
    """

    __tablename__ = "morning_briefings"
    __table_args__ = (
        Index("ix_morning_briefings_company_sent", "company_id", "sent_at"),
        # Atomic generation claim (see app/services/briefing.py::generate_briefing) —
        # closes a real duplicate-send race: generate_briefing used to be a plain
        # "read latest_briefing_today, then decide, then INSERT" with no unique
        # constraint backing it, and it's reachable from three independent,
        # mostly-unlocked callers (the scheduler tick, the admin POST /briefing
        # endpoint, and the webhook's on-demand "give me my briefing" reply).
        # NULL business_date (pre-migration rows) never collides — Postgres
        # treats every NULL as distinct under a unique constraint.
        UniqueConstraint(
            "company_id", "business_date", name="uq_morning_briefings_company_business_date"
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    generated_text: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Numeric(5, 2) — values like 94.50 representing 94.5% confidence.
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    data_freshness_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivery_status: Mapped[str | None] = mapped_column(String, nullable=True)
    # Business-local date this briefing was generated for — the unique-constraint
    # anchor for the atomic generation claim above. Set once at creation time in
    # generate_briefing, never changed afterward.
    business_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Atomic delivery claim, same shape as DailyBusinessSnapshot.delivered_at
    # (see app/services/evening_brief.py) — closes the send-side race (two
    # overlapping scheduler ticks both delivering the same generated row).
    # Set immediately before the real WhatsApp send is attempted, released
    # back to NULL if that attempt's send then fails so a later tick can retry.
    delivery_claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Relationships ────────────────────────────────────────────────────────
    company: Mapped[Company] = relationship("Company", back_populates="morning_briefings")
