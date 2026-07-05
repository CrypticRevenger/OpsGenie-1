"""Admin FAQ routes.

A small per-company Q&A list the founder populates so the WhatsApp assistant
can answer policy-style questions from real, founder-approved text — see
app/services/agent/read_tools.py's get_faqs tool.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.company import Company
from app.models.faq import FAQ
from app.schemas.faq import FAQCreate, FAQResponse, FAQUpdate
from app.schemas.pagination import Page

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/companies/{company_id}/faqs", tags=["admin:faqs"])


async def _get_company_or_404(company_id: uuid.UUID, db: AsyncSession) -> Company:
    company = await db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company {company_id} not found.",
        )
    return company


async def _get_faq_or_404(company_id: uuid.UUID, faq_id: uuid.UUID, db: AsyncSession) -> FAQ:
    result = await db.execute(select(FAQ).where(FAQ.id == faq_id, FAQ.company_id == company_id))
    faq = result.scalar_one_or_none()
    if faq is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"FAQ {faq_id} not found in company {company_id}.",
        )
    return faq


@router.post(
    "",
    response_model=FAQResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a Q&A pair to a company's FAQ list",
)
async def create_faq(
    company_id: uuid.UUID,
    payload: FAQCreate,
    db: AsyncSession = Depends(get_db),
) -> FAQ:
    await _get_company_or_404(company_id, db)

    faq = FAQ(company_id=company_id, question=payload.question, answer=payload.answer)
    db.add(faq)
    await db.commit()
    await db.refresh(faq)
    logger.info("Created FAQ %s for company %s", faq.id, company_id)
    return faq


@router.get(
    "",
    response_model=Page[FAQResponse],
    summary="List FAQs for a company",
)
async def list_faqs(
    company_id: uuid.UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> Page[FAQResponse]:
    await _get_company_or_404(company_id, db)
    total = (
        await db.scalar(select(func.count()).select_from(FAQ).where(FAQ.company_id == company_id))
        or 0
    )
    result = await db.execute(
        select(FAQ)
        .where(FAQ.company_id == company_id)
        .order_by(FAQ.created_at)
        .offset((page - 1) * limit)
        .limit(limit)
    )
    faqs = list(result.scalars().all())
    return Page.create(items=faqs, total=total, page=page, limit=limit)


@router.patch(
    "/{faq_id}",
    response_model=FAQResponse,
    summary="Update a FAQ entry",
)
async def update_faq(
    company_id: uuid.UUID,
    faq_id: uuid.UUID,
    payload: FAQUpdate,
    db: AsyncSession = Depends(get_db),
) -> FAQ:
    await _get_company_or_404(company_id, db)
    faq = await _get_faq_or_404(company_id, faq_id, db)

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(faq, field, value)

    await db.commit()
    await db.refresh(faq)
    logger.info("Updated FAQ %s for company %s", faq.id, company_id)
    return faq


@router.delete(
    "/{faq_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a FAQ entry",
)
async def delete_faq(
    company_id: uuid.UUID,
    faq_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Response:
    await _get_company_or_404(company_id, db)
    faq = await _get_faq_or_404(company_id, faq_id, db)
    await db.delete(faq)
    await db.commit()
    logger.info("Deleted FAQ %s for company %s", faq_id, company_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
