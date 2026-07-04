"""Admin invoice-follow-up trigger route — Phase 9.

POST manually triggers InvoiceDueDateFollowUpService for one company (real
WhatsApp send, real DB write) — mirrors app/api/admin/briefing.py's manual
POST pattern used before any scheduler exists. SPEC's Step 15 (APScheduler
daily dispatch) is separate and still not built; a scheduler can call
send_due_today_follow_up directly without touching this endpoint.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.company import Company
from app.schemas.followup import FollowUpSendResponse
from app.services.followup import send_due_today_follow_up

router = APIRouter(prefix="/companies/{company_id}", tags=["admin:followup"])


async def _get_company_or_404(company_id: uuid.UUID, db: AsyncSession) -> Company:
    company = await db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company {company_id} not found.",
        )
    return company


@router.post(
    "/follow-ups/send-due-today",
    response_model=FollowUpSendResponse,
    summary="Send the next due-today invoice follow-up for this company (real WhatsApp send)",
)
async def send_due_today_follow_ups(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> FollowUpSendResponse:
    await _get_company_or_404(company_id, db)
    result = await send_due_today_follow_up(db, company_id)
    await db.commit()
    return FollowUpSendResponse(status=result.status, invoice_number=result.invoice_number)
