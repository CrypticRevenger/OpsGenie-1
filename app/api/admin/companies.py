"""Admin company routes.

Founder-only endpoints.  No authentication required for pilot (V0.0).
Founder creates companies via these endpoints directly — no self-serve
onboarding in V0.0 or V0.1.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.company import Company
from app.schemas.company import CompanyCreate, CompanyResponse
from app.schemas.pagination import Page

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/companies", tags=["admin:companies"])


@router.post(
    "",
    response_model=CompanyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a company",
    description="Register a new B2B distributor company. whatsapp_number must be unique.",
)
async def create_company(
    payload: CompanyCreate,
    db: AsyncSession = Depends(get_db),
) -> Company:
    company = Company(
        business_name=payload.business_name,
        owner_name=payload.owner_name,
        whatsapp_number=payload.whatsapp_number,
        email=payload.email,
        business_type=payload.business_type,
        preferred_language=payload.preferred_language,
        timezone=payload.timezone,
        opening_balance=payload.opening_balance,
    )
    db.add(company)
    try:
        await db.commit()
        await db.refresh(company)
    except IntegrityError as err:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A company with WhatsApp number '{payload.whatsapp_number}' already exists.",
        ) from err
    logger.info("Created company %s (%s)", company.business_name, company.id)
    return company


@router.get(
    "",
    response_model=Page[CompanyResponse],
    summary="List all companies",
)
async def list_companies(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> Page[CompanyResponse]:
    total = await db.scalar(select(func.count()).select_from(Company)) or 0
    result = await db.execute(
        select(Company).order_by(Company.created_at.desc()).offset((page - 1) * limit).limit(limit)
    )
    companies = list(result.scalars().all())
    return Page.create(items=companies, total=total, page=page, limit=limit)


@router.get(
    "/{company_id}",
    response_model=CompanyResponse,
    summary="Get a company by ID",
)
async def get_company(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Company:
    company = await db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company {company_id} not found.",
        )
    return company


@router.delete(
    "/{company_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a company and all its data",
    description=(
        "Permanently deletes a company and everything scoped to it — dealers, "
        "suppliers, invoices, payments, business events, activity timeline, "
        "briefings, imports, and notification logs — via database cascade. "
        "Irreversible."
    ),
)
async def delete_company(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Response:
    company = await db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company {company_id} not found.",
        )
    # Core DELETE (not db.delete(company)) so the whole subtree is removed by
    # Postgres ON DELETE CASCADE in one statement — the ORM cascade would try
    # to lazy-load every child collection, which raises under async. Postgres
    # resolves the Phase 9 circular FK (companies.pending_follow_up_invoice_id
    # -> invoices) and the invoice dealer/supplier CHECK correctly on its own
    # (verified against real data).
    await db.execute(delete(Company).where(Company.id == company_id))
    await db.commit()
    logger.info("Deleted company %s (%s)", company.business_name, company_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
