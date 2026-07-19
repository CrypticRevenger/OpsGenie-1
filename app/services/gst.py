"""Shared GST-rate parsing and per-line fallback — Phase 2C.

One seam so onboarding's gst_rate_same/product_awaiting_gst_rate states, the
bulk product parser, the "update gst" WhatsApp flow, and order calculation
all agree on what counts as a valid rate. Currently an unrestricted 0-100
range (not a fixed slab list like India's GST Council rates) — kept as a
single function so swapping in a slab list later is a one-line change, not a
hunt across four call sites.
"""

from __future__ import annotations

import re
from decimal import Decimal

from app.services.importer.normalizer import parse_amount

_MIN_GST_RATE = Decimal("0")
_MAX_GST_RATE = Decimal("100")

# 15-char GSTIN: 2-digit state code, 10-char PAN (5 letters, 4 digits, 1
# letter), 1-char entity number, literal 'Z', 1-char checksum.
_GSTIN_FORMAT = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
_GSTIN_CHARSET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def validate_gstin(value: str) -> bool:
    """True if `value` is a 15-char GSTIN with a valid format and checksum
    digit (the standard mod-36 algorithm every real GSTIN is generated
    with). Used to reject a typo'd GSTIN at entry rather than storing junk."""
    candidate = value.strip().upper()
    if not _GSTIN_FORMAT.match(candidate):
        return False
    total = 0
    factor = 1
    for char in candidate[:14]:
        product = _GSTIN_CHARSET.index(char) * factor
        total += (product // 36) + (product % 36)
        factor = 2 if factor == 1 else 1
    expected_checksum = _GSTIN_CHARSET[(36 - (total % 36)) % 36]
    return candidate[14] == expected_checksum


def parse_gst_rate(raw: str) -> Decimal:
    """Parse a GST percentage string. Raises ValueError (with a message
    already fit for a WhatsApp reply) if unparseable or out of range."""
    value = parse_amount(raw)
    if not (_MIN_GST_RATE <= value <= _MAX_GST_RATE):
        raise ValueError("gst_rate must be between 0 and 100")
    return value


def effective_gst_rate(product_gst_rate: Decimal | None, company_gst_rate: Decimal) -> Decimal:
    """A product's own rate wins when set; otherwise fall back to the
    company default. Mirrors Product.selling_price's own nullable-with-
    fallback shape."""
    return product_gst_rate if product_gst_rate is not None else company_gst_rate
