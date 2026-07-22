"""E.164 phone normalization for dealer/supplier entry points.

Distinct from app.services.onboarding.normalize_number, which requires an
explicit country code and is scoped to Company.whatsapp_number (the
founder's own number — a wrong region guess there would silently break the
whole company's WhatsApp integration). Dealer/supplier phones are
realistically typed as a bare 10-digit Indian number ("9876543210"), so this
defaults to settings.default_phone_region ("IN" today) when no country code
is present, while still respecting an explicit "+<country><number>" if one
is given.
"""

from __future__ import annotations

import re

import phonenumbers

from app.core.config import get_settings

_STRIP_CHARS = re.compile(r"[\s\-().]")


class InvalidPhoneNumberError(Exception):
    """The submitted number couldn't be normalized to E.164."""


def normalize_party_phone(raw: str, default_region: str | None = None) -> str:
    region = default_region or get_settings().default_phone_region
    cleaned = _STRIP_CHARS.sub("", raw.strip())
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    try:
        parsed = phonenumbers.parse(cleaned, region)
    except phonenumbers.NumberParseException as exc:
        raise InvalidPhoneNumberError(
            "That doesn't look like a valid phone number. Include the country "
            "code if it's not Indian, e.g. +919876543210."
        ) from exc
    if not phonenumbers.is_valid_number(parsed):
        raise InvalidPhoneNumberError(
            "That doesn't look like a valid phone number. Include the country "
            "code if it's not Indian, e.g. +919876543210."
        )
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
