"""void_payment / void_order — correction-workflow deterministic write services.

Called only from app/services/writes/pending_operation.py's
execute_pending_operation, at confirm time. Mirrors every other write
service's contract: never commits (the caller commits once), re-fetches
everything fresh rather than trusting the preview. Relationships are never
lazy-loaded (an explicit query instead, same as followup.py) — AsyncSession
has no implicit lazy-load support.

Scope is deliberately narrow (see PROJECT_STATUS.md "Edit / correction /
data-management" and the plan behind it): only the single most-recently
recorded WhatsApp payment/order can be targeted (the guided flow in
app/services/workflows/void_flow.py enforces that lookup), and voiding an
order that already has a payment against it is refused outright rather than
attempting any automatic reallocation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business_event import BusinessEvent, BusinessEventType
from app.models.company import Company
from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceStatus
from app.models.invoice_item import InvoiceItem
from app.models.payment import Payment
from app.models.product import Product
from app.models.supplier import Supplier


def _recompute_invoice_status(invoice: Invoice, paid_total: Decimal) -> None:
    """Same three-way rule followup.py's _record_payment_and_close already
    uses for a fresh payment, applied in reverse for a void: Paid only when
    fully covered, Partially_Paid when something remains applied, Pending
    when nothing does."""
    if paid_total <= 0:
        invoice.status = InvoiceStatus.Pending
    elif paid_total >= invoice.total_amount:
        invoice.status = InvoiceStatus.Paid
    else:
        invoice.status = InvoiceStatus.Partially_Paid


async def _party_name_for_invoice(db: AsyncSession, invoice: Invoice) -> str:
    if invoice.dealer_id is not None:
        return await db.scalar(select(Dealer.name).where(Dealer.id == invoice.dealer_id)) or "them"
    if invoice.supplier_id is not None:
        return (
            await db.scalar(select(Supplier.name).where(Supplier.id == invoice.supplier_id))
            or "them"
        )
    return "them"


@dataclass(frozen=True)
class VoidPaymentResult:
    invoice_number: str
    party_name: str
    amount: Decimal


async def void_payment(
    db: AsyncSession, company: Company, *, payment_id: uuid.UUID, reason: str | None
) -> VoidPaymentResult:
    """Delete a payment and recompute its invoice's status. Raises ValueError
    if the payment is gone (e.g. already voided in a race) — the caller
    turns this into a friendly reply rather than committing bad data."""
    payment = await db.get(Payment, payment_id)
    if payment is None or payment.company_id != company.id:
        raise ValueError("that payment is no longer on file")

    invoice = await db.get(Invoice, payment.invoice_id)
    if invoice is None:
        raise ValueError("that payment's invoice is no longer on file")

    party_name = await _party_name_for_invoice(db, invoice)
    amount = payment.amount
    invoice_number = invoice.invoice_number
    await db.delete(payment)
    await db.flush()

    paid_rows = (
        (await db.execute(select(Payment.amount).where(Payment.invoice_id == invoice.id)))
        .scalars()
        .all()
    )
    paid_total = sum(paid_rows, Decimal("0.00"))
    _recompute_invoice_status(invoice, paid_total)

    db.add(
        BusinessEvent(
            company_id=company.id,
            event_type=BusinessEventType.payment_voided,
            entity_type="payment",
            entity_id=payment_id,
            payload={
                "invoice_number": invoice_number,
                "party_name": party_name,
                "amount": str(amount),
                "reason": reason,
            },
            created_by="whatsapp",
        )
    )
    return VoidPaymentResult(invoice_number=invoice_number, party_name=party_name, amount=amount)


@dataclass(frozen=True)
class VoidOrderResult:
    invoice_number: str
    dealer_name: str
    total_amount: Decimal


async def void_order(
    db: AsyncSession, company: Company, *, invoice_id: uuid.UUID, reason: str | None
) -> VoidOrderResult:
    """Soft-cancel a WhatsApp-created order: status -> Cancelled (never a
    hard delete, so the invoice number/history survives and Payment's
    ondelete=CASCADE on invoice_id can't silently take payments with it) and
    restore stock for every line. Raises ValueError if the invoice is gone,
    or if it already has any payment recorded against it (out of scope for
    this simple path — void the payment first)."""
    invoice = await db.get(Invoice, invoice_id)
    if invoice is None or invoice.company_id != company.id:
        raise ValueError("that order is no longer on file")

    has_payment = await db.scalar(select(Payment.id).where(Payment.invoice_id == invoice.id))
    if has_payment is not None:
        raise ValueError(
            "this order already has a payment recorded against it — void the payment first"
        )

    items = (
        (await db.execute(select(InvoiceItem).where(InvoiceItem.invoice_id == invoice.id)))
        .scalars()
        .all()
    )
    for item in items:
        if item.product_id is None:
            continue
        product = await db.get(Product, item.product_id)
        if product is not None:
            product.stock_quantity = product.stock_quantity + item.quantity

    dealer_name = await _party_name_for_invoice(db, invoice)
    invoice_number = invoice.invoice_number
    total_amount = invoice.total_amount
    invoice.status = InvoiceStatus.Cancelled

    db.add(
        BusinessEvent(
            company_id=company.id,
            event_type=BusinessEventType.invoice_voided,
            entity_type="invoice",
            entity_id=invoice.id,
            payload={
                "invoice_number": invoice_number,
                "dealer_name": dealer_name,
                "total_amount": str(total_amount),
                "reason": reason,
            },
            created_by="whatsapp",
        )
    )
    return VoidOrderResult(
        invoice_number=invoice_number, dealer_name=dealer_name, total_amount=total_amount
    )
