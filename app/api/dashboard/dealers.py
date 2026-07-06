"""Dashboard dealer routes — create/edit/delete forms over
app/api/admin/dealers.py, plus a JSON delete-preview passthrough that
dashboard.js fetches to show the real cascade-delete impact before
confirm() (see contiune.md's dealer/supplier delete landmine).
"""

from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.dealers import create_dealer as api_create_dealer
from app.api.admin.dealers import dealer_delete_preview as api_dealer_delete_preview
from app.api.admin.dealers import delete_dealer as api_delete_dealer
from app.api.admin.dealers import update_dealer as api_update_dealer
from app.api.dashboard._shared import redirect_to_company
from app.db.session import get_db
from app.schemas.dealer import DealerCreate, DealerUpdate

router = APIRouter(prefix="/companies/{company_id}/dealers", tags=["dashboard:dealers"])


def _s(v: str) -> str | None:
    return v.strip() or None


@router.post("", summary="Create a dealer")
async def dealer_create(
    company_id: uuid.UUID,
    name: str = Form(...),
    phone: str = Form(""),
    address: str = Form(""),
    gst_number: str = Form(""),
    payment_terms_days: str = Form(""),
    credit_limit: str = Form(""),
    notes: str = Form(""),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    try:
        payload = DealerCreate(
            name=name,
            phone=_s(phone),
            address=_s(address),
            gst_number=_s(gst_number),
            payment_terms_days=int(payment_terms_days) if payment_terms_days.strip() else None,
            credit_limit=Decimal(credit_limit) if credit_limit.strip() else None,
            notes=_s(notes),
        )
    except (ValueError, InvalidOperation, ValidationError) as exc:
        return redirect_to_company(company_id, error=str(exc))
    try:
        await api_create_dealer(company_id, payload, db)
    except HTTPException as exc:
        return redirect_to_company(company_id, error=str(exc.detail))
    return redirect_to_company(company_id)


@router.post("/{dealer_id}/edit", summary="Update a dealer")
async def dealer_edit(
    company_id: uuid.UUID,
    dealer_id: uuid.UUID,
    name: str = Form(""),
    phone: str = Form(""),
    address: str = Form(""),
    gst_number: str = Form(""),
    payment_terms_days: str = Form(""),
    credit_limit: str = Form(""),
    notes: str = Form(""),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    # Only fields the founder actually typed something into are sent to
    # DealerUpdate, so exclude_unset=True downstream leaves everything else
    # untouched — the edit form is pre-filled with current values, so a
    # blank field here means "didn't touch this," not "clear it."
    fields: dict[str, object] = {}
    if name.strip():
        fields["name"] = name.strip()
    if phone.strip():
        fields["phone"] = phone.strip()
    if address.strip():
        fields["address"] = address.strip()
    if gst_number.strip():
        fields["gst_number"] = gst_number.strip()
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
        payload = DealerUpdate(**fields)
    except ValidationError as exc:
        return redirect_to_company(company_id, error=str(exc))
    try:
        await api_update_dealer(company_id, dealer_id, payload, db)
    except HTTPException as exc:
        return redirect_to_company(company_id, error=str(exc.detail))
    return redirect_to_company(company_id)


@router.post("/{dealer_id}/delete", summary="Delete a dealer and its invoices")
async def dealer_delete(
    company_id: uuid.UUID,
    dealer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    try:
        await api_delete_dealer(company_id, dealer_id, db)
    except HTTPException as exc:
        return redirect_to_company(company_id, error=str(exc.detail))
    return redirect_to_company(company_id)


@router.get(
    "/{dealer_id}/delete-preview",
    summary="Pre-delete impact summary (JSON — fetched by dashboard.js before confirm())",
)
async def dealer_delete_preview(
    company_id: uuid.UUID,
    dealer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    data = await api_dealer_delete_preview(company_id, dealer_id, db)
    return JSONResponse(
        content={"invoice_count": data["invoice_count"], "total_amount": str(data["total_amount"])}
    )
