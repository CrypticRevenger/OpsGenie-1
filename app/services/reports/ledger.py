"""Party ledger statement — the "single most-requested Tally report" per
PROJECT_STATUS.md: opening balance -> every invoice (debit)/payment (credit)
in the period, chronologically, with a running balance -> closing balance.

Sign convention matches app/services/party_outstanding.py exactly (invoice
total_amount is a debit, payment amount is a credit, for both directions
uniformly) — an all-time ledger's closing balance is therefore always equal
to calculate_party_outstanding()'s result for the same party (verified in
tests), since a fully-paid invoice's debit and its payments' credits net to
zero and only genuinely open invoices contribute to the total either way.
"""

from __future__ import annotations

import io
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from fpdf import FPDF
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.dealer import Dealer
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.supplier import Supplier
from app.services.money_format import format_inr
from app.services.party_outstanding import Direction
from app.services.reports import pdf_common, xlsx_common
from app.services.reports.period import ReportPeriod
from app.services.reports.statuses import EXCLUDED_STATUSES

_LEDGER_HEADERS = ("Date", "Type", "Reference", "Debit", "Credit", "Balance")
_LEDGER_FORMATS = [None, None, None, "money", "money", "money"]
_PDF_COL_WIDTHS = (24, 22, 36, 28, 28, 32)


@dataclass(frozen=True)
class _LedgerEntry:
    entry_date: date
    kind: str
    reference: str
    debit: Decimal | None
    credit: Decimal | None
    signed_amount: Decimal


@dataclass(frozen=True)
class _LedgerData:
    opening_balance: Decimal
    rows: list[tuple[_LedgerEntry, Decimal]]
    closing_balance: Decimal


async def _ledger_entries(
    db: AsyncSession, party_id: uuid.UUID, direction: Direction
) -> list[_LedgerEntry]:
    party_column = Invoice.dealer_id if direction == "receivable" else Invoice.supplier_id
    invoices = (
        await db.scalars(
            select(Invoice)
            .where(party_column == party_id, Invoice.status.notin_(EXCLUDED_STATUSES))
            .order_by(Invoice.invoice_date)
        )
    ).all()
    invoice_ids = [inv.id for inv in invoices]
    invoice_numbers = {inv.id: inv.invoice_number for inv in invoices}
    payments: list[Payment] = []
    if invoice_ids:
        payments = (
            await db.scalars(
                select(Payment).where(Payment.invoice_id.in_(invoice_ids)).order_by(Payment.payment_date)
            )
        ).all()

    entries = [
        _LedgerEntry(
            entry_date=inv.invoice_date,
            kind="Invoice",
            reference=inv.invoice_number,
            debit=inv.total_amount,
            credit=None,
            signed_amount=inv.total_amount,
        )
        for inv in invoices
    ]
    entries += [
        _LedgerEntry(
            entry_date=pay.payment_date,
            kind="Payment",
            reference=invoice_numbers.get(pay.invoice_id, ""),
            debit=None,
            credit=pay.amount,
            signed_amount=-pay.amount,
        )
        for pay in payments
    ]
    entries.sort(key=lambda e: e.entry_date)
    return entries


async def _load_ledger_data(
    db: AsyncSession, party_id: uuid.UUID, direction: Direction, period: ReportPeriod
) -> _LedgerData:
    opening_balance = Decimal("0.00")
    rows: list[tuple[_LedgerEntry, Decimal]] = []
    running = opening_balance
    for entry in await _ledger_entries(db, party_id, direction):
        if period.from_date is not None and entry.entry_date < period.from_date:
            opening_balance += entry.signed_amount
            running += entry.signed_amount
            continue
        if period.to_date is not None and entry.entry_date > period.to_date:
            continue
        running += entry.signed_amount
        rows.append((entry, running))
    return _LedgerData(opening_balance=opening_balance, rows=rows, closing_balance=running)


async def build_party_ledger_workbook(
    db: AsyncSession,
    company: Company,
    party: Dealer | Supplier,
    direction: Direction,
    period: ReportPeriod,
) -> bytes:
    data = await _load_ledger_data(db, party.id, direction, period)
    generated_at = datetime.now(UTC)

    wb = Workbook(write_only=True)
    ws = wb.create_sheet("Ledger")
    xlsx_common.write_meta_block(
        ws,
        report_name=f"Ledger — {party.name}",
        company_name=company.business_name,
        period_label=period.label,
        generated_at=generated_at,
        row_count=len(data.rows),
    )
    xlsx_common.write_header(ws, list(_LEDGER_HEADERS))
    xlsx_common.total_row(
        ws, ["", "Opening Balance", "", None, None, data.opening_balance], _LEDGER_FORMATS
    )
    for entry, balance in data.rows:
        xlsx_common.row(
            ws,
            [entry.entry_date, entry.kind, entry.reference, entry.debit, entry.credit, balance],
            _LEDGER_FORMATS,
        )
    xlsx_common.total_row(
        ws, ["", "Closing Balance", "", None, None, data.closing_balance], _LEDGER_FORMATS
    )

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


async def build_party_ledger_pdf(
    db: AsyncSession,
    company: Company,
    party: Dealer | Supplier,
    direction: Direction,
    period: ReportPeriod,
) -> bytes:
    data = await _load_ledger_data(db, party.id, direction, period)
    generated_at = datetime.now(UTC)

    pdf = FPDF(format="A4")
    pdf.add_page()
    unicode_ok = pdf_common.try_load_unicode_fonts(pdf)

    def money(amount: Decimal) -> str:
        return format_inr(amount) if unicode_ok else pdf_common.rs(amount)

    pdf_common.write_meta_header(
        pdf,
        report_name=f"Ledger - {party.name}",
        company_name=company.business_name,
        period_label=period.label,
        generated_at=generated_at,
        unicode_ok=unicode_ok,
    )

    rows: list[tuple[object, ...]] = [
        ("", "Opening Balance", "", "", "", money(data.opening_balance))
    ]
    for entry, balance in data.rows:
        rows.append(
            (
                entry.entry_date.isoformat(),
                entry.kind,
                entry.reference,
                money(entry.debit) if entry.debit is not None else "",
                money(entry.credit) if entry.credit is not None else "",
                money(balance),
            )
        )
    rows.append(("", "Closing Balance", "", "", "", money(data.closing_balance)))

    pdf_common.write_table(
        pdf,
        headers=_LEDGER_HEADERS,
        col_widths=_PDF_COL_WIDTHS,
        rows=rows,
        unicode_ok=unicode_ok,
        bold_rows={0, len(rows) - 1},
    )
    return bytes(pdf.output())
