"""Admin dealer routes.

Dealers are created scoped to a specific company.
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.company import Company
from app.models.dealer import Dealer
from app.models.invoice import Invoice
from app.schemas.dealer import DealerCreate, DealerResponse, DealerUpdate
from app.schemas.pagination import Page

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/companies/{company_id}/dealers", tags=["admin:dealers"])


async def _get_company_or_404(company_id: uuid.UUID, db: AsyncSession) -> Company:
    """Fetch a company or raise 404."""
    company = await db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company {company_id} not found.",
        )
    return company


async def _get_dealer_or_404(
    company_id: uuid.UUID, dealer_id: uuid.UUID, db: AsyncSession
) -> Dealer:
    result = await db.execute(
        select(Dealer).where(Dealer.id == dealer_id, Dealer.company_id == company_id)
    )
    dealer = result.scalar_one_or_none()
    if dealer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dealer {dealer_id} not found in company {company_id}.",
        )
    return dealer


@router.post(
    "",
    response_model=DealerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a dealer to a company",
)
async def create_dealer(
    company_id: uuid.UUID,
    payload: DealerCreate,
    db: AsyncSession = Depends(get_db),
) -> Dealer:
    await _get_company_or_404(company_id, db)

    dealer = Dealer(
        company_id=company_id,
        name=payload.name,
        phone=payload.phone,
        address=payload.address,
        gst_number=payload.gst_number,
        payment_terms_days=payload.payment_terms_days,
        credit_limit=payload.credit_limit,
        notes=payload.notes,
    )
    db.add(dealer)
    await db.commit()
    await db.refresh(dealer)
    logger.info("Created dealer %s for company %s", dealer.name, company_id)
    return dealer


@router.get(
    "",
    response_model=Page[DealerResponse],
    summary="List dealers for a company",
)
async def list_dealers(
    company_id: uuid.UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> Page[DealerResponse]:
    await _get_company_or_404(company_id, db)
    total = (
        await db.scalar(
            select(func.count()).select_from(Dealer).where(Dealer.company_id == company_id)
        )
        or 0
    )
    result = await db.execute(
        select(Dealer)
        .where(Dealer.company_id == company_id)
        .order_by(Dealer.name)
        .offset((page - 1) * limit)
        .limit(limit)
    )
    dealers = list(result.scalars().all())
    return Page.create(items=dealers, total=total, page=page, limit=limit)


@router.get(
    "/{dealer_id}",
    response_model=DealerResponse,
    summary="Get a dealer by ID",
)
async def get_dealer(
    company_id: uuid.UUID,
    dealer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Dealer:
    await _get_company_or_404(company_id, db)
    result = await db.execute(
        select(Dealer).where(Dealer.id == dealer_id, Dealer.company_id == company_id)
    )
    dealer = result.scalar_one_or_none()
    if dealer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dealer {dealer_id} not found in company {company_id}.",
        )
    return dealer


@router.patch(
    "/{dealer_id}",
    response_model=DealerResponse,
    summary="Update a dealer",
)
async def update_dealer(
    company_id: uuid.UUID,
    dealer_id: uuid.UUID,
    payload: DealerUpdate,
    db: AsyncSession = Depends(get_db),
) -> Dealer:
    await _get_company_or_404(company_id, db)
    dealer = await _get_dealer_or_404(company_id, dealer_id, db)

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(dealer, field, value)

    await db.commit()
    await db.refresh(dealer)
    logger.info("Updated dealer %s for company %s", dealer.id, company_id)
    return dealer


@router.get(
    "/{dealer_id}/delete-preview",
    summary="Pre-delete impact summary for a dealer",
)
async def dealer_delete_preview(
    company_id: uuid.UUID,
    dealer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """How many invoices (and their total amount) would be cascade-deleted
    along with this dealer — see delete_dealer's docstring for why deleting
    a dealer's invoices is unavoidable.
    """
    await _get_company_or_404(company_id, db)
    await _get_dealer_or_404(company_id, dealer_id, db)
    invoice_count = (
        await db.scalar(
            select(func.count()).select_from(Invoice).where(Invoice.dealer_id == dealer_id)
        )
        or 0
    )
    total_amount = (
        await db.scalar(
            select(func.sum(Invoice.total_amount)).where(Invoice.dealer_id == dealer_id)
        )
        or Decimal("0.00")
    )
    return {"invoice_count": invoice_count, "total_amount": total_amount}


@router.delete(
    "/{dealer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a dealer and its invoices",
    description=(
        "Permanently deletes a dealer. invoices.dealer_id is ON DELETE SET "
        "NULL, but the dealer-or-supplier CHECK constraint then rejects that "
        "SET NULL for a dealer-direction invoice (supplier_id is also null) "
        "— so this deletes the dealer's invoices first (cascading to their "
        "line items and payments), then the dealer, in one commit. "
        "Irreversible — call the delete-preview endpoint first to see the "
        "impact."
    ),
)
async def delete_dealer(
    company_id: uuid.UUID,
    dealer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Response:
    await _get_company_or_404(company_id, db)
    await _get_dealer_or_404(company_id, dealer_id, db)

    deleted_invoices = await db.execute(delete(Invoice).where(Invoice.dealer_id == dealer_id))
    await db.execute(delete(Dealer).where(Dealer.id == dealer_id))
    await db.commit()
    logger.info(
        "Deleted dealer %s for company %s (cascaded %d invoices)",
        dealer_id,
        company_id,
        deleted_invoices.rowcount,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
