"""Admin supplier routes.

Suppliers are created scoped to a specific company.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.company import Company
from app.models.supplier import Supplier
from app.schemas.pagination import Page
from app.schemas.supplier import SupplierCreate, SupplierResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/companies/{company_id}/suppliers", tags=["admin:suppliers"])


async def _get_company_or_404(company_id: uuid.UUID, db: AsyncSession) -> Company:
    company = await db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company {company_id} not found.",
        )
    return company


@router.post(
    "",
    response_model=SupplierResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a supplier to a company",
)
async def create_supplier(
    company_id: uuid.UUID,
    payload: SupplierCreate,
    db: AsyncSession = Depends(get_db),
) -> Supplier:
    await _get_company_or_404(company_id, db)

    supplier = Supplier(
        company_id=company_id,
        name=payload.name,
        phone=payload.phone,
        payment_terms_days=payload.payment_terms_days,
        credit_limit=payload.credit_limit,
        notes=payload.notes,
    )
    db.add(supplier)
    await db.commit()
    await db.refresh(supplier)
    logger.info("Created supplier %s for company %s", supplier.name, company_id)
    return supplier


@router.get(
    "",
    response_model=Page[SupplierResponse],
    summary="List suppliers for a company",
)
async def list_suppliers(
    company_id: uuid.UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> Page[SupplierResponse]:
    await _get_company_or_404(company_id, db)
    total = await db.scalar(
        select(func.count()).select_from(Supplier).where(Supplier.company_id == company_id)
    ) or 0
    result = await db.execute(
        select(Supplier)
        .where(Supplier.company_id == company_id)
        .order_by(Supplier.name)
        .offset((page - 1) * limit)
        .limit(limit)
    )
    suppliers = list(result.scalars().all())
    return Page.create(items=suppliers, total=total, page=page, limit=limit)


@router.get(
    "/{supplier_id}",
    response_model=SupplierResponse,
    summary="Get a supplier by ID",
)
async def get_supplier(
    company_id: uuid.UUID,
    supplier_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Supplier:
    await _get_company_or_404(company_id, db)
    result = await db.execute(
        select(Supplier).where(
            Supplier.id == supplier_id, Supplier.company_id == company_id
        )
    )
    supplier = result.scalar_one_or_none()
    if supplier is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Supplier {supplier_id} not found in company {company_id}.",
        )
    return supplier
