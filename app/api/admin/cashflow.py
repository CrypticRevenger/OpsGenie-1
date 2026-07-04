"""Admin cashflow route — Phase 5A.

Read-only. Assembles BusinessSnapshotService's snapshot and
RecommendationEngine's ranked action list into one response. No LLM
involved — see app/services/snapshot.py and app/services/recommendations.py
for the deterministic logic this endpoint just exposes.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.company import Company
from app.schemas.cashflow import CashflowResponse
from app.services.recommendations import build_recommendations
from app.services.snapshot import build_snapshot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/companies/{company_id}", tags=["admin:cashflow"])


async def _get_company_or_404(company_id: uuid.UUID, db: AsyncSession) -> Company:
    company = await db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company {company_id} not found.",
        )
    return company


@router.get(
    "/cashflow",
    response_model=CashflowResponse,
    summary="Business snapshot and recommended actions for a company",
)
async def get_cashflow(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> CashflowResponse:
    await _get_company_or_404(company_id, db)

    snapshot = await build_snapshot(db, company_id)
    recommendations = build_recommendations(snapshot)

    return CashflowResponse(
        company_id=snapshot.company_id,
        generated_at=snapshot.generated_at,
        cash_available_today=snapshot.cash_available_today,
        expected_collections_7d=snapshot.expected_collections_7d,
        expected_collections_7d_total=snapshot.expected_collections_7d_total,
        expected_payments_7d=snapshot.expected_payments_7d,
        expected_payments_7d_total=snapshot.expected_payments_7d_total,
        net_cash_position=snapshot.net_cash_position,
        cash_deficit=snapshot.cash_deficit,
        overdue_dealers=snapshot.overdue_dealers,
        data_freshness_hours=snapshot.data_freshness_hours,
        data_completeness_score=snapshot.data_completeness_score,
        confidence_score=snapshot.confidence_score,
        recommendations=recommendations,
    )
