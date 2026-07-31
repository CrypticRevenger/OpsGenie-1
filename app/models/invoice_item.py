"""InvoiceItem ORM model.

Line items on an invoice.  product_id is nullable because CSV-imported invoices
may not have matched a product in the catalogue yet.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._mixins import UUIDMixin
from app.models._types import Money, Quantity

if TYPE_CHECKING:
    from app.models.invoice import Invoice
    from app.models.product import Product


class InvoiceItem(UUIDMixin, Base):
    """A single line on an invoice."""

    __tablename__ = "invoice_items"
    __table_args__ = (
        # Items are always fetched (or EXISTS-tested) by their parent invoice;
        # also covers the FK's ON DELETE CASCADE scan.
        Index("ix_invoice_items_invoice_id", "invoice_id"),
    )

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
    )
    description: Mapped[str] = mapped_column(String, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Money, nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Money, nullable=False)
    # Snapshot of the rate/amount actually applied to this line at invoice
    # time (from Product.gst_rate or the company default, whichever applied
    # then) — never rewritten by a later rate change, so historical invoices
    # stay accurate. See app/services/writes/orders.py::create_order.
    gst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("0"))
    gst_amount: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))

    # ── Relationships ────────────────────────────────────────────────────────
    invoice: Mapped[Invoice] = relationship("Invoice", back_populates="items")
    product: Mapped[Product | None] = relationship("Product", back_populates="invoice_items")
