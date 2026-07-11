"""Public, signed-link company data export — the WhatsApp-facing entry point.

Not under /admin (no X-API-Key — a distributor has no dashboard login) and
not a stored/permanent token: `company_id`/`expires_at`/`signature` are
verified statelessly by app/services/company_export.py::verify_export_link,
the same HMAC-signing convention app/api/webhooks/whatsapp.py already uses to
verify Meta's own payloads. A link is only ever valid for
EXPORT_LINK_TTL_MINUTES (default 30) from the moment it was generated.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.business_event import BusinessEvent, BusinessEventType
from app.models.company import Company
from app.services.company_export import build_company_workbook, verify_export_link

logger = logging.getLogger(__name__)

router = APIRouter()

_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get(
    "/export/{company_id}/{expires_at}/{signature}",
    summary="Download a company's Excel data export via a short-lived signed link",
)
async def download_company_export(
    company_id: uuid.UUID,
    expires_at: int,
    signature: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    if not verify_export_link(company_id, expires_at, signature):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Link is invalid or has expired."
        )

    company = await db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found.")

    workbook_bytes = await build_company_workbook(db, company)
    db.add(
        BusinessEvent(
            company_id=company.id,
            event_type=BusinessEventType.export_downloaded,
            entity_type="company",
            entity_id=company.id,
            payload={"source": "whatsapp_signed_link"},
            created_by="export_api",
        )
    )
    await db.commit()

    filename = f"{company.business_name.replace(' ', '_')}_export.xlsx"
    return Response(
        content=workbook_bytes,
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
