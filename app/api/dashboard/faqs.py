"""Dashboard FAQ routes — create/edit/delete over app/api/admin/faq.py."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Form
from fastapi.exceptions import HTTPException
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.faq import create_faq as api_create_faq
from app.api.admin.faq import delete_faq as api_delete_faq
from app.api.admin.faq import update_faq as api_update_faq
from app.api.dashboard._shared import redirect_to_company
from app.db.session import get_db
from app.schemas.faq import FAQCreate, FAQUpdate

router = APIRouter(prefix="/companies/{company_id}/faqs", tags=["dashboard:faqs"])


@router.post("", summary="Add a Q&A pair to a company's FAQ list")
async def faq_create(
    company_id: uuid.UUID,
    question: str = Form(...),
    answer: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    try:
        payload = FAQCreate(question=question, answer=answer)
    except ValidationError as exc:
        return redirect_to_company(company_id, error=str(exc))
    try:
        await api_create_faq(company_id, payload, db)
    except HTTPException as exc:
        return redirect_to_company(company_id, error=str(exc.detail))
    return redirect_to_company(company_id)


@router.post("/{faq_id}/edit", summary="Update a FAQ entry")
async def faq_edit(
    company_id: uuid.UUID,
    faq_id: uuid.UUID,
    question: str = Form(""),
    answer: str = Form(""),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    fields: dict[str, object] = {}
    if question.strip():
        fields["question"] = question.strip()
    if answer.strip():
        fields["answer"] = answer.strip()

    try:
        payload = FAQUpdate(**fields)
    except ValidationError as exc:
        return redirect_to_company(company_id, error=str(exc))
    try:
        await api_update_faq(company_id, faq_id, payload, db)
    except HTTPException as exc:
        return redirect_to_company(company_id, error=str(exc.detail))
    return redirect_to_company(company_id)


@router.post("/{faq_id}/delete", summary="Delete a FAQ entry")
async def faq_delete(
    company_id: uuid.UUID,
    faq_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    try:
        await api_delete_faq(company_id, faq_id, db)
    except HTTPException as exc:
        return redirect_to_company(company_id, error=str(exc.detail))
    return redirect_to_company(company_id)
