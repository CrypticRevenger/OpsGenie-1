"""Admin company data export route — behind the shared X-API-Key like every
other /admin/* route (wired once in app/main.py), so no signed link is
needed here — see app/api/export.py for the WhatsApp-facing signed-link
counterpart.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._shared import content_disposition
from app.db.session import get_db
from app.models.business_event import BusinessEvent, BusinessEventType
from app.models.company import Company
from app.services.company_export import build_company_workbook

router = APIRouter(prefix="/companies/{company_id}", tags=["admin:export"])

_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/export", summary="Download this company's Excel data export")
async def download_company_export(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Response:
    company = await db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Company {company_id} not found."
        )

    workbook_bytes = await build_company_workbook(db, company)
    db.add(
        BusinessEvent(
            company_id=company.id,
            event_type=BusinessEventType.export_downloaded,
            entity_type="company",
            entity_id=company.id,
            payload={"source": "admin_api"},
            created_by="admin_export",
        )
    )
    await db.commit()

    filename = f"{company.business_name.replace(' ', '_')}_export.xlsx"
    return Response(
        content=workbook_bytes,
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": content_disposition(filename)},
    )
