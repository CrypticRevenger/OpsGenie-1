"""Self-serve onboarding — create a *pending* company from the public form.

A distributor submits their details on /onboard. This stores them as a
Company with subscription_active=False; the WhatsApp agent stays silent for
them until they self-activate via the wizard's final step (app/api/
onboarding.py's POST /onboard/{id}/activate, sharing app/services/
activation.py's activate_company with the founder-only admin route), which is
also what fires the welcome template. onboarding_enabled is the only gate on
this public endpoint (a plain kill-switch, not a secret) — fails closed when
disabled.
"""

from __future__ import annotations

import logging
import re
import uuid
from decimal import Decimal

import phonenumbers
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.company import Company, OnboardingState
from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceDirection
from app.models.product import Product
from app.models.supplier import Supplier
from app.services.party_outstanding import calculate_outstanding_for_company

logger = logging.getLogger(__name__)


class OnboardingDisabledError(Exception):
    """ONBOARDING_ENABLED is false — onboarding is off."""


class InvalidPhoneNumberError(Exception):
    """The submitted number couldn't be normalised to E.164."""


class FounderNumberConflictError(Exception):
    """The submitted number matches FOUNDER_WHATSAPP_NUMBER.

    That number is where NotificationEngine's founder-facing alerts (stale
    data, briefing-delivery failure — app/services/notifications.py's
    send_founder_alert) go for *every* company. Letting a company register
    the same number would make that company's own chat silently receive
    every other company's internal ops alerts alongside its real briefing.
    """


def normalize_number(raw: str) -> str:
    """Turn free-form form input into validated E.164 via libphonenumber.

    Full validity (is_valid_number, not just plausible length) is required so
    a distributor who enters their local number WITHOUT a country code — the
    likeliest mistake on a mobile form — is rejected instead of silently
    stored as a wrong number. e.g. "9876543210" would otherwise become
    "+9876543210" (parsed as +98 Iran), which no real inbound would ever
    match, permanently breaking the agent for that company. Strips
    spaces/dashes/parens and accepts a 00 international prefix or a bare
    country code without +.
    """
    cleaned = re.sub(r"[\s\-().]", "", raw.strip())
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    if not cleaned.startswith("+"):
        cleaned = "+" + cleaned
    try:
        parsed = phonenumbers.parse(cleaned, None)
    except phonenumbers.NumberParseException as exc:
        raise InvalidPhoneNumberError(
            "Enter a valid WhatsApp number with country code, e.g. +919876543210."
        ) from exc
    if not phonenumbers.is_valid_number(parsed):
        raise InvalidPhoneNumberError(
            "That doesn't look like a valid number. Include your country code, e.g. +919876543210."
        )
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def reject_founder_collision(number: str) -> None:
    """Raise if `number` (already E.164-normalised) is FOUNDER_WHATSAPP_NUMBER.

    Shared by both company-creation entry points — self-serve onboarding
    below and the founder-only admin create route (app/api/admin/
    companies.py) — since either can otherwise seed the exact bug this
    guards against.
    """
    founder_number = get_settings().founder_whatsapp_number
    if founder_number and number == founder_number:
        raise FounderNumberConflictError(
            "This number is reserved for OpsGenie's internal ops alerts and can't "
            "be registered as a company's WhatsApp number."
        )


async def onboard_company(
    db: AsyncSession,
    *,
    business_name: str,
    owner_name: str,
    whatsapp_number: str,
    email: str | None = None,
    business_type: str | None = None,
    preferred_language: str = "en",
    city: str | None = None,
    gst_number: str | None = None,
) -> tuple[Company, bool]:
    """Register a pending company. Returns (company, created) — created is
    False when the number was already registered (a resubmit), so the caller
    can report "already registered" rather than error.
    """
    settings = get_settings()
    if not settings.onboarding_enabled:
        raise OnboardingDisabledError("Onboarding is not enabled.")

    number = normalize_number(whatsapp_number)
    reject_founder_collision(number)

    existing = await db.scalar(select(Company).where(Company.whatsapp_number == number))
    if existing is not None:
        return existing, False

    company = Company(
        business_name=business_name.strip(),
        owner_name=owner_name.strip(),
        whatsapp_number=number,
        email=email.strip() if email else None,
        business_type=business_type.strip() if business_type else None,
        preferred_language=preferred_language,
        city=city.strip() if city else None,
        gst_number=gst_number.strip() if gst_number else None,
        subscription_active=False,
        # Self-serve companies walk the guided WhatsApp setup once activated;
        # the column otherwise defaults to `completed` for founder-created rows.
        onboarding_state=OnboardingState.not_started,
    )
    db.add(company)
    try:
        await db.commit()
    except IntegrityError:
        # Raced with another submit of the same number — treat as already
        # registered rather than surfacing a 500.
        await db.rollback()
        existing = await db.scalar(select(Company).where(Company.whatsapp_number == number))
        if existing is not None:
            return existing, False
        raise
    await db.refresh(company)
    logger.info("Onboarded pending company %s (%s)", company.business_name, company.id)
    return company, True


async def _count(db: AsyncSession, model, company_id: uuid.UUID) -> int:
    stmt = select(func.count()).select_from(model).where(model.company_id == company_id)
    return await db.scalar(stmt) or 0


async def summarize_business_data(db: AsyncSession, company_id: uuid.UUID) -> dict[str, object]:
    """Counts + outstanding totals for the self-serve reconciliation screen
    shown right after a website import (app/api/onboarding.py's
    POST /onboard/{id}/import). Not import-specific — just queries current
    state via the same calculate_outstanding_for_company the rest of the
    product uses, so it's correct regardless of how the data got there.
    """
    product_count = await _count(db, Product, company_id)
    dealer_count = await _count(db, Dealer, company_id)
    supplier_count = await _count(db, Supplier, company_id)
    receivable_invoice_count = await db.scalar(
        select(func.count())
        .select_from(Invoice)
        .where(Invoice.company_id == company_id, Invoice.direction == InvoiceDirection.receivable)
    )
    payable_invoice_count = await db.scalar(
        select(func.count())
        .select_from(Invoice)
        .where(Invoice.company_id == company_id, Invoice.direction == InvoiceDirection.payable)
    )
    receivable_by_party = await calculate_outstanding_for_company(
        db, company_id=company_id, direction="receivable"
    )
    payable_by_party = await calculate_outstanding_for_company(
        db, company_id=company_id, direction="payable"
    )
    return {
        "product_count": product_count,
        "dealer_count": dealer_count,
        "supplier_count": supplier_count,
        "receivable_invoice_count": receivable_invoice_count or 0,
        "receivable_total": sum(receivable_by_party.values(), Decimal("0.00")),
        "payable_invoice_count": payable_invoice_count or 0,
        "payable_total": sum(payable_by_party.values(), Decimal("0.00")),
    }
