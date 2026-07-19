"""edit_invoice / edit_payment — correction-workflow deterministic write
services, safe cases only.

Called only from app/services/writes/pending_operation.py's
execute_pending_operation, at confirm time. Re-fetches everything fresh,
never commits (the caller commits once).

Deliberately narrow scope (see PROJECT_STATUS.md "Edit / correction /
data-management" and the plan behind it — an earlier, more "clever" version
that auto-reallocated payments across invoices via FIFO was cut after
review as too risky/hard to explain): editing an invoice is refused outright
the moment it has any payment recorded against it, regardless of which
field — no automatic reallocation is ever attempted. Editing a payment's
amount is bounds-checked only against its own invoice's total; it can never
move money to a different invoice.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business_event import BusinessEvent, BusinessEventType
from app.models.company import Company
from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceDirection
from app.models.payment import Payment
from app.models.supplier import Supplier
from app.services.writes.void import _recompute_invoice_status


@dataclass(frozen=True)
class EditInvoiceResult:
    invoice_number: str
    field: str
    old_value: str
    new_value: str


async def edit_invoice(
    db: AsyncSession,
    company: Company,
    *,
    invoice_id: uuid.UUID,
    field: str,
    new_value: str,
    reason: str | None,
) -> EditInvoiceResult:
    """Raises ValueError if the invoice is gone, already has any payment
    recorded (the one deliberate guardrail — see module docstring), or the
    new value doesn't parse/validate."""
    invoice = await db.get(Invoice, invoice_id)
    if invoice is None or invoice.company_id != company.id:
        raise ValueError("that invoice is no longer on file")

    has_payment = await db.scalar(select(Payment.id).where(Payment.invoice_id == invoice.id))
    if has_payment is not None:
        raise ValueError(
            "this invoice already has a payment recorded against it — void it and "
            "recreate instead"
        )

    if field == "amount":
        new_amount = Decimal(new_value)
        if new_amount <= 0:
            raise ValueError("amount must be greater than zero")
        # The GST amount is a snapshot of the rate that applied at creation
        # (same "never rewrite history" rule update_gst.py documents) — the
        # correction lands entirely on subtotal, the taxable value, so
        # subtotal + gst_amount still equals the new total exactly. Editing
        # the header total does not rewrite InvoiceItem line totals — a
        # deliberate simplification, see module docstring.
        new_subtotal = new_amount - invoice.gst_amount
        if new_subtotal < 0:
            raise ValueError("that amount is less than the GST already recorded on this invoice")
        old_value = str(invoice.total_amount)
        invoice.subtotal = new_subtotal
        invoice.total_amount = new_amount
        new_value_display = str(new_amount)
    elif field == "date":
        old_value = invoice.invoice_date.isoformat()
        invoice.invoice_date = date.fromisoformat(new_value)
        new_value_display = new_value
    elif field == "party":
        if invoice.direction == InvoiceDirection.receivable:
            old_dealer = await db.get(Dealer, invoice.dealer_id) if invoice.dealer_id else None
            old_value = old_dealer.name if old_dealer is not None else "—"
            new_dealer = await db.get(Dealer, uuid.UUID(new_value))
            if new_dealer is None or new_dealer.company_id != company.id:
                raise ValueError("that dealer is no longer on file")
            invoice.dealer_id = new_dealer.id
            new_value_display = new_dealer.name
        else:
            old_supplier = (
                await db.get(Supplier, invoice.supplier_id) if invoice.supplier_id else None
            )
            old_value = old_supplier.name if old_supplier is not None else "—"
            new_supplier = await db.get(Supplier, uuid.UUID(new_value))
            if new_supplier is None or new_supplier.company_id != company.id:
                raise ValueError("that supplier is no longer on file")
            invoice.supplier_id = new_supplier.id
            new_value_display = new_supplier.name
    else:
        raise ValueError(f"unknown field: {field}")

    invoice_number = invoice.invoice_number
    db.add(
        BusinessEvent(
            company_id=company.id,
            event_type=BusinessEventType.invoice_edited,
            entity_type="invoice",
            entity_id=invoice.id,
            payload={
                "invoice_number": invoice_number,
                "field": field,
                "old": old_value,
                "new": new_value_display,
                "reason": reason,
            },
            created_by="whatsapp",
        )
    )
    return EditInvoiceResult(
        invoice_number=invoice_number, field=field, old_value=old_value, new_value=new_value_display
    )


@dataclass(frozen=True)
class EditPaymentResult:
    invoice_number: str
    field: str
    old_value: str
    new_value: str


async def edit_payment(
    db: AsyncSession,
    company: Company,
    *,
    payment_id: uuid.UUID,
    field: str,
    new_value: str,
    reason: str | None,
) -> EditPaymentResult:
    """Raises ValueError if the payment is gone, or (for an amount edit)
    the new amount would overpay its own invoice — never moves money to a
    different invoice, see module docstring."""
    payment = await db.get(Payment, payment_id)
    if payment is None or payment.company_id != company.id:
        raise ValueError("that payment is no longer on file")

    invoice = await db.get(Invoice, payment.invoice_id)
    if invoice is None:
        raise ValueError("that payment's invoice is no longer on file")

    if field == "date":
        old_value = payment.payment_date.isoformat()
        payment.payment_date = date.fromisoformat(new_value)
        new_value_display = new_value
    elif field == "amount":
        new_amount = Decimal(new_value)
        if new_amount <= 0:
            raise ValueError("amount must be greater than zero")
        other_paid = (
            await db.execute(
                select(Payment.amount).where(
                    Payment.invoice_id == invoice.id, Payment.id != payment.id
                )
            )
        ).scalars().all()
        other_paid_total = sum(other_paid, Decimal("0.00"))
        if other_paid_total + new_amount > invoice.total_amount:
            overpay_by = other_paid_total + new_amount - invoice.total_amount
            raise ValueError(
                f"that would overpay this invoice by {overpay_by} — reduce the amount, "
                "or edit the invoice's total instead"
            )
        old_value = str(payment.amount)
        payment.amount = new_amount
        _recompute_invoice_status(invoice, other_paid_total + new_amount)
        new_value_display = str(new_amount)
    else:
        raise ValueError(f"unknown field: {field}")

    invoice_number = invoice.invoice_number
    db.add(
        BusinessEvent(
            company_id=company.id,
            event_type=BusinessEventType.payment_edited,
            entity_type="payment",
            entity_id=payment.id,
            payload={
                "invoice_number": invoice_number,
                "field": field,
                "old": old_value,
                "new": new_value_display,
                "reason": reason,
            },
            created_by="whatsapp",
        )
    )
    return EditPaymentResult(
        invoice_number=invoice_number, field=field, old_value=old_value, new_value=new_value_display
    )
