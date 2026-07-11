"""Admin Daily Business Summary routes — read-only snapshot views + a manual
evening-brief trigger. No LLM involved — see app/services/daily_snapshot.py
and app/services/evening_brief.py for the deterministic logic this endpoint
exposes.
"""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.company import Company
from app.models.daily_business_snapshot import DailyBusinessSnapshot
from app.schemas.daily_snapshot import (
    DailySnapshotResponse,
    EveningBriefSendResponse,
    MonthSummaryResponse,
    MonthToDateTotals,
)
from app.services.daily_snapshot import compute_daily_snapshot, month_to_date_totals
from app.services.evening_brief import send_evening_brief
from app.services.snapshot import business_now

router = APIRouter(prefix="/companies/{company_id}", tags=["admin:daily-snapshot"])


async def _get_company_or_404(company_id: uuid.UUID, db: AsyncSession) -> Company:
    company = await db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company {company_id} not found.",
        )
    return company


@router.get(
    "/daily-snapshot/today",
    response_model=DailySnapshotResponse,
    summary="Today's live Daily Business Summary (Sales, Margin, Cash Movement, Outstanding)",
)
async def get_today_snapshot(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> DailySnapshotResponse:
    company = await _get_company_or_404(company_id, db)
    today = business_now(company.timezone).date()
    result = await compute_daily_snapshot(db, company, today)
    return DailySnapshotResponse(**result.__dict__)


@router.get(
    "/daily-snapshot/month-summary",
    response_model=MonthSummaryResponse,
    summary="Month-to-date Daily Business Summary totals + day-by-day finalized rows",
)
async def get_month_summary(
    company_id: uuid.UUID,
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    db: AsyncSession = Depends(get_db),
) -> MonthSummaryResponse:
    company = await _get_company_or_404(company_id, db)
    totals = await month_to_date_totals(db, company, year, month)

    month_start = date(year, month, 1)
    next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    rows = (
        (
            await db.execute(
                select(DailyBusinessSnapshot)
                .where(
                    DailyBusinessSnapshot.company_id == company_id,
                    DailyBusinessSnapshot.business_date >= month_start,
                    DailyBusinessSnapshot.business_date < next_month,
                )
                .order_by(DailyBusinessSnapshot.business_date)
            )
        )
        .scalars()
        .all()
    )

    return MonthSummaryResponse(
        year=year,
        month=month,
        totals=MonthToDateTotals(**totals),
        days=[DailySnapshotResponse.model_validate(row) for row in rows],
    )


@router.post(
    "/evening-brief/send",
    response_model=EveningBriefSendResponse,
    summary="Manually send today's Evening Business Summary (real WhatsApp send)",
)
async def send_evening_brief_now(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> EveningBriefSendResponse:
    company = await _get_company_or_404(company_id, db)
    sent = await send_evening_brief(db, company)
    await db.commit()
    return EveningBriefSendResponse(sent=sent)
