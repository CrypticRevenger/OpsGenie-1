"""Dashboard invoice routes — view + delete only, never create/edit.

Real invoice writes go through CSV/Excel import or the guided WhatsApp
workflows — see this project's "writes are workflows" principle. Listing
(filterable) is handled inline by company_detail's aggregator in
companies.py; this file only carries the delete action.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.exceptions import HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.invoices import delete_invoice as api_delete_invoice
from app.api.dashboard._shared import redirect_to_company
from app.db.session import get_db

router = APIRouter(prefix="/companies/{company_id}/invoices", tags=["dashboard:invoices"])


@router.post(
    "/{invoice_id}/delete",
    summary="Delete an invoice (cascades to its line items and payments)",
)
async def invoice_delete(
    company_id: uuid.UUID,
    invoice_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    try:
        await api_delete_invoice(company_id, invoice_id, db)
    except HTTPException as exc:
        return redirect_to_company(company_id, error=str(exc.detail))
    return redirect_to_company(company_id)
