"""Admin morning briefing routes — Phase 5B.

POST generates a new briefing (calls the configured LLM provider chain —
real cost, real DB write). GET reads the most recently generated one — free,
no network call.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.company import Company
from app.models.morning_briefing import MorningBriefing
from app.schemas.briefing import MorningBriefingResponse
from app.services.briefing import (
    AllProvidersExhaustedError,
    NoApiKeyConfiguredError,
    find_unverified_amounts,
    generate_briefing,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/companies/{company_id}", tags=["admin:briefing"])


async def _get_company_or_404(company_id: uuid.UUID, db: AsyncSession) -> Company:
    company = await db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company {company_id} not found.",
        )
    return company


def _to_response(briefing: MorningBriefing) -> MorningBriefingResponse:
    # snapshot_json is exactly the payload sent to Claude — recompute the
    # traceability check from the persisted data rather than storing it as
    # its own column, so it's never stale relative to generated_text.
    unverified = find_unverified_amounts(briefing.generated_text, briefing.snapshot_json)
    return MorningBriefingResponse(
        id=briefing.id,
        company_id=briefing.company_id,
        generated_text=briefing.generated_text,
        confidence_score=briefing.confidence_score,
        data_freshness_hours=briefing.data_freshness_hours,
        sent_at=briefing.sent_at,
        delivery_status=briefing.delivery_status,
        created_at=briefing.created_at,
        unverified_amounts=unverified,
    )


@router.post(
    "/briefing",
    response_model=MorningBriefingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a new morning briefing (calls the LLM provider chain — real cost)",
)
async def create_briefing(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> MorningBriefingResponse:
    await _get_company_or_404(company_id, db)
    try:
        briefing = await generate_briefing(db, company_id)
    except (NoApiKeyConfiguredError, AllProvidersExhaustedError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    return _to_response(briefing)


@router.get(
    "/briefing",
    response_model=MorningBriefingResponse,
    summary="Get the most recently generated morning briefing (no network call)",
)
async def get_latest_briefing(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> MorningBriefingResponse:
    await _get_company_or_404(company_id, db)
    briefing = await db.scalar(
        select(MorningBriefing)
        .where(MorningBriefing.company_id == company_id)
        .order_by(MorningBriefing.created_at.desc())
        .limit(1)
    )
    if briefing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No briefing has been generated yet for company {company_id}.",
        )
    return _to_response(briefing)
