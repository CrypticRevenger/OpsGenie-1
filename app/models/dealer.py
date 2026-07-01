"""Dealer ORM model.

A Dealer is a customer of the distributor — someone who buys from the company
and whose outstanding receivables are tracked by OpsGenie.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Integer, String, Text, Uuid
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

    # ── Relationships ────────────────────────────────────────────────────────
    company: Mapped[Company] = relationship("Company", back_populates="dealers")
    invoices: Mapped[list[Invoice]] = relationship("Invoice", back_populates="dealer")
