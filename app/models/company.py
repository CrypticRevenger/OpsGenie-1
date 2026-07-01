"""Company ORM model.

A Company represents a single B2B distributor using OpsGenie.  All other
entities (dealers, invoices, payments …) are scoped to a company.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._mixins import TimestampMixin, UUIDMixin
from app.models._types import Money

if TYPE_CHECKING:
    from app.models.activity_timeline import ActivityTimeline
    from app.models.business_event import BusinessEvent
    from app.models.cash_snapshot import CashSnapshot
    from app.models.dealer import Dealer
    from app.models.import_log import ImportLog
    from app.models.invoice import Invoice
    from app.models.morning_briefing import MorningBriefing
    from app.models.notification_log import NotificationLog
    from app.models.payment import Payment
    from app.models.product import Product
    from app.models.supplier import Supplier


class Company(UUIDMixin, TimestampMixin, Base):
    """A B2B distributor company registered with OpsGenie."""

    __tablename__ = "companies"
    __table_args__ = (
        UniqueConstraint("whatsapp_number", name="uq_companies_whatsapp_number"),
    )

    business_name: Mapped[str] = mapped_column(String, nullable=False)
    owner_name: Mapped[str] = mapped_column(String, nullable=False)
    whatsapp_number: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    business_type: Mapped[str | None] = mapped_column(String, nullable=True)
    preferred_language: Mapped[str] = mapped_column(String, nullable=False, default="en")
    # Manually toggled for pilot users — no billing system in V0.0 or V0.1.
    subscription_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    opening_balance: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))

    # ── Relationships ────────────────────────────────────────────────────────
    dealers: Mapped[list[Dealer]] = relationship(
        "Dealer", back_populates="company", cascade="all, delete-orphan"
    )
    suppliers: Mapped[list[Supplier]] = relationship(
        "Supplier", back_populates="company", cascade="all, delete-orphan"
    )
    products: Mapped[list[Product]] = relationship(
        "Product", back_populates="company", cascade="all, delete-orphan"
    )
    invoices: Mapped[list[Invoice]] = relationship(
        "Invoice", back_populates="company", cascade="all, delete-orphan"
    )
    payments: Mapped[list[Payment]] = relationship(
        "Payment", back_populates="company", cascade="all, delete-orphan"
    )
    cash_snapshots: Mapped[list[CashSnapshot]] = relationship(
        "CashSnapshot", back_populates="company", cascade="all, delete-orphan"
    )
    business_events: Mapped[list[BusinessEvent]] = relationship(
        "BusinessEvent", back_populates="company", cascade="all, delete-orphan"
    )
    activity_timelines: Mapped[list[ActivityTimeline]] = relationship(
        "ActivityTimeline", back_populates="company", cascade="all, delete-orphan"
    )
    morning_briefings: Mapped[list[MorningBriefing]] = relationship(
        "MorningBriefing", back_populates="company", cascade="all, delete-orphan"
    )
    import_logs: Mapped[list[ImportLog]] = relationship(
        "ImportLog", back_populates="company", cascade="all, delete-orphan"
    )
    notification_logs: Mapped[list[NotificationLog]] = relationship(
        "NotificationLog", back_populates="company", cascade="all, delete-orphan"
    )
