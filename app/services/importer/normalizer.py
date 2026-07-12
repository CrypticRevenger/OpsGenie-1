"""Date and amount normalisation utilities.

These functions are intentionally format-agnostic — they receive a raw
string from any source (CSV cell, Excel cell value) and return a clean
Python type or raise ValueError with a helpful message.

The Tally-specific normaliser (when the real file arrives) will pre-process
column names and then delegate individual cell parsing here.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

# ── Date parsing ──────────────────────────────────────────────────────────────

_DATE_PATTERNS: list[str] = [
    r"^(\d{4})-(\d{1,2})-(\d{1,2})$",  # YYYY-MM-DD  (ISO)
    r"^(\d{1,2})-(\d{1,2})-(\d{4})$",  # DD-MM-YYYY  (Tally default)
    r"^(\d{1,2})/(\d{1,2})/(\d{4})$",  # DD/MM/YYYY  (Vyapar)
    r"^(\d{4})/(\d{1,2})/(\d{1,2})$",  # YYYY/MM/DD
]


def parse_date(raw: str) -> date:
    """Parse a date string in any common Indian accounting format.

    Returns a :class:`datetime.date`.  Raises :class:`ValueError` if the
    string cannot be parsed.
    """
    raw = raw.strip()

    for pattern in _DATE_PATTERNS:
        m = re.match(pattern, raw)
        if m:
            a, b, c = int(m.group(1)), int(m.group(2)), int(m.group(3))
            # Determine year position: if first group > 31 it must be the year
            if a > 31:
                year, month, day = a, b, c
            elif c > 31:
                day, month, year = a, b, c
            else:
                # Ambiguous — assume DD-MM-YYYY (Tally default)
                day, month, year = a, b, c
            try:
                return date(year, month, day)
            except ValueError as exc:
                raise ValueError(f"Invalid date components in '{raw}'") from exc

    raise ValueError(
        f"Unrecognised date format '{raw}'. Expected DD-MM-YYYY, YYYY-MM-DD, or DD/MM/YYYY."
    )


# ── Amount parsing ────────────────────────────────────────────────────────────

_STRIP_CHARS = re.compile(r"[₹,\s]")


def parse_amount(raw: str) -> Decimal:
    """Parse a monetary amount string, stripping currency symbols and commas.

    Returns a :class:`decimal.Decimal` rounded to 2 decimal places.
    Raises :class:`ValueError` if the string cannot be parsed.
    """
    cleaned = _STRIP_CHARS.sub("", raw.strip())
    if not cleaned:
        raise ValueError(f"Empty amount: '{raw}'")
    try:
        value = Decimal(cleaned)
        # A non-finite Decimal ("nan"/"inf") parses cleanly but has no place in
        # money math — reject it here rather than letting NaN poison a later
        # sum or crash a comparison. quantize() itself must also stay inside
        # this guard: on a number with too many significant digits it raises
        # InvalidOperation (an ArithmeticError, NOT a ValueError), which every
        # caller's `except ValueError` would miss and let 500 the webhook.
        if not value.is_finite():
            raise ValueError(f"Amount '{raw}' is not a finite number")
        return value.quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise ValueError(f"Cannot parse amount '{raw}' as a number") from exc


# ── Column name normalisation ─────────────────────────────────────────────────


def normalise_header(raw: str) -> str:
    """Lower-case, strip whitespace, replace spaces/hyphens with underscores."""
    return re.sub(r"[\s\-]+", "_", raw.strip().lower())


def row_by_normalised_header(raw_row: dict[str, str], headers: list[str]) -> dict[str, str]:
    """Re-key a row from original header text to normalised header text.

    BaseImporter.map_headers()/normalise_row() operate on normalised header
    strings throughout — this bridges a row keyed by original file headers
    (as read by engine.parse_file) to that contract. Shared by both the
    invoice and payment import paths.
    """
    return {normalise_header(h): raw_row.get(h, "") for h in headers}
