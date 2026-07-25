"""Public, signed-link company data export — the WhatsApp-facing entry point.

Not under /admin (no X-API-Key — a distributor has no dashboard login) and
not a stored/permanent token: `company_id`/`expires_at`/`signature` are
verified statelessly by app/services/company_export.py::verify_export_link,
the same HMAC-signing convention app/api/webhooks/whatsapp.py already uses to
verify Meta's own payloads. A link is only ever valid for
EXPORT_LINK_TTL_MINUTES (default 30) from the moment it was generated.

`report`/`format`/`from`/`to`/`month` are optional query params, not part of
the signed path — see company_export.py::generate_export_link's docstring for
why that's safe. `party` is different: it's passed through to
verify_export_link and must match what was actually signed, so a link issued
for one party can't be edited to read another party's data. No query params
at all reproduces the original, single all-time-workbook behavior exactly
(report defaults to "full"). Report metadata (display name, which builder,
whether a party/PDF is required) all comes from
app.services.reports.registry.REPORTS — this route has no per-report
branching of its own.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._shared import content_disposition
from app.db.session import get_db
from app.models.business_event import BusinessEvent, BusinessEventType
from app.models.company import Company
from app.services.company_export import verify_export_link
from app.services.party_lookup import get_party_by_id
from app.services.reports.period import InvalidPeriodError, resolve_period
from app.services.reports.registry import REPORTS, ReportContext

logger = logging.getLogger(__name__)

router = APIRouter()

_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_PDF_MEDIA_TYPE = "application/pdf"


@router.get(
    "/export/{company_id}/{expires_at}/{signature}",
    summary="Download a company's Excel/PDF data export via a short-lived signed link",
)
async def download_company_export(
    company_id: uuid.UUID,
    expires_at: int,
    signature: str,
    report: str = "full",
    format: str = "xlsx",
    month: str | None = None,
    from_date: str | None = Query(default=None, alias="from"),
    to_date: str | None = Query(default=None, alias="to"),
    party: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
) -> Response:
    if not verify_export_link(company_id, expires_at, signature, party_id=party):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Link is invalid or has expired."
        )

    company = await db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found.")

    spec = REPORTS.get(report)
    if spec is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown report '{report}'."
        )
    if format not in ("xlsx", "pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown format '{format}'."
        )
    if format == "pdf" and spec.build_pdf is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"'{report}' has no PDF version."
        )

    party_obj = None
    direction = None
    if spec.needs_party:
        if party is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"'{report}' requires a 'party' id.",
            )
        match = await get_party_by_id(db, company_id, party)
        if match is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Party not found.")
        party_obj, direction = match

    try:
        period = resolve_period(from_str=from_date, to_str=to_date, month_str=month)
    except InvalidPeriodError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    builder = spec.build_pdf if format == "pdf" else spec.build_xlsx
    ctx = ReportContext(period=period, party=party_obj, direction=direction)
    file_bytes = await builder(db, company, ctx)

    db.add(
        BusinessEvent(
            company_id=company.id,
            event_type=BusinessEventType.export_downloaded,
            entity_type="company",
            entity_id=company.id,
            payload={"source": "whatsapp_signed_link", "report_type": report},
            created_by="export_api",
        )
    )
    await db.commit()

    media_type = _PDF_MEDIA_TYPE if format == "pdf" else _XLSX_MEDIA_TYPE
    extension = "pdf" if format == "pdf" else "xlsx"
    suffix = "" if report == "full" else f"_{report}"
    filename = f"{company.business_name.replace(' ', '_')}{suffix}_export.{extension}"
    return Response(
        content=file_bytes,
        media_type=media_type,
        headers={"Content-Disposition": content_disposition(filename)},
    )
