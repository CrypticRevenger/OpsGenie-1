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

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.templates import templates
from app.db.session import get_db
from app.models.company import Company, OnboardingState
from app.schemas.company import SubscriptionResponse
from app.schemas.onboarding import OnboardRequest, OnboardResponse
from app.services.activation import activate_company
from app.services.onboarding import (
    FounderNumberConflictError,
    InvalidPhoneNumberError,
    OnboardingDisabledError,
    onboard_company,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["onboarding"])


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
            whatsapp_number=company.whatsapp_number,
            message=message,
        )
    return OnboardResponse(
        status="already_registered",
        company_id=company.id,
        whatsapp_number=company.whatsapp_number,
        message="This number is already registered with us.",
    )


@router.post(
    "/onboard/{company_id}/activate",
    response_model=SubscriptionResponse,
    summary="Self-serve activation (turns on the WhatsApp agent + welcome)",
)
async def activate_onboarded_company(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> SubscriptionResponse:
    settings = get_settings()
    if not settings.onboarding_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Onboarding is not available right now.",
        )
    company = await db.get(Company, company_id)
    # Only companies that actually came through self-serve onboarding are
    # activatable here — narrows the blast radius of "any unguessable UUID"
    # beyond just the kill-switch, so a founder-created company's id leaking
    # through some other channel can't be self-activated through this route.
    if company is None or (
        company.onboarding_state == OnboardingState.completed and not company.subscription_active
    ):
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
