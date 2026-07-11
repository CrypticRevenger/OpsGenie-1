"""create_order — Phase 2B deterministic write service.

Called only from app/services/writes/pending_operation.py's
execute_pending_operation, at confirm time. Mirrors record_payment's shape:
the guided flow (app/services/workflows/order_flow.py) only collects and
previews raw user input; this module re-derives dealer/product resolution,
pricing, and stock against current DB state and performs the actual write.

Never commits — the caller (execute_pending_operation) commits once, same
contract as every other write-touching service in this codebase.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.invoice import Invoice, InvoiceDirection, InvoiceSource, InvoiceStatus
from app.models.invoice_item import InvoiceItem
from app.models.product import Product
from app.services.importer.parties import find_or_create_party
from app.services.snapshot import business_now

_CENTS = Decimal("0.01")
# SPEC.md's V0.2 "Invoice Creation" example ("Due: 14 days from today") — used
# whenever the dealer has no payment_terms_days on file.
_DEFAULT_DUE_DAYS = 14


@dataclass(frozen=True)
class OrderLine:
    product_id: uuid.UUID
    product_name: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal


@dataclass(frozen=True)
class CreateOrderResult:
    invoice_id: uuid.UUID
    invoice_number: str
    invoice_date: date
    due_date: date
    dealer_id: uuid.UUID
    dealer_name: str
    dealer_phone: str | None
    lines: list[OrderLine]
    subtotal: Decimal
    gst_amount: Decimal
    total_amount: Decimal
    negative_stock_warnings: list[str]


async def _resolve_product(db: AsyncSession, company_id: uuid.UUID, item: dict) -> Product:
    """Case-insensitive match against Product; create it (or backfill its
    price) if the guided flow collected one, since onboarding-created
    products commonly have no selling_price on file yet.

    Raises ValueError if a price is genuinely needed but unavailable —
    re-validated fresh here rather than trusting the flow's preview, per the
    PendingOperation contract.
    """
    name = item["product_name"]
    product = await db.scalar(
        select(Product).where(
            Product.company_id == company_id, func.lower(Product.name) == name.lower()
        )
    )
    price_raw = item.get("price")

    if product is None:
        if not price_raw:
            raise ValueError(f"No price on file for '{name}' and none was provided")
        product = Product(
            company_id=company_id,
            name=name,
            selling_price=Decimal(price_raw),
            stock_quantity=Decimal("0"),
        )
        db.add(product)
        await db.flush()
        return product

    if product.selling_price is None:
        if not price_raw:
            raise ValueError(f"No price on file for '{name}'")
        product.selling_price = Decimal(price_raw)

    return product


async def create_order(
    db: AsyncSession,
    company: Company,
    *,
    dealer_name: str,
    items: list[dict],
) -> CreateOrderResult:
    """Record a WhatsApp-guided order as a receivable invoice against a
    dealer, decrementing catalogue stock for each line.

    Raises ValueError on re-validation failure (a quantity of zero or less,
    or a product with no price collected) — the caller turns this into a
    friendly reply rather than committing bad data.
    """
    if not items:
        raise ValueError("An order needs at least one product")

    dealer = await find_or_create_party(db, company.id, "receivable", dealer_name)

    lines: list[OrderLine] = []
    negative_stock_warnings: list[str] = []

    for item in items:
        quantity = Decimal(item["quantity"])
        if quantity <= 0:
            raise ValueError(f"Quantity for '{item['product_name']}' must be greater than zero")

        product = await _resolve_product(db, company.id, item)
        unit_price = product.selling_price
        line_total = (unit_price * quantity).quantize(_CENTS)

        product.stock_quantity = product.stock_quantity - quantity
        if product.stock_quantity < 0:
            negative_stock_warnings.append(product.name)

        lines.append(
            OrderLine(
                product_id=product.id,
                product_name=product.name,
                quantity=quantity,
                unit_price=unit_price,
                line_total=line_total,
            )
        )

    subtotal = sum((line.line_total for line in lines), Decimal("0.00"))
    gst_amount = (subtotal * company.gst_rate / Decimal("100")).quantize(_CENTS)
    total_amount = subtotal + gst_amount
    today = business_now(company.timezone).date()
    due_date = today + timedelta(days=dealer.payment_terms_days or _DEFAULT_DUE_DAYS)
    invoice_number = f"WA-{uuid.uuid4().hex[:10]}"

    invoice = Invoice(
        company_id=company.id,
        invoice_number=invoice_number,
        direction=InvoiceDirection.receivable,
        dealer_id=dealer.id,
        invoice_date=today,
        due_date=due_date,
        subtotal=subtotal,
        gst_amount=gst_amount,
        total_amount=total_amount,
        status=InvoiceStatus.Pending,
        source=InvoiceSource.whatsapp,
    )
    db.add(invoice)
    await db.flush()

    for line in lines:
        db.add(
            InvoiceItem(
                invoice_id=invoice.id,
                product_id=line.product_id,
                description=line.product_name,
                quantity=line.quantity,
                unit_price=line.unit_price,
                line_total=line.line_total,
            )
        )

    return CreateOrderResult(
        invoice_id=invoice.id,
        invoice_number=invoice_number,
        invoice_date=today,
        due_date=due_date,
        dealer_id=dealer.id,
        dealer_name=dealer.name,
        dealer_phone=dealer.phone,
        lines=lines,
        subtotal=subtotal,
        gst_amount=gst_amount,
        total_amount=total_amount,
        negative_stock_warnings=negative_stock_warnings,
    )
