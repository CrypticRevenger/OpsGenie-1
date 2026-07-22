"""Admin payment read routes — Phase 4.

Read-only. Payment creation happens via CSV/Excel import (Phase 3) or,
later, WhatsApp (V0.2) — never through this router.
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.company import Company
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.schemas.pagination import Page
from app.schemas.payment import PaymentResponse
from app.services.writes.void import recompute_invoice_status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/companies/{company_id}", tags=["admin:payments"])


async def _get_company_or_404(company_id: uuid.UUID, db: AsyncSession) -> Company:
    company = await db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company {company_id} not found.",
        )
    return company


def _payments_base_stmt(
    company_id: uuid.UUID,
    *,
    dealer_id: uuid.UUID | None,
    supplier_id: uuid.UUID | None,
    invoice_id: uuid.UUID | None,
):
    """Shared WHERE/JOIN construction for both the count and data query, so
    `total` can never drift from the filters applied to `items`.
    """
    conditions = [Payment.company_id == company_id]
    needs_invoice_join = dealer_id is not None or supplier_id is not None
    if dealer_id is not None:
        conditions.append(Invoice.dealer_id == dealer_id)
    if supplier_id is not None:
        conditions.append(Invoice.supplier_id == supplier_id)
    if invoice_id is not None:
        conditions.append(Payment.invoice_id == invoice_id)
    return conditions, needs_invoice_join


@router.get(
    "/payments",
    response_model=Page[PaymentResponse],
    summary="List payments for a company",
)
async def list_payments(
    company_id: uuid.UUID,
    dealer_id: uuid.UUID | None = Query(None),
    supplier_id: uuid.UUID | None = Query(None),
    invoice_id: uuid.UUID | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> Page[PaymentResponse]:
    await _get_company_or_404(company_id, db)

    conditions, needs_invoice_join = _payments_base_stmt(
        company_id, dealer_id=dealer_id, supplier_id=supplier_id, invoice_id=invoice_id
    )

    count_stmt = select(func.count()).select_from(Payment)
    stmt = select(Payment)
    if needs_invoice_join:
        # Payment has no direct dealer_id/supplier_id column — filtering by
        # party requires joining through the invoice it was recorded against.
        count_stmt = count_stmt.join(Invoice, Payment.invoice_id == Invoice.id)
        stmt = stmt.join(Invoice, Payment.invoice_id == Invoice.id)
    count_stmt = count_stmt.where(*conditions)
    stmt = stmt.where(*conditions).order_by(Payment.payment_date.desc())
    stmt = stmt.offset((page - 1) * limit).limit(limit)

    total = await db.scalar(count_stmt) or 0
    payments = list((await db.execute(stmt)).scalars().all())
    return Page.create(items=payments, total=total, page=page, limit=limit)


@router.delete(
    "/payments/{payment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a payment",
    description=(
        "Permanently deletes a payment and recomputes its invoice's status "
        "from the payments that remain. This does NOT re-run FIFO payment "
        "reconciliation across the party's *other* invoices — real payments "
        "should normally go through CSV import or the guided WhatsApp "
        "workflows. Use this only to clean up bad data."
    ),
)
async def delete_payment(
    company_id: uuid.UUID,
    payment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Response:
    await _get_company_or_404(company_id, db)
    payment = await db.scalar(
        select(Payment).where(Payment.id == payment_id, Payment.company_id == company_id)
    )
    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Payment {payment_id} not found in company {company_id}.",
        )
    logger.warning(
        "Deleting payment %s for company %s — this does not re-run FIFO "
        "reconciliation across the party's other invoices.",
        payment_id,
        company_id,
    )
    invoice_id = payment.invoice_id
    await db.delete(payment)
    await db.flush()

    # Restore the invoice-status invariant every read path depends on. Without
    # this the invoice keeps a stale `Paid`, which _OPEN_STATUSES excludes — so
    # calculate_party_outstanding reports 0 for money that is once again owed,
    # while reports/ledger.py (which filters only Draft/Cancelled) still shows
    # the full balance. Same three-way rule as writes/void.py::void_payment,
    # which is the guided-workflow equivalent of this route.
    invoice = await db.get(Invoice, invoice_id)
    if invoice is not None:
        paid_total = sum(
            (
                await db.execute(select(Payment.amount).where(Payment.invoice_id == invoice.id))
            )
            .scalars()
            .all(),
            Decimal("0.00"),
        )
        recompute_invoice_status(invoice, paid_total)

    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
