"""MorningBriefing ORM model.

Stores every generated briefing with its full snapshot payload for auditability.
Every number in a delivered briefing must trace back to this record.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, Uuid
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
    __table_args__ = (Index("ix_morning_briefings_company_sent", "company_id", "sent_at"),)

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

    # ── Relationships ────────────────────────────────────────────────────────
    company: Mapped[Company] = relationship("Company", back_populates="morning_briefings")
