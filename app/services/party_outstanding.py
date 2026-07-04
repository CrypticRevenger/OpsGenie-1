"""DealerOutstandingCalculator — per SPEC.md TDD.

"Calculates outstanding for a dealer as: sum of total_amount for all
receivable invoices in status Pending, Partially_Paid, or Overdue, minus sum
of all payments recorded against those invoices. No stored DealerLedger
table. Pure calculation from Invoices and Payments."

Same calculation applies to a supplier's payable outstanding — the TDD
describes it for dealers, but the schema and logic are symmetric (Invoice
already models both directions), so this module serves both via a single
`direction` parameter rather than two near-identical copies.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invoice import Invoice, InvoiceDirection, InvoiceStatus
from app.models.payment import Payment

Direction = Literal["receivable", "payable"]

_OPEN_STATUSES = (InvoiceStatus.Pending, InvoiceStatus.Partially_Paid, InvoiceStatus.Overdue)


async def calculate_party_outstanding(
    db: AsyncSession, *, direction: Direction, party_id: uuid.UUID
) -> Decimal:
    """Outstanding for one dealer/supplier. Use calculate_outstanding_for_company
    when computing this for many parties at once — this issues 2 queries per
    call, which is fine for a single lookup but would be N+1 in a loop.
    """
    party_column = Invoice.dealer_id if direction == "receivable" else Invoice.supplier_id
    invoice_stmt = select(Invoice.id, Invoice.total_amount).where(
        party_column == party_id,
        Invoice.direction == InvoiceDirection(direction),
        Invoice.status.in_(_OPEN_STATUSES),
    )
    rows = (await db.execute(invoice_stmt)).all()
    if not rows:
        return Decimal("0.00")

    invoice_ids = [r[0] for r in rows]
    total_invoiced = sum((r[1] for r in rows), Decimal("0.00"))

    paid = await db.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.invoice_id.in_(invoice_ids)
        )
    )
    return total_invoiced - Decimal(paid)


async def calculate_outstanding_for_company(
    db: AsyncSession, *, company_id: uuid.UUID, direction: Direction
) -> dict[uuid.UUID, Decimal]:
    """Outstanding for every dealer/supplier in a company, in 2 queries total
    (not one call per party) — the batched counterpart to the single-party
    function above, for use by BusinessSnapshotService.
    """
    party_column = Invoice.dealer_id if direction == "receivable" else Invoice.supplier_id
    invoice_stmt = select(Invoice.id, party_column, Invoice.total_amount).where(
        Invoice.company_id == company_id,
        Invoice.direction == InvoiceDirection(direction),
        Invoice.status.in_(_OPEN_STATUSES),
        party_column.is_not(None),
    )
    rows = (await db.execute(invoice_stmt)).all()
    if not rows:
        return {}

    invoice_ids = [r[0] for r in rows]

    paid_rows = await db.execute(
        select(Payment.invoice_id, func.sum(Payment.amount))
        .where(Payment.invoice_id.in_(invoice_ids))
        .group_by(Payment.invoice_id)
    )
    paid_by_invoice: dict[uuid.UUID, Decimal] = dict(paid_rows.all())

    outstanding_by_party: dict[uuid.UUID, Decimal] = {}
    for invoice_id, party_id, total_amount in rows:
        paid = paid_by_invoice.get(invoice_id, Decimal("0.00"))
        outstanding_by_party[party_id] = (
            outstanding_by_party.get(party_id, Decimal("0.00")) + total_amount - paid
        )
    return outstanding_by_party
