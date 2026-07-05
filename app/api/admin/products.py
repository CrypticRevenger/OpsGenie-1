"""Admin product routes.

Products are created scoped to a specific company. This is the first admin
endpoint set with a PATCH — used to set/adjust selling_price and
stock_quantity for products the guided WhatsApp onboarding created with a
name only (see app/services/onboarding_flow.py) or to restock after a sale.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.company import Company
from app.models.product import Product
from app.schemas.pagination import Page
from app.schemas.product import ProductCreate, ProductResponse, ProductUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/companies/{company_id}/products", tags=["admin:products"])


async def _get_company_or_404(company_id: uuid.UUID, db: AsyncSession) -> Company:
    company = await db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company {company_id} not found.",
        )
    return company


async def _get_product_or_404(
    company_id: uuid.UUID, product_id: uuid.UUID, db: AsyncSession
) -> Product:
    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.company_id == company_id)
    )
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product {product_id} not found in company {company_id}.",
        )
    return product


@router.post(
    "",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a product to a company's catalogue",
)
async def create_product(
    company_id: uuid.UUID,
    payload: ProductCreate,
    db: AsyncSession = Depends(get_db),
) -> Product:
    await _get_company_or_404(company_id, db)

    product = Product(
        company_id=company_id,
        name=payload.name,
        unit=payload.unit,
        selling_price=payload.selling_price,
        purchase_price=payload.purchase_price,
        stock_quantity=payload.stock_quantity,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    logger.info("Created product %s for company %s", product.name, company_id)
    return product


@router.get(
    "",
    response_model=Page[ProductResponse],
    summary="List products for a company",
)
async def list_products(
    company_id: uuid.UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> Page[ProductResponse]:
    await _get_company_or_404(company_id, db)
    total = (
        await db.scalar(
            select(func.count()).select_from(Product).where(Product.company_id == company_id)
        )
        or 0
    )
    result = await db.execute(
        select(Product)
        .where(Product.company_id == company_id)
        .order_by(Product.name)
        .offset((page - 1) * limit)
        .limit(limit)
    )
    products = list(result.scalars().all())
    return Page.create(items=products, total=total, page=page, limit=limit)


@router.get(
    "/{product_id}",
    response_model=ProductResponse,
    summary="Get a product by ID",
)
async def get_product(
    company_id: uuid.UUID,
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Product:
    await _get_company_or_404(company_id, db)
    return await _get_product_or_404(company_id, product_id, db)


@router.patch(
    "/{product_id}",
    response_model=ProductResponse,
    summary="Update a product (e.g. set price or restock)",
)
async def update_product(
    company_id: uuid.UUID,
    product_id: uuid.UUID,
    payload: ProductUpdate,
    db: AsyncSession = Depends(get_db),
) -> Product:
    await _get_company_or_404(company_id, db)
    product = await _get_product_or_404(company_id, product_id, db)

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(product, field, value)

    await db.commit()
    await db.refresh(product)
    logger.info("Updated product %s for company %s", product.id, company_id)
    return product
