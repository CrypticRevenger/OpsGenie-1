"""Invoice ORM model with all status, direction, and source enums.

Invoices are the central entity in OpsGenie.  Every receivable and payable
flows through this table.  The CHECK constraint enforces that every invoice
is tied to either a dealer (receivable) or a supplier (payable).

Append-only business events are triggered on every status change — see
BusinessEngine (Phase 3).
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, DateTime, Enum, ForeignKey, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._mixins import TimestampMixin, UUIDMixin
from app.models._types import Money

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.dealer import Dealer
    from app.models.invoice_item import InvoiceItem
    from app.models.payment import Payment
    from app.models.supplier import Supplier


class InvoiceDirection(enum.StrEnum):
    """Whether money flows in (receivable from dealer) or out (payable to supplier)."""

    receivable = "receivable"
    payable = "payable"


class InvoiceStatus(enum.StrEnum):
    """Invoice lifecycle states.  Every transition writes a BusinessEvent."""

    Draft = "Draft"
    Sent = "Sent"
    Pending = "Pending"
    Partially_Paid = "Partially_Paid"
    Paid = "Paid"
    Overdue = "Overdue"
    Cancelled = "Cancelled"


class InvoiceSource(enum.StrEnum):
    """How the invoice entered the system."""

    csv_import = "csv_import"
    whatsapp = "whatsapp"


class Invoice(UUIDMixin, TimestampMixin, Base):
    """A financial document representing money owed to or by the distributor."""

    __tablename__ = "invoices"
    __table_args__ = (
        # Every invoice must be linked to exactly one counterparty.
        CheckConstraint(
            "dealer_id IS NOT NULL OR supplier_id IS NOT NULL",
            name="ck_invoices_dealer_or_supplier",
        ),
        Index("ix_invoices_company_id", "company_id"),
        Index("ix_invoices_company_status", "company_id", "status"),
        Index("ix_invoices_company_due_date", "company_id", "due_date"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    invoice_number: Mapped[str] = mapped_column(String, nullable=False)
    direction: Mapped[InvoiceDirection] = mapped_column(
        Enum(InvoiceDirection, name="invoicedirection", create_constraint=True),
        nullable=False,
    )
    dealer_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("dealers.id", ondelete="SET NULL"),
        nullable=True,
    )
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
    )
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Money, nullable=False)
    gst_amount: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    total_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    status: Mapped[InvoiceStatus] = mapped_column(
        Enum(InvoiceStatus, name="invoicestatus", create_constraint=True),
        nullable=False,
        default=InvoiceStatus.Pending,
    )
    source: Mapped[InvoiceSource] = mapped_column(
        Enum(InvoiceSource, name="invoicesource", create_constraint=True),
        nullable=False,
        default=InvoiceSource.csv_import,
    )
    # updated_at is the only mutable timestamp in the schema — all event and
    # timeline tables are append-only and have no updated_at by design.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # ── Relationships ────────────────────────────────────────────────────────
    company: Mapped[Company] = relationship("Company", back_populates="invoices")
    dealer: Mapped[Dealer | None] = relationship(
        "Dealer", back_populates="invoices", foreign_keys=[dealer_id]
    )
    supplier: Mapped[Supplier | None] = relationship(
        "Supplier", back_populates="invoices", foreign_keys=[supplier_id]
    )
    items: Mapped[list[InvoiceItem]] = relationship(
        "InvoiceItem", back_populates="invoice", cascade="all, delete-orphan"
    )
    payments: Mapped[list[Payment]] = relationship(
        "Payment", back_populates="invoice", cascade="all, delete-orphan"
    )
