"""Public self-serve onboarding — the /onboard wizard + its two endpoints.

Outside the admin router (no X-API-Key) so distributors can reach it; the
onboarding_enabled kill-switch is its only gate. POST /onboard stores a
pending company (subscription_active=False); POST /onboard/{id}/activate is
the wizard's final "Activate Account" step — fully self-serve, no founder
review — which shares app/services/activation.py's activate_company with the
founder-only admin route, so both flip the flag and send the welcome template
identically.
"""

from __future__ import annotations

import logging
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.templates import templates
from app.db.session import get_db
from app.models.company import Company, OnboardingState
from app.schemas.company import SubscriptionResponse
from app.schemas.import_result import ImportResponse, ImportRowError
from app.schemas.onboarding import (
    OnboardImportResponse,
    OnboardImportSummary,
    OnboardRequest,
    OnboardResponse,
)
from app.services.activation import activate_company
from app.services.importer.engine import UnrecognisedFormatError, UnsupportedFileError, run_import
from app.services.importer.log_writer import write_import_log
from app.services.onboarding import (
    FounderNumberConflictError,
    InvalidPhoneNumberError,
    OnboardingDisabledError,
    onboard_company,
    summarize_business_data,
)
from app.services.onboarding_token import (
    generate_onboarding_token,
    verify_onboarding_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["onboarding"])

# Real Tally/Vyapar exports are well under a megabyte — same real-world
# constraint as the founder-only admin import route (app/api/admin/
# imports.py), which allows 10 MB. This route is public/unauthenticated
# though, so the cap is halved as cheap defense-in-depth against an
# anonymous caller trying to burn memory/CPU on oversized uploads; the real
# guard is the company-state check in _get_importable_company below.
_MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def _require_onboarding_token(company_id: uuid.UUID, token: str | None) -> None:
    """Both public per-company routes need proof the caller is the one who
    registered this company, not merely someone who knows its UUID.

    404 rather than 401 on purpose: it matches what these routes already
    return for an unknown/ineligible company, so a caller can't use the status
    code to distinguish "this company exists but you have no token" from "no
    such company" — which is exactly the oracle this token closes.
    """
    if not verify_onboarding_token(company_id, token):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company {company_id} not found.",
        )


async def _get_importable_company(company_id: uuid.UUID, db: AsyncSession) -> Company:
    """A company is only importable through this public route while it's
    still exactly where the self-serve wizard leaves it before WhatsApp
    starts: registered (not_started) and not yet subscribed. Paired with the
    onboarding-token check at the call site — the state gate bounds the window
    in which this route works at all, the token bounds *who* can use it, and
    neither alone is sufficient: without the token, any leaked/guessed UUID
    could inject junk invoices into a real distributor's books during that
    window.
    """
    company = await db.get(Company, company_id)
    if (
        company is None
        or company.onboarding_state != OnboardingState.not_started
        or company.subscription_active
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company {company_id} not found.",
        )
    return company


@router.get("/onboard", response_class=HTMLResponse, summary="Distributor onboarding wizard")
async def onboarding_page(request: Request) -> HTMLResponse:
    settings = get_settings()
    return templates.TemplateResponse(
        request,
        "onboard.html",
        {
            "whatsapp_business_display_number": settings.whatsapp_business_display_number or "",
            "marketing_site_url": settings.marketing_site_url or "/",
        },
    )


@router.post("/onboard", response_model=OnboardResponse, summary="Submit an onboarding request")
async def submit_onboarding(
    payload: OnboardRequest,
    db: AsyncSession = Depends(get_db),
) -> OnboardResponse:
    try:
        company, created = await onboard_company(
            db,
            business_name=payload.business_name,
            owner_name=payload.owner_name,
            whatsapp_number=payload.whatsapp_number,
            email=payload.email,
            business_type=payload.business_type,
            preferred_language=payload.preferred_language,
            city=payload.city,
            gst_number=payload.gst_number,
        )
    except OnboardingDisabledError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Onboarding is not available right now.",
        ) from exc
    except InvalidPhoneNumberError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except FounderNumberConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    if created:
        message = "Thanks! You're registered. Next: activate your account."
        return OnboardResponse(
            status="registered",
            company_id=company.id,
            onboarding_token=generate_onboarding_token(company.id),
            whatsapp_number=company.whatsapp_number,
            message=message,
        )
    # Deliberately no company_id and no token on this branch. A WhatsApp
    # number is public information (printed on invoices, encoded in the wa.me
    # link), so returning the id here turned this endpoint into an oracle:
    # post a real distributor's number, get their UUID, then use it against
    # /import — which writes into their books and echoes back their real
    # receivable/payable totals. Someone resuming their *own* signup re-runs
    # the wizard and gets a fresh token on a new registration; someone probing
    # a number they don't control learns nothing.
    return OnboardResponse(
        status="already_registered",
        whatsapp_number=company.whatsapp_number,
        message=(
            "This number is already registered with us. "
            "Check your WhatsApp to continue setting up, or contact us for help."
        ),
    )


