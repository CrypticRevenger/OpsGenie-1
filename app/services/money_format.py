"""₹ formatting shared by the numbered query menu (Phase 8) and the
follow-up conversation (Phase 9) — both build WhatsApp text directly, without
an LLM step, so amounts need a deterministic, human-readable format here
rather than relying on narration.
"""

from __future__ import annotations

from decimal import Decimal


def _indian_grouping(digits: str) -> str:
    if len(digits) <= 3:
        return digits
    last3 = digits[-3:]
    rest = digits[:-3]
    groups: list[str] = []
    while len(rest) > 2:
        groups.insert(0, rest[-2:])
        rest = rest[:-2]
    if rest:
        groups.insert(0, rest)
    return ",".join([*groups, last3])


def format_inr(amount: Decimal) -> str:
    """₹ with Indian digit grouping (lakhs/crores), e.g. Decimal('184000') ->
    '₹1,84,000'. Paise are shown only when non-zero.
    """
    quantized = amount.quantize(Decimal("0.01"))
    sign = "-" if quantized < 0 else ""
    int_part, _, frac_part = str(abs(quantized)).partition(".")
    grouped = _indian_grouping(int_part)
    if frac_part in ("", "00"):
        return f"{sign}₹{grouped}"
    return f"{sign}₹{grouped}.{frac_part}"


def format_signed_inr(amount: Decimal) -> str:
    formatted = format_inr(amount)
    return formatted if formatted.startswith("-") else f"+{formatted}"
