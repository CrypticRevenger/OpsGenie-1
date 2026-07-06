"""Dashboard payment routes — view + delete only, never create/edit (see
app/api/dashboard/invoices.py's docstring for why).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.exceptions import HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.payments import delete_payment as api_delete_payment
from app.api.dashboard._shared import redirect_to_company
from app.db.session import get_db

router = APIRouter(prefix="/companies/{company_id}/payments", tags=["dashboard:payments"])


@router.post("/{payment_id}/delete", summary="Delete a payment")
async def payment_delete(
    company_id: uuid.UUID,
    payment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    try:
        await api_delete_payment(company_id, payment_id, db)
    except HTTPException as exc:
        return redirect_to_company(company_id, error=str(exc.detail))
    return redirect_to_company(company_id)
