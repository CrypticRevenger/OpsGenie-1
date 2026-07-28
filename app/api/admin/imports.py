"""Admin import routes.

Founder-only endpoint (no auth in V0.0/V0.1, same as companies/dealers/suppliers).
Accepts a Tally, Vyapar, or OpsGenie-canonical CSV/Excel export and persists it
through ImportEngine.
"""

from __future__ import annotations

import logging
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.company import Company
from app.schemas.import_result import ImportResponse, ImportRowError
from app.services.importer.engine import UnrecognisedFormatError, UnsupportedFileError, run_import
from app.services.importer.log_writer import write_import_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/companies/{company_id}", tags=["admin:imports"])

# Real Tally/Vyapar exports are well under a megabyte; 10 MB is generous
# headroom. The cap stops an oversized upload from being read whole into
# memory (parse_file loads the entire file), which would otherwise be an
# availability risk on an unauthenticated endpoint.
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024


async def _get_company_or_404(company_id: uuid.UUID, db: AsyncSession) -> Company:
    company = await db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company {company_id} not found.",
        )
    return company


@router.post(
    "/import",
    response_model=ImportResponse,
    summary="Import a CSV/Excel/PDF file of invoices, payments, or products",
    description=(
        "Accepts a Tally, Vyapar, or OpsGenie-canonical CSV/Excel export, or a "
        "Tally-style PDF (voucher/invoice printouts, or a 'Stock Group Summary' "
        "report for file_kind=products — see app/services/importer/"
        "pdf_extractor.py) for any file_kind. "
        "One bad row (or unparseable PDF page) never fails the whole file — "
        "failures are reported per row, not raised. Re-uploading the same file "
        "is safe (idempotent)."
    ),
)
async def import_file(
    company_id: uuid.UUID,
    direction: Literal["receivable", "payable"] | None = Query(
        None,
        description="receivable = dealer invoices/payments, payable = supplier. "
        "Required unless file_kind=products.",
    ),
    file_kind: Literal["invoices", "payments", "products"] = Query(
        "invoices",
        description="Whether this file contains invoices, payments, or a product/stock catalogue",
    ),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> ImportResponse:
    await _get_company_or_404(company_id, db)
    if file_kind != "products" and direction is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="direction is required unless file_kind=products.",
        )

    # Bounded read: pull at most the limit + 1 byte. If we get more than the
    # limit, the file is too big — reject without having buffered it all.
    contents = await file.read(_MAX_UPLOAD_BYTES + 1)
    if len(contents) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds the {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit.",
        )
    try:
        result = await run_import(
            db,
            company_id=company_id,
            direction=direction,
            file_kind=file_kind,
            filename=file.filename or "upload",
            contents=contents,
        )
    except (UnsupportedFileError, UnrecognisedFormatError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await write_import_log(db, company_id, result)

    logger.info(
        "Import %s for company %s: %d processed, %d succeeded, %d skipped, %d failed",
        result.filename,
        company_id,
        result.rows_processed,
        result.rows_succeeded,
        result.rows_skipped,
        result.rows_failed,
    )

    return ImportResponse(
        filename=result.filename,
        source_format=result.source_format,
        rows_processed=result.rows_processed,
        rows_succeeded=result.rows_succeeded,
        rows_skipped=result.rows_skipped,
        rows_failed=result.rows_failed,
        errors=[ImportRowError(row=e.row_number, reason=e.reason) for e in result.errors],
    )
