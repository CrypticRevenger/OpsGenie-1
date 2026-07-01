"""Admin dealer routes.

Dealers are created scoped to a specific company.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.company import Company
from app.models.dealer import Dealer
from app.schemas.dealer import DealerCreate, DealerResponse

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
    response_model=list[DealerResponse],
    summary="List dealers for a company",
)
async def list_dealers(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[Dealer]:
    await _get_company_or_404(company_id, db)
    result = await db.execute(
        select(Dealer)
        .where(Dealer.company_id == company_id)
        .order_by(Dealer.name)
    )
    return list(result.scalars().all())


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
