"""Dashboard product routes — create/edit/delete over app/api/admin/products.py.

No delete-preview here (unlike dealers/suppliers): product delete is a plain
row delete, invoice_items.product_id just goes null (SET NULL, no CHECK
constraint) — see contiune.md's delete-landmine section.
"""

from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form
from fastapi.exceptions import HTTPException
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.products import create_product as api_create_product
from app.api.admin.products import delete_product as api_delete_product
from app.api.admin.products import update_product as api_update_product
from app.api.dashboard._shared import redirect_to_company
from app.db.session import get_db
from app.schemas.product import ProductCreate, ProductUpdate

router = APIRouter(prefix="/companies/{company_id}/products", tags=["dashboard:products"])


def _s(v: str) -> str | None:
    return v.strip() or None


@router.post("", summary="Create a product")
async def product_create(
    company_id: uuid.UUID,
    name: str = Form(...),
    unit: str = Form(""),
    selling_price: str = Form(""),
    purchase_price: str = Form(""),
    stock_quantity: str = Form("0"),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    try:
        payload = ProductCreate(
            name=name,
            unit=_s(unit),
            selling_price=Decimal(selling_price) if selling_price.strip() else None,
            purchase_price=Decimal(purchase_price) if purchase_price.strip() else None,
            stock_quantity=Decimal(stock_quantity) if stock_quantity.strip() else Decimal("0"),
        )
    except (ValueError, InvalidOperation, ValidationError) as exc:
        return redirect_to_company(company_id, error=str(exc))
    try:
        await api_create_product(company_id, payload, db)
    except HTTPException as exc:
        return redirect_to_company(company_id, error=str(exc.detail))
    return redirect_to_company(company_id)


@router.post("/{product_id}/edit", summary="Update a product (e.g. set price or restock)")
async def product_edit(
    company_id: uuid.UUID,
    product_id: uuid.UUID,
    name: str = Form(""),
    unit: str = Form(""),
    selling_price: str = Form(""),
    purchase_price: str = Form(""),
    stock_quantity: str = Form(""),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    fields: dict[str, object] = {}
    if name.strip():
        fields["name"] = name.strip()
    if unit.strip():
        fields["unit"] = unit.strip()
    try:
        if selling_price.strip():
            fields["selling_price"] = Decimal(selling_price)
        if purchase_price.strip():
            fields["purchase_price"] = Decimal(purchase_price)
        if stock_quantity.strip():
            fields["stock_quantity"] = Decimal(stock_quantity)
    except InvalidOperation as exc:
        return redirect_to_company(company_id, error=str(exc))

    try:
        payload = ProductUpdate(**fields)
    except ValidationError as exc:
        return redirect_to_company(company_id, error=str(exc))
    try:
        await api_update_product(company_id, product_id, payload, db)
    except HTTPException as exc:
        return redirect_to_company(company_id, error=str(exc.detail))
    return redirect_to_company(company_id)


@router.post("/{product_id}/delete", summary="Delete a product")
async def product_delete(
    company_id: uuid.UUID,
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    try:
        await api_delete_product(company_id, product_id, db)
    except HTTPException as exc:
        return redirect_to_company(company_id, error=str(exc.detail))
    return redirect_to_company(company_id)
