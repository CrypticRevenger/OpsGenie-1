"""Admin invoice read routes — Phase 4.

Read-only. Invoice creation happens via CSV/Excel import (Phase 3) or,
later, WhatsApp (V0.2) — never through this router.
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.company import Company
from app.models.invoice import Invoice, InvoiceStatus
from app.models.payment import Payment
from app.schemas.invoice import InvoiceDetailResponse, InvoiceResponse
from app.schemas.pagination import Page
from app.schemas.payment import PaymentResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/companies/{company_id}", tags=["admin:invoices"])


async def _get_company_or_404(company_id: uuid.UUID, db: AsyncSession) -> Company:
    company = await db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company {company_id} not found.",
        )
    return company


async def _attach_payment_totals(db: AsyncSession, invoices: list[Invoice]) -> None:
    """Attach amount_paid/amount_outstanding to each Invoice as transient attrs.

    One grouped query for the whole batch — not one SUM query per invoice.
    """
    if not invoices:
        return
    invoice_ids = [inv.id for inv in invoices]
    paid_rows = await db.execute(
        select(Payment.invoice_id, func.sum(Payment.amount))
        .where(Payment.invoice_id.in_(invoice_ids))
        .group_by(Payment.invoice_id)
    )
    paid_by_invoice: dict[uuid.UUID, Decimal] = dict(paid_rows.all())
    for invoice in invoices:
        paid = paid_by_invoice.get(invoice.id, Decimal("0.00"))
        invoice.amount_paid = paid
        invoice.amount_outstanding = invoice.total_amount - paid


@router.get(
    "/invoices",
    response_model=Page[InvoiceResponse],
    summary="List invoices for a company",
)
async def list_invoices(
    company_id: uuid.UUID,
    direction: Literal["receivable", "payable"] | None = Query(None),
    status_filter: InvoiceStatus | None = Query(None, alias="status"),
    dealer_id: uuid.UUID | None = Query(None),
    supplier_id: uuid.UUID | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> Page[InvoiceResponse]:
    await _get_company_or_404(company_id, db)

    # Built once, applied to both the count and the data query, so the
    # reported `total` always matches the same filters as `items`.
    conditions = [Invoice.company_id == company_id]
    if direction is not None:
        conditions.append(Invoice.direction == direction)
    if status_filter is not None:
        conditions.append(Invoice.status == status_filter)
    if dealer_id is not None:
        conditions.append(Invoice.dealer_id == dealer_id)
    if supplier_id is not None:
        conditions.append(Invoice.supplier_id == supplier_id)

    total = await db.scalar(select(func.count()).select_from(Invoice).where(*conditions)) or 0
    stmt = (
        select(Invoice)
        .where(*conditions)
        .order_by(Invoice.due_date, Invoice.invoice_number)
        .offset((page - 1) * limit)
        .limit(limit)
    )
    invoices = list((await db.execute(stmt)).scalars().all())
    await _attach_payment_totals(db, invoices)
    return Page.create(items=invoices, total=total, page=page, limit=limit)


@router.get(
    "/invoices/{invoice_id}",
    response_model=InvoiceDetailResponse,
    summary="Get a single invoice, with its payments",
)
async def get_invoice(
    company_id: uuid.UUID,
    invoice_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> InvoiceDetailResponse:
    await _get_company_or_404(company_id, db)

    invoice = await db.scalar(
        select(Invoice).where(Invoice.id == invoice_id, Invoice.company_id == company_id)
    )
    if invoice is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice {invoice_id} not found in company {company_id}.",
        )

    payments = list(
        (
            await db.execute(
                select(Payment)
                .where(Payment.invoice_id == invoice_id)
                .order_by(Payment.payment_date.desc())
            )
        )
        .scalars()
        .all()
    )
    paid = sum((p.amount for p in payments), Decimal("0.00"))
    # Set as plain transient attributes, not via the real ORM `payments`
    # relationship (that's a mapped, cascading collection — reassigning it
    # here could trigger unwanted SQLAlchemy relationship bookkeeping, and
    # under AsyncSession an unloaded access would raise a lazy-load error).
    invoice.amount_paid = paid
    invoice.amount_outstanding = invoice.total_amount - paid
    return InvoiceDetailResponse(
        **InvoiceResponse.model_validate(invoice).model_dump(),
        payments=[PaymentResponse.model_validate(p) for p in payments],
    )


@router.delete(
    "/invoices/{invoice_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an invoice (cascades to its line items and payments)",
    description=(
        "Permanently deletes an invoice and everything scoped to it (line "
        "items, payments) via database cascade. This does NOT re-run FIFO "
        "payment reconciliation on any other invoice — real invoice/payment "
        "writes should normally go through CSV import or the guided "
        "WhatsApp workflows, which keep amount_outstanding correct. Use "
        "this only to clean up bad data; spot-check cashflow afterward."
    ),
)
async def delete_invoice(
    company_id: uuid.UUID,
    invoice_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Response:
    await _get_company_or_404(company_id, db)
    invoice = await db.scalar(
        select(Invoice).where(Invoice.id == invoice_id, Invoice.company_id == company_id)
    )
    if invoice is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice {invoice_id} not found in company {company_id}.",
        )
    logger.warning(
        "Deleting invoice %s for company %s — this does not re-run FIFO "
        "payment reconciliation; verify cashflow afterward.",
        invoice_id,
        company_id,
    )
    await db.delete(invoice)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
