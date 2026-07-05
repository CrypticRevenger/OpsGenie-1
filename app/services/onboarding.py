"""Self-serve onboarding — create a *pending* company from the public form.

A distributor submits their details plus a shared access code on /onboard.
This stores them as a Company with subscription_active=False; the WhatsApp
agent stays silent for them until the founder activates their subscription
(app/api/admin/companies.py's activate-subscription), which is also what
fires the welcome template. The access code is the only gate on this public
endpoint, so it's checked in constant time and fails closed when unset.
"""

from __future__ import annotations

import logging
import re
import secrets

import phonenumbers
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.company import Company, OnboardingState

logger = logging.getLogger(__name__)


class OnboardingDisabledError(Exception):
    """ONBOARDING_ACCESS_CODE is not configured — onboarding is off."""


class InvalidAccessCodeError(Exception):
    """The submitted access code did not match."""


class InvalidPhoneNumberError(Exception):
    """The submitted number couldn't be normalised to E.164."""


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


async def onboard_company(
    db: AsyncSession,
    *,
    business_name: str,
    owner_name: str,
    whatsapp_number: str,
    access_code: str,
) -> tuple[Company, bool]:
    """Validate the access code and register a pending company. Returns
    (company, created) — created is False when the number was already
    registered (a resubmit), so the caller can report "already registered"
    rather than error.
    """
    settings = get_settings()
    if not settings.onboarding_access_code:
        raise OnboardingDisabledError("Onboarding is not enabled.")
    if not secrets.compare_digest(access_code or "", settings.onboarding_access_code):
        raise InvalidAccessCodeError("Invalid access code.")

    number = normalize_number(whatsapp_number)

    existing = await db.scalar(select(Company).where(Company.whatsapp_number == number))
    if existing is not None:
        return existing, False

    company = Company(
        business_name=business_name.strip(),
        owner_name=owner_name.strip(),
        whatsapp_number=number,
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
