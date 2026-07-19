"""REPORTS — the single lookup table tying a report key to its display name,
Excel/PDF builders, and whether it needs a resolved party. Both the signed
export endpoint (app/api/export.py) and the WhatsApp trigger reply builder
(app/api/webhooks/whatsapp.py) look report metadata up here instead of each
hardcoding report identifiers/names separately — adding another report later
is one new entry here, not edits scattered across both call sites.

Deliberately a dict of small adapter functions (dataclass values), not a
class-based `ReportBuilder` interface — matches this codebase's existing
dispatch idiom (CommandRouter, _WORKFLOW_HANDLERS, _INSTANT_COMMANDS are all
plain dicts, not an OOP hierarchy).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.dealer import Dealer
from app.models.supplier import Supplier
from app.services import company_export
from app.services.party_outstanding import Direction
from app.services.reports import aging, ledger, registers
from app.services.reports.period import ReportPeriod

# aging/outstanding is always a snapshot as of "now" (per party_outstanding.py,
# there is no historical point-in-time outstanding calculation) — the period
# a caller resolved from from/to/month is ignored for this report, same
# decision confirmed with the user during planning.
_UNUSED_PERIOD = ReportPeriod(from_date=None, to_date=None, label="All time")


@dataclass(frozen=True)
class ReportContext:
    period: ReportPeriod = _UNUSED_PERIOD
    party: Dealer | Supplier | None = None
    direction: Direction | None = None


BuildFn = Callable[[AsyncSession, Company, ReportContext], Awaitable[bytes]]


@dataclass(frozen=True)
class ReportSpec:
    key: str
    display_name: str
    build_xlsx: BuildFn
    build_pdf: BuildFn | None = None
    needs_party: bool = False


async def _full_xlsx(db: AsyncSession, company: Company, ctx: ReportContext) -> bytes:
    return await company_export.build_company_workbook(db, company)


async def _ledger_xlsx(db: AsyncSession, company: Company, ctx: ReportContext) -> bytes:
    return await ledger.build_party_ledger_workbook(
        db, company, ctx.party, ctx.direction, ctx.period
    )


async def _ledger_pdf(db: AsyncSession, company: Company, ctx: ReportContext) -> bytes:
    return await ledger.build_party_ledger_pdf(db, company, ctx.party, ctx.direction, ctx.period)


async def _payment_register_xlsx(db: AsyncSession, company: Company, ctx: ReportContext) -> bytes:
    return await registers.build_payment_register_workbook(db, company, ctx.period)


async def _sales_register_xlsx(db: AsyncSession, company: Company, ctx: ReportContext) -> bytes:
    return await registers.build_sales_register_workbook(db, company, ctx.period)


async def _purchase_register_xlsx(db: AsyncSession, company: Company, ctx: ReportContext) -> bytes:
    return await registers.build_purchase_register_workbook(db, company, ctx.period)


async def _day_book_xlsx(db: AsyncSession, company: Company, ctx: ReportContext) -> bytes:
    return await registers.build_day_book_workbook(db, company, ctx.period)


async def _aging_xlsx(db: AsyncSession, company: Company, ctx: ReportContext) -> bytes:
    return await aging.build_aging_report_workbook(db, company, datetime.now(UTC).date())


async def _aging_pdf(db: AsyncSession, company: Company, ctx: ReportContext) -> bytes:
    return await aging.build_aging_report_pdf(db, company, datetime.now(UTC).date())


REPORTS: dict[str, ReportSpec] = {
    spec.key: spec
    for spec in [
        ReportSpec("full", "Full Data Export", _full_xlsx),
        ReportSpec("ledger", "Ledger", _ledger_xlsx, _ledger_pdf, needs_party=True),
        ReportSpec("payment_register", "Payment Register", _payment_register_xlsx),
        ReportSpec("sales_register", "Sales Register", _sales_register_xlsx),
        ReportSpec("purchase_register", "Purchase Register", _purchase_register_xlsx),
        ReportSpec("day_book", "Day Book", _day_book_xlsx),
        ReportSpec("aging", "Outstanding Aging Report", _aging_xlsx, _aging_pdf),
    ]
}
