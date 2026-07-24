"""DailyBusinessSnapshot ORM model.

One row per company per calendar (business-local) day, finalized by the
evening scheduler job (see app/services/daily_snapshot.py). Deliberately
generic — not a narrow "profit/loss" table — so the same row can back the
dashboard, the evening WhatsApp brief, and future monthly reports without a
schema change. Every field measures one specific, unambiguous thing; nothing
here blends accrual (margin) and cash-basis (collections/payments) figures
into a single derived number — see the module docstring on
app/services/daily_snapshot.py for why.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Integer, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._mixins import TimestampMixin, UUIDMixin
from app.models._types import Money

if TYPE_CHECKING:
    from app.models.company import Company


class DailyBusinessSnapshot(UUIDMixin, TimestampMixin, Base):
    """A finalized, per-day rollup of a company's sales, margin, and cash
    activity — see app/services/daily_snapshot.py::finalize_daily_snapshot.
    """

    __tablename__ = "daily_business_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "business_date", name="uq_daily_business_snapshots_company_date"
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    business_date: Mapped[date] = mapped_column(Date, nullable=False)

    sales_amount: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    sales_margin: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    # Line items excluded from sales_margin because their product has no
    # purchase_price on file — never assumed to be 0-cost, which would
    # overstate margin. See app/services/daily_snapshot.py.
    items_missing_cost_data: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    revenue_excluded_no_cost_data: Mapped[Decimal] = mapped_column(
        Money, nullable=False, default=Decimal("0")
    )

    collections_amount: Mapped[Decimal] = mapped_column(
        Money, nullable=False, default=Decimal("0")
    )
    supplier_payments_amount: Mapped[Decimal] = mapped_column(
        Money, nullable=False, default=Decimal("0")
    )
    net_cash_movement: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))

    outstanding_receivables: Mapped[Decimal] = mapped_column(
        Money, nullable=False, default=Decimal("0")
    )

    invoices_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payments_recorded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Receivable invoices created via the WhatsApp guided flow (source ==
    # "whatsapp") dated today. Named "created," not "delivered" — this schema
    # has no delivery/fulfillment status to honestly report on.
    orders_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    finalized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Atomic claim marker for the evening WhatsApp brief send — see
    # app/services/evening_brief.py::send_evening_brief. NULL until a tick
    # claims this row via a conditional UPDATE ... WHERE delivered_at IS
    # NULL; reset back to NULL if that attempt's send then fails, so a later
    # tick can retry. This is the actual race guard (Postgres's row lock on
    # this unique-constrained row), not just an informational timestamp —
    # deliberately distinct from NotificationLog's own "sent"/"failed_to_send"
    # bookkeeping, which stays the source of truth for delivery *history*.
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Relationships ────────────────────────────────────────────────────────
    company: Mapped[Company] = relationship("Company", back_populates="daily_business_snapshots")
