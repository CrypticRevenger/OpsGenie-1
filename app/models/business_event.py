"""BusinessEvent ORM model — append-only event log.

Every significant state change in the system writes an immutable BusinessEvent
before returning.  This table is never updated after insert — no updated_at
column exists by design (review comment 9).

BusinessEvents are the audit trail.  They feed ActivityTimeline and are the
source of truth for what happened and when.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._mixins import UUIDMixin

if TYPE_CHECKING:
    from app.models.company import Company


class BusinessEventType(enum.StrEnum):
    """All event types that the BusinessEngine can emit."""

    invoice_created = "invoice_created"
    invoice_status_updated = "invoice_status_updated"
    payment_received = "payment_received"
    supplier_paid = "supplier_paid"
    reminder_sent = "reminder_sent"
    dealer_called = "dealer_called"
    briefing_sent = "briefing_sent"
    data_imported = "data_imported"
    follow_up_sent = "follow_up_sent"
    follow_up_responded = "follow_up_responded"
    # Phase 7 — WhatsApp inbound webhook (see app/api/webhooks/whatsapp.py).
    whatsapp_message_received = "whatsapp_message_received"
    whatsapp_status_received = "whatsapp_status_received"
    # Phase 8 — outbound reply to a numbered-menu command or unknown input.
    whatsapp_reply_sent = "whatsapp_reply_sent"
    # Phase 10 — NotificationEngine internal ops alert to the founder's number
    # (payload.reason distinguishes "stale_data" vs "briefing_failed").
    founder_alert_sent = "founder_alert_sent"


class BusinessEvent(UUIDMixin, Base):
    """An immutable record of a significant business event.

    Append-only — never updated after insert.
    """

    __tablename__ = "business_events"
    __table_args__ = (
        Index("ix_business_events_company_created", "company_id", "created_at"),
        Index("ix_business_events_company_type", "company_id", "event_type"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[BusinessEventType] = mapped_column(
        Enum(BusinessEventType, name="businesseventtype", create_constraint=True),
        nullable=False,
    )
    # Polymorphic reference — entity_type tells you which table entity_id points to.
    # Not a real FK because one column cannot reference two tables.
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Append-only: created_at is defined here directly (not via TimestampMixin)
    # to make the intent explicit.  No updated_at.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)

    # ── Relationships ────────────────────────────────────────────────────────
    company: Mapped[Company] = relationship("Company", back_populates="business_events")
