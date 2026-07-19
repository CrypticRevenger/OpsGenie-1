"""Period resolution shared by every period-scoped report builder.

A single `resolve_period()` so "which of from/to/month wins, and what does
an un-parameterized request default to" is answered in exactly one place —
every report builder takes the resulting `ReportPeriod` rather than
re-deriving it from raw query params. Takes plain date/string inputs rather
than a hardcoded preset enum, so a later "last month" / "this quarter" / "FY
2026-27" shortcut is just a small function that computes `from_date`/`to_date`
and calls this same resolver — not needed yet, so not built yet.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date


class InvalidPeriodError(ValueError):
    """A `from`/`to`/`month` query param that doesn't parse, or from > to."""


@dataclass(frozen=True)
class ReportPeriod:
    """`from_date`/`to_date` both None means all-time — no filter applied."""

    from_date: date | None
    to_date: date | None
    label: str


def resolve_period(
    *,
    from_str: str | None = None,
    to_str: str | None = None,
    month_str: str | None = None,
    default_to_current_month: bool = False,
    today: date | None = None,
) -> ReportPeriod:
    """`month_str` (YYYY-MM) wins if given; else explicit `from`/`to` (ISO
    dates, either may be open-ended); else the current calendar month if
    `default_to_current_month`; else all-time.
    """
    today = today or date.today()

    if month_str is not None:
        return _month_period(month_str)

    if from_str is not None or to_str is not None:
        from_date = _parse_date(from_str) if from_str else None
        to_date = _parse_date(to_str) if to_str else None
        if from_date is not None and to_date is not None and from_date > to_date:
            raise InvalidPeriodError(f"'from' ({from_date}) is after 'to' ({to_date}).")
        label = _range_label(from_date, to_date)
        return ReportPeriod(from_date=from_date, to_date=to_date, label=label)

    if default_to_current_month:
        return _month_period(f"{today.year:04d}-{today.month:02d}")

    return ReportPeriod(from_date=None, to_date=None, label="All time")


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise InvalidPeriodError(f"'{value}' is not a valid YYYY-MM-DD date.") from exc


def _month_period(month_str: str) -> ReportPeriod:
    try:
        year_str, month_str_part = month_str.strip().split("-", 1)
        year, month = int(year_str), int(month_str_part)
        if not 1 <= month <= 12:
            raise ValueError
    except ValueError as exc:
        raise InvalidPeriodError(f"'{month_str}' is not a valid YYYY-MM month.") from exc
    from_date = date(year, month, 1)
    to_date = date(year, month, calendar.monthrange(year, month)[1])
    return ReportPeriod(from_date=from_date, to_date=to_date, label=from_date.strftime("%B %Y"))


def _range_label(from_date: date | None, to_date: date | None) -> str:
    if from_date and to_date:
        return f"{from_date.isoformat()} to {to_date.isoformat()}"
    if from_date:
        return f"From {from_date.isoformat()}"
    return f"Up to {to_date.isoformat()}"
