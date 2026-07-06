"""Dashboard import route — CSV/Excel upload form over
app/api/admin/imports.py::import_file.
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.exceptions import HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.imports import import_file as api_import_file
from app.api.dashboard._shared import redirect_to_company
from app.db.session import get_db

router = APIRouter(prefix="/companies/{company_id}/import", tags=["dashboard:imports"])


@router.post("", summary="Upload a CSV/Excel file of invoices or payments")
async def import_upload(
    company_id: uuid.UUID,
    direction: Literal["receivable", "payable"] = Form(...),
    file_kind: Literal["invoices", "payments"] = Form("invoices"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    try:
        result = await api_import_file(
            company_id, direction=direction, file_kind=file_kind, file=file, db=db
        )
    except HTTPException as exc:
        return redirect_to_company(company_id, error=str(exc.detail))
    if result.rows_failed:
        return redirect_to_company(
            company_id,
            error=(
                f"Import finished with {result.rows_failed} failed row(s) out of "
                f"{result.rows_processed} — {result.rows_succeeded} succeeded."
            ),
        )
    return redirect_to_company(company_id)
