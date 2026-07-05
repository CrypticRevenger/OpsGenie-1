"""Product ORM model.

Products exist as a catalogue for invoice line items, and (Phase 2B) carry a
live stock_quantity decremented whenever a WhatsApp-guided order is created —
see app/services/writes/orders.py.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._mixins import TimestampMixin, UUIDMixin
from app.models._types import Money, Quantity

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.invoice_item import InvoiceItem


class Product(UUIDMixin, TimestampMixin, Base):
    """A product in the distributor's catalogue."""

    __tablename__ = "products"
    __table_args__ = (Index("ix_products_company_id", "company_id"),)

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    unit: Mapped[str | None] = mapped_column(String, nullable=True)
    selling_price: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    purchase_price: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    # Phase 2B — decremented by app/services/writes/orders.py::create_order.
    # Allowed to go negative (flagged, not blocked) since physical counts can
    # lag digital ones; server_default backfills existing rows to 0.
    stock_quantity: Mapped[Decimal] = mapped_column(
        Quantity, nullable=False, default=Decimal("0"), server_default=text("0")
    )

    # ── Relationships ────────────────────────────────────────────────────────
    company: Mapped[Company] = relationship("Company", back_populates="products")
    invoice_items: Mapped[list[InvoiceItem]] = relationship("InvoiceItem", back_populates="product")
