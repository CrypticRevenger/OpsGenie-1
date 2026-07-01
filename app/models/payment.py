"""Payment ORM model.

Records every payment received from a dealer or made to a supplier.
DealerOutstandingCalculator aggregates these against invoices — no
stored ledger table (per TDD: calculate, never pre-aggregate until
performance demands it).
"""

from __future__ import annotations

import enum
import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, Enum, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._mixins import TimestampMixin, UUIDMixin
from app.models._types import Money

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.invoice import Invoice


class PaymentSource(enum.StrEnum):
    """How the payment was recorded."""

    csv_import = "csv_import"
    whatsapp = "whatsapp"


class Payment(UUIDMixin, TimestampMixin, Base):
    """A payment event against an invoice."""

    __tablename__ = "payments"
    __table_args__ = (
        Index("ix_payments_company_id", "company_id"),
        Index("ix_payments_invoice_id", "invoice_id"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    method: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[PaymentSource] = mapped_column(
        Enum(PaymentSource, name="paymentsource", create_constraint=True),
        nullable=False,
        default=PaymentSource.csv_import,
    )

    # ── Relationships ────────────────────────────────────────────────────────
    company: Mapped[Company] = relationship("Company", back_populates="payments")
    invoice: Mapped[Invoice] = relationship("Invoice", back_populates="payments")
