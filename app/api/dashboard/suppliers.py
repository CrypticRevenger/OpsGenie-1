"""Dashboard supplier routes — same shape as dealers.py, supplier-flavored."""

from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.suppliers import create_supplier as api_create_supplier
from app.api.admin.suppliers import delete_supplier as api_delete_supplier
from app.api.admin.suppliers import supplier_delete_preview as api_supplier_delete_preview
from app.api.admin.suppliers import update_supplier as api_update_supplier
from app.api.dashboard._shared import redirect_to_company
from app.db.session import get_db
from app.schemas.supplier import SupplierCreate, SupplierUpdate

router = APIRouter(prefix="/companies/{company_id}/suppliers", tags=["dashboard:suppliers"])


def _s(v: str) -> str | None:
    return v.strip() or None


@router.post("", summary="Create a supplier")
async def supplier_create(
    company_id: uuid.UUID,
    name: str = Form(...),
    phone: str = Form(""),
    payment_terms_days: str = Form(""),
    credit_limit: str = Form(""),
    notes: str = Form(""),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    try:
        payload = SupplierCreate(
            name=name,
            phone=_s(phone),
            payment_terms_days=int(payment_terms_days) if payment_terms_days.strip() else None,
            credit_limit=Decimal(credit_limit) if credit_limit.strip() else None,
            notes=_s(notes),
        )
    except (ValueError, InvalidOperation, ValidationError) as exc:
        return redirect_to_company(company_id, error=str(exc))
    try:
        await api_create_supplier(company_id, payload, db)
    except HTTPException as exc:
        return redirect_to_company(company_id, error=str(exc.detail))
    return redirect_to_company(company_id)


@router.post("/{supplier_id}/edit", summary="Update a supplier")
async def supplier_edit(
    company_id: uuid.UUID,
    supplier_id: uuid.UUID,
    name: str = Form(""),
    phone: str = Form(""),
    payment_terms_days: str = Form(""),
    credit_limit: str = Form(""),
    notes: str = Form(""),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    fields: dict[str, object] = {}
    if name.strip():
        fields["name"] = name.strip()
    if phone.strip():
        fields["phone"] = phone.strip()
    if payment_terms_days.strip():
        try:
            fields["payment_terms_days"] = int(payment_terms_days)
        except ValueError as exc:
            return redirect_to_company(company_id, error=str(exc))
    if credit_limit.strip():
        try:
            fields["credit_limit"] = Decimal(credit_limit)
        except InvalidOperation as exc:
            return redirect_to_company(company_id, error=str(exc))
    if notes.strip():
        fields["notes"] = notes.strip()

    try:
        payload = SupplierUpdate(**fields)
    except ValidationError as exc:
        return redirect_to_company(company_id, error=str(exc))
    try:
        await api_update_supplier(company_id, supplier_id, payload, db)
    except HTTPException as exc:
        return redirect_to_company(company_id, error=str(exc.detail))
    return redirect_to_company(company_id)


@router.post("/{supplier_id}/delete", summary="Delete a supplier and its invoices")
async def supplier_delete(
    company_id: uuid.UUID,
    supplier_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    try:
        await api_delete_supplier(company_id, supplier_id, db)
    except HTTPException as exc:
        return redirect_to_company(company_id, error=str(exc.detail))
    return redirect_to_company(company_id)


@router.get(
    "/{supplier_id}/delete-preview",
    summary="Pre-delete impact summary (JSON — fetched by dashboard.js before confirm())",
)
async def supplier_delete_preview(
    company_id: uuid.UUID,
    supplier_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    data = await api_supplier_delete_preview(company_id, supplier_id, db)
    return JSONResponse(
        content={"invoice_count": data["invoice_count"], "total_amount": str(data["total_amount"])}
    )
