"""Dealer ORM model.

A Dealer is a customer of the distributor — someone who buys from the company
and whose outstanding receivables are tracked by OpsGenie.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._mixins import TimestampMixin, UUIDMixin
from app.models._types import Money

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.invoice import Invoice


class Dealer(UUIDMixin, TimestampMixin, Base):
    """A dealer (customer) who buys from the distributor."""

    __tablename__ = "dealers"
    __table_args__ = (Index("ix_dealers_company_id", "company_id"),)

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    address: Mapped[str | None] = mapped_column(String, nullable=True)
    gst_number: Mapped[str | None] = mapped_column(String, nullable=True)
    payment_terms_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    credit_limit: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Marketing broadcast consent (see app/services/writes/broadcast.py) —
    # opt-in, defaults False. CSV import never sets this (same precedent as
    # find_or_create_party never setting phone); a dealer becomes opted-in
    # via the edit-dealer flow or the founder's "opt in all dealers" bulk
    # command, never automatically.
    marketing_opt_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Direct overdue-reminder consent (see
    # app/services/notifications.py::check_dealer_overdue_alerts) — the
    # distributor's per-dealer opt-in to also reminding this dealer directly
    # on their own WhatsApp, not only the distributor. Defaults False, same
    # opt-in-not-opt-out precedent as marketing_opt_in above; toggled via the
    # edit-dealer flow, never automatically.
    direct_reminders_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # ── Relationships ────────────────────────────────────────────────────────
    company: Mapped[Company] = relationship("Company", back_populates="dealers")
    invoices: Mapped[list[Invoice]] = relationship("Invoice", back_populates="dealer")
