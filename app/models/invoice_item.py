"""InvoiceItem ORM model.

Line items on an invoice.  product_id is nullable because CSV-imported invoices
may not have matched a product in the catalogue yet.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Uuid
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

    # ── Relationships ────────────────────────────────────────────────────────
    invoice: Mapped[Invoice] = relationship("Invoice", back_populates="items")
    product: Mapped[Product | None] = relationship("Product", back_populates="invoice_items")