@router.post(
    "/onboard/{company_id}/import",
    response_model=OnboardImportResponse,
    summary="Self-serve: import a Tally/Vyapar/Excel/PDF export before WhatsApp starts",
    description=(
        "Optional wizard step between business details and activation — lets a "
        "distributor bootstrap dealers/suppliers/invoices/payments, or their "
        "product/stock catalogue, from an existing export instead of typing "
        "everything into WhatsApp. Same importer as the founder admin route "
        "(Tally/Vyapar/OpsGenie-canonical CSV/Excel, plus Tally-style PDF "
        "voucher/invoice printouts for file_kind=invoices/payments), scoped to "
        "one direction per call, matching how a real sales register vs. "
        "purchase register export works. Payments FIFO-allocate against "
        "already-imported open invoices for that party, so an invoices file "
        "for a given party should be imported before its payments file. "
        "Returns the import result plus a fresh reconciliation summary so the "
        "distributor can confirm it looks right before continuing."
    ),
)
async def import_onboarding_data(
    company_id: uuid.UUID,
    file_kind: Literal["invoices", "payments", "products"] = Query(
        "invoices",
        description="Whether this file contains invoices, payments, or a product/stock catalogue",
    ),
    direction: Literal["receivable", "payable"] | None = Query(
        None,
        description="receivable = dealer invoices/payments, payable = supplier. "
        "Required unless file_kind=products.",
    ),
    file: UploadFile = File(...),
    token: str | None = Query(
        None,
        description="The onboarding_token returned when this company was registered.",
    ),
    db: AsyncSession = Depends(get_db),
) -> OnboardImportResponse:
    settings = get_settings()
    if not settings.onboarding_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Onboarding is not available right now.",
        )
    _require_onboarding_token(company_id, token)
    company = await _get_importable_company(company_id, db)
    if file_kind != "products" and direction is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="direction is required unless file_kind=products.",
        )

    # Bounded read: pull at most the limit + 1 byte, so an oversized upload is
    # rejected without ever being fully buffered.
    contents = await file.read(_MAX_UPLOAD_BYTES + 1)
    if len(contents) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds the {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit.",
        )
    try:
        result = await run_import(
            db,
            company_id=company.id,
            direction=direction,
            file_kind=file_kind,
            filename=file.filename or "upload",
            contents=contents,
        )
    except (UnsupportedFileError, UnrecognisedFormatError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await write_import_log(db, company.id, result)
    summary = await summarize_business_data(db, company.id)

    logger.info(
        "Onboarding import %s for company %s: %d processed, %d succeeded, %d skipped, %d failed",
        result.filename,
        company.id,
        result.rows_processed,
        result.rows_succeeded,
        result.rows_skipped,
        result.rows_failed,
    )

    return OnboardImportResponse(
        import_result=ImportResponse(
            filename=result.filename,
            source_format=result.source_format,
            rows_processed=result.rows_processed,
            rows_succeeded=result.rows_succeeded,
            rows_skipped=result.rows_skipped,
            rows_failed=result.rows_failed,
            errors=[ImportRowError(row=e.row_number, reason=e.reason) for e in result.errors],
        ),
        summary=OnboardImportSummary(**summary),
    )


@router.post(
    "/onboard/{company_id}/activate",
    response_model=SubscriptionResponse,
    summary="Self-serve activation (turns on the WhatsApp agent + welcome)",
)
async def activate_onboarded_company(
    company_id: uuid.UUID,
    token: str | None = Query(
        None,
        description="The onboarding_token returned when this company was registered.",
    ),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionResponse:
    settings = get_settings()
    if not settings.onboarding_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Onboarding is not available right now.",
        )
    _require_onboarding_token(company_id, token)
    company = await db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Company {company_id} not found."
        )
    # An already-active company is a no-op, not a rejection: the wizard's
    # Activate button can be double-clicked or retried, and the caller has
    # already proved (via the token) that this is their own registration.
    # activate_company itself is idempotent and returns "already_active".
    if not company.subscription_active:
        # Otherwise only a company still sitting where the self-serve wizard
        # leaves it may be activated: freshly registered (not_started).
        #
        # The previous condition was written inverted — it rejected only
        # `completed AND inactive`, so every *other* inactive state passed. A
        # company the founder had deactivated mid-onboarding could therefore
        # be switched back on through this public route, re-enabling the
        # WhatsApp agent for a suspended tenant and firing a billable Meta
        # welcome template. This now matches _get_importable_company's gate,
        # which is what the comment always claimed it did.
        if company.onboarding_state != OnboardingState.not_started:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Company {company_id} not found."
            )
    status_, welcome_sent = await activate_company(db, company)
    return SubscriptionResponse(
        company_id=company.id,
        subscription_active=company.subscription_active,
        status=status_,
        welcome_sent=welcome_sent,
    )
