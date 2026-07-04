"""NotificationLog ORM model.

Records every outbound notification sent by the NotificationEngine — supplier
payment reminders, dealer overdue alerts, stale-data warnings, and briefing
delivery failures.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._mixins import UUIDMixin

if TYPE_CHECKING:
    from app.models.company import Company


class NotificationLog(UUIDMixin, Base):
    """A record of a single outbound WhatsApp notification."""

    __tablename__ = "notification_logs"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    notification_type: Mapped[str] = mapped_column(String, nullable=False)
    recipient_whatsapp: Mapped[str] = mapped_column(String, nullable=False)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    # sent_at is the canonical timestamp for this table (matches TDD spec).
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    delivery_status: Mapped[str | None] = mapped_column(String, nullable=True)
    # Meta's "wamid" for this send (Phase 8) — the correlation key a later
    # whatsapp_status_received webhook uses to update delivery_status above.
    whatsapp_message_id: Mapped[str | None] = mapped_column(String, nullable=True, unique=True)

    # ── Relationships ────────────────────────────────────────────────────────
    company: Mapped[Company] = relationship("Company", back_populates="notification_logs")
