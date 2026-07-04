"""Admin company routes (founder-only, behind the shared X-API-Key).

Founder creates/reads/deletes companies here. Companies can also arrive via
the public self-serve /onboard page (app/api/onboarding.py) as *pending*
(subscription_active=False); activate-subscription below is what turns the
WhatsApp agent on for them and sends the welcome template.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db
from app.models.company import Company
from app.models.notification_log import NotificationLog
from app.schemas.company import CompanyCreate, CompanyResponse, SubscriptionResponse
from app.schemas.pagination import Page
from app.services.whatsapp_client import (
    WhatsAppNotConfiguredError,
    WhatsAppSendError,
    send_template_message,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/companies", tags=["admin:companies"])


@router.post(
    "",
    response_model=CompanyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a company",
    description="Register a new B2B distributor company. whatsapp_number must be unique.",
)
async def create_company(
    payload: CompanyCreate,
    db: AsyncSession = Depends(get_db),
) -> Company:
    company = Company(
        business_name=payload.business_name,
        owner_name=payload.owner_name,
        whatsapp_number=payload.whatsapp_number,
        email=payload.email,
        business_type=payload.business_type,
        preferred_language=payload.preferred_language,
        timezone=payload.timezone,
        opening_balance=payload.opening_balance,
    )
    db.add(company)
    try:
        await db.commit()
        await db.refresh(company)
    except IntegrityError as err:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A company with WhatsApp number '{payload.whatsapp_number}' already exists.",
        ) from err
    logger.info("Created company %s (%s)", company.business_name, company.id)
    return company


@router.get(
    "",
    response_model=Page[CompanyResponse],
    summary="List all companies",
)
async def list_companies(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> Page[CompanyResponse]:
    total = await db.scalar(select(func.count()).select_from(Company)) or 0
    result = await db.execute(
        select(Company).order_by(Company.created_at.desc()).offset((page - 1) * limit).limit(limit)
    )
    companies = list(result.scalars().all())
    return Page.create(items=companies, total=total, page=page, limit=limit)


@router.get(
    "/{company_id}",
    response_model=CompanyResponse,
    summary="Get a company by ID",
)
async def get_company(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Company:
    company = await db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company {company_id} not found.",
        )
    return company


@router.delete(
    "/{company_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a company and all its data",
    description=(
        "Permanently deletes a company and everything scoped to it — dealers, "
        "suppliers, invoices, payments, business events, activity timeline, "
        "briefings, imports, and notification logs — via database cascade. "
        "Irreversible."
    ),
)
async def delete_company(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Response:
    company = await db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company {company_id} not found.",
        )
    # Core DELETE (not db.delete(company)) so the whole subtree is removed by
    # Postgres ON DELETE CASCADE in one statement — the ORM cascade would try
    # to lazy-load every child collection, which raises under async. Postgres
    # resolves the Phase 9 circular FK (companies.pending_follow_up_invoice_id
    # -> invoices) and the invoice dealer/supplier CHECK correctly on its own
    # (verified against real data).
    await db.execute(delete(Company).where(Company.id == company_id))
    await db.commit()
    logger.info("Deleted company %s (%s)", company.business_name, company_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _send_welcome(db: AsyncSession, company: Company) -> bool:
    """Send the approved welcome template to a newly-activated company and log
    it. Fail-open like every other send — a missing template or a Meta error
    is logged, never raised, so activation still succeeds. Returns whether the
    welcome actually went out.
    """
    settings = get_settings()
    if not settings.welcome_template_name:
        logger.info("Welcome not sent to %s — WELCOME_TEMPLATE_NAME unset.", company.id)
        return False
    send_result = None
    try:
        send_result = await send_template_message(
            company.whatsapp_number,
            settings.welcome_template_name,
            settings.welcome_template_language,
            # Fills the template's {{1}} body variable. The approved
            # `opsgenie_welcome` template must have exactly one body variable;
            # a variable-less template would be rejected by Meta for having a
            # parameter, and vice-versa — the two must match.
            body_params=[company.business_name],
        )
    except (WhatsAppNotConfiguredError, WhatsAppSendError) as exc:
        logger.warning("Welcome template to %s not sent: %s", company.whatsapp_number, exc)
    db.add(
        NotificationLog(
            company_id=company.id,
            notification_type="welcome",
            recipient_whatsapp=company.whatsapp_number,
            message_text=f"welcome template: {settings.welcome_template_name}",
            whatsapp_message_id=send_result.message_id if send_result else None,
            delivery_status="sent" if send_result else "failed_to_send",
        )
    )
    return send_result is not None


@router.post(
    "/{company_id}/activate-subscription",
    response_model=SubscriptionResponse,
    summary="Activate a company's subscription (turns on the WhatsApp agent + welcome)",
)
async def activate_subscription(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> SubscriptionResponse:
    company = await db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Company {company_id} not found."
        )
    if company.subscription_active:
        # Already live — don't re-send the welcome.
        return SubscriptionResponse(
            company_id=company.id,
            subscription_active=True,
            status="already_active",
            welcome_sent=False,
        )
    # Commit the activation first — that's the durable, important part — then
    # send the (best-effort) welcome in a second transaction. This keeps the
    # ~10s Meta round-trip out of the row lock, and means a commit failure
    # after a successful send can't leave the flag False (which would re-send
    # the welcome on retry): a retry sees subscription_active=True and no-ops.
    company.subscription_active = True
    await db.commit()
    welcome_sent = await _send_welcome(db, company)
    await db.commit()
    logger.info("Activated subscription for %s (welcome_sent=%s)", company_id, welcome_sent)
    return SubscriptionResponse(
        company_id=company.id,
        subscription_active=True,
        status="activated",
        welcome_sent=welcome_sent,
    )


@router.post(
    "/{company_id}/deactivate-subscription",
    response_model=SubscriptionResponse,
    summary="Deactivate a company's subscription (silences the WhatsApp agent)",
)
async def deactivate_subscription(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> SubscriptionResponse:
    company = await db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Company {company_id} not found."
        )
    already_inactive = not company.subscription_active
    company.subscription_active = False
    await db.commit()
    return SubscriptionResponse(
        company_id=company.id,
        subscription_active=False,
        status="already_inactive" if already_inactive else "deactivated",
        welcome_sent=False,
    )
