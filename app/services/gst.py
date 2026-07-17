"""Shared GST-rate parsing and per-line fallback — Phase 2C.

One seam so onboarding's gst_rate_same/product_awaiting_gst_rate states, the
bulk product parser, the "update gst" WhatsApp flow, and order calculation
all agree on what counts as a valid rate. Currently an unrestricted 0-100
range (not a fixed slab list like India's GST Council rates) — kept as a
single function so swapping in a slab list later is a one-line change, not a
hunt across four call sites.
"""

from __future__ import annotations

from decimal import Decimal

from app.services.importer.normalizer import parse_amount

_MIN_GST_RATE = Decimal("0")
_MAX_GST_RATE = Decimal("100")


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
