"""Dashboard follow-up route — manually trigger today's due-invoice
follow-up send (real WhatsApp message) for one company.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.exceptions import HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.followup import send_due_today_follow_ups as api_send_due_today_follow_ups
from app.api.dashboard._shared import redirect_to_company
from app.db.session import get_db

router = APIRouter(prefix="/companies/{company_id}/follow-ups", tags=["dashboard:followup"])


@router.post(
    "/send-due-today",
    summary="Send the next due-today invoice follow-up for this company (real WhatsApp send)",
)
async def followup_send_due_today(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    try:
        result = await api_send_due_today_follow_ups(company_id, db)
    except HTTPException as exc:
        return redirect_to_company(company_id, error=str(exc.detail))
    if result.status != "sent":
        return redirect_to_company(company_id, error=f"Follow-up not sent: {result.status}")
    return redirect_to_company(company_id)
