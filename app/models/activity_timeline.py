"""ActivityTimeline ORM model — append-only per-entity event history.

Provides fast per-dealer and per-supplier event history used by the
RecommendationEngine to avoid surfacing actions that were recently taken.

Append-only — no updated_at by design (review comment 9).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._mixins import UUIDMixin
from app.models._types import Money

if TYPE_CHECKING:
    from app.models.company import Company


class ActivityEntityType(enum.StrEnum):
    """The type of entity this timeline entry refers to."""

    dealer = "dealer"
    supplier = "supplier"
    # Proactive stock-out forecast dedup key — see
    # app/services/notifications.py::check_stock_out_forecasts.
    product = "product"


class ActivityEventType(enum.StrEnum):
    """The type of activity recorded on the timeline."""

    invoice_created = "invoice_created"
    payment_received = "payment_received"
    reminder_sent = "reminder_sent"
    dealer_called = "dealer_called"
    briefing_mentioned = "briefing_mentioned"
    overdue_flagged = "overdue_flagged"
    follow_up_sent = "follow_up_sent"
    follow_up_responded = "follow_up_responded"
    # Proactive early-warning alerts — see app/services/notifications.py.
    stock_out_forecast_sent = "stock_out_forecast_sent"
    predue_nudge_sent = "predue_nudge_sent"


class ActivityTimeline(UUIDMixin, Base):
    """An immutable entry in a dealer's or supplier's activity history.

    Append-only — never updated after insert.
    """

    __tablename__ = "activity_timelines"
    __table_args__ = (
        Index(
            "ix_activity_timelines_company_entity",
            "company_id",
            "entity_type",
            "entity_id",
        ),
        Index("ix_activity_timelines_company_timestamp", "company_id", "event_timestamp"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_type: Mapped[ActivityEntityType] = mapped_column(
        Enum(ActivityEntityType, name="activityentitytype", create_constraint=True),
        nullable=False,
    )
    # Polymorphic UUID — points to dealers.id or suppliers.id depending on entity_type.
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    event_type: Mapped[ActivityEventType] = mapped_column(
        Enum(ActivityEventType, name="activityeventtype", create_constraint=True),
        nullable=False,
    )
    amount: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # event_timestamp is the canonical timestamp for this table (matches TDD spec).
    # Append-only: no updated_at.
    event_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # ── Relationships ────────────────────────────────────────────────────────
    company: Mapped[Company] = relationship("Company", back_populates="activity_timelines")
