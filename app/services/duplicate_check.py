"""Advisory (party, date, amount) duplicate lookups for the WhatsApp guided
payment/order flows.

Distinct from the CSV importer's dedup (app/services/importer/payment_row.py's
source_row_key, checked against BusinessEvent payloads): WhatsApp-written
payments get a synthetic always-unique source_row_key, and WhatsApp-created
orders never emit an invoice_created BusinessEvent at all (only CSV import
does) — so this queries Payment/Invoice directly instead.

Both checks are advisory only (a match is a "heads up", never a block) —
callers decide whether/how to surface it, same "flag, don't block" tier as
writes/orders.py's negative_stock_warnings. A limitation worth remembering:
allocate_payment_fifo can split one real payment across several invoices as
several partial Payment rows, so an exact-amount match here can miss that
split case — acceptable for a best-effort heads-up, not a hard guarantee.
"""

from __future__ import annotations

import uuid
from datetime import date as date_type
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invoice import Invoice, InvoiceDirection, InvoiceStatus
from app.models.payment import Payment
from app.services.party_outstanding import Direction


async def find_similar_payment(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    direction: Direction,
    party_id: uuid.UUID,
    payment_date: date_type,
    amount: Decimal,
) -> Payment | None:
    party_column = Invoice.dealer_id if direction == "receivable" else Invoice.supplier_id
    return await db.scalar(
        select(Payment)
        .join(Invoice, Payment.invoice_id == Invoice.id)
        .where(
            Invoice.company_id == company_id,
            party_column == party_id,
            Invoice.direction == InvoiceDirection(direction),
            Payment.payment_date == payment_date,
            Payment.amount == amount,
        )
        .limit(1)
    )


async def find_similar_order(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    dealer_id: uuid.UUID,
    invoice_date: date_type,
    total_amount: Decimal,
) -> Invoice | None:
    return await db.scalar(
        select(Invoice)
        .where(
            Invoice.company_id == company_id,
            Invoice.dealer_id == dealer_id,
            Invoice.direction == InvoiceDirection.receivable,
            Invoice.status != InvoiceStatus.Cancelled,
            Invoice.invoice_date == invoice_date,
            Invoice.total_amount == total_amount,
        )
        .limit(1)
    )
