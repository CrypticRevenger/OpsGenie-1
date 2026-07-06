"""Dashboard briefing route — manually (re)generate a company's morning
briefing. Viewing the latest one is handled inline by company_detail's
aggregator in companies.py; this file only carries the generate action
(a real LLM call — same cost as the admin API's POST).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.exceptions import HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.briefing import create_briefing as api_create_briefing
from app.api.dashboard._shared import redirect_to_company
from app.db.session import get_db

router = APIRouter(prefix="/companies/{company_id}/briefing", tags=["dashboard:briefing"])


@router.post(
    "/generate",
    summary="Generate a new morning briefing (calls the LLM provider chain — real cost)",
)
async def briefing_generate(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    try:
        await api_create_briefing(company_id, db)
    except HTTPException as exc:
        return redirect_to_company(company_id, error=str(exc.detail))
    return redirect_to_company(company_id)
