"""Public self-serve onboarding — the /onboard page + submit endpoint.

Outside the admin router (no X-API-Key) so distributors can reach it; the
shared access code checked inside onboard_company is its only gate. Stores a
pending company (subscription_active=False) — the founder activates it later,
which is what turns on the WhatsApp agent and sends the welcome template.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.onboarding_page import ONBOARD_HTML
from app.db.session import get_db
from app.schemas.onboarding import OnboardRequest, OnboardResponse
from app.services.onboarding import (
    InvalidAccessCodeError,
    InvalidPhoneNumberError,
    OnboardingDisabledError,
    onboard_company,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["onboarding"])


@router.get("/onboard", response_class=HTMLResponse, summary="Distributor onboarding page")
async def onboarding_page() -> HTMLResponse:
    return HTMLResponse(ONBOARD_HTML)


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
            access_code=payload.access_code,
        )
    except OnboardingDisabledError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Onboarding is not available right now.",
        ) from exc
    except InvalidAccessCodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid access code."
        ) from exc
    except InvalidPhoneNumberError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

    if created:
        message = "Thanks! You're registered. You'll get a WhatsApp welcome once activated."
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
