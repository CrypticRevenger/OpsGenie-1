"""ImportEngine integration tests — Phase 3A (invoice import).

Tests against a live DB, following the same convention as test_admin.py:
each test creates its own Company with a unique whatsapp_number, so tests
don't collide even though rows aren't rolled back (ImportEngine commits
internally — that's the point of the transaction-per-file design).

Requires postgres running with migrations applied:

    uv run alembic upgrade head
    uv run pytest tests/test_import_engine.py -v
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models.business_event import BusinessEvent, BusinessEventType
from app.models.company import Company
from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceStatus
from app.services.importer.engine import (
    UnrecognisedFormatError,
    UnsupportedFileError,
    run_import,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

CANONICAL_HEADER = (
    "invoice_number,direction,party_name,invoice_date,due_date,"
    "subtotal,gst_amount,total_amount,description\n"
)


def _unique_phone() -> str:
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


async def _make_company(db: AsyncSession) -> uuid.UUID:
    company = Company(
        business_name="Import Test Co",
        owner_name="Owner",
        whatsapp_number=_unique_phone(),
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company.id


def _csv(*rows: str) -> bytes:
    return (CANONICAL_HEADER + "\n".join(rows) + "\n").encode("utf-8")


# ── Basic create ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_import_creates_dealer_and_invoice(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    contents = _csv(
        "INV-1,receivable,Ram Traders,2026-01-05,2026-02-04,10000.00,0.00,10000.00,rice"
    )

    result = await run_import(
        db,
        company_id=company_id,
        direction="receivable",
        file_kind="invoices",
        filename="test.csv",
        contents=contents,
    )

    assert result.rows_succeeded == 1
    assert result.rows_failed == 0

    dealer = await db.scalar(select(Dealer).where(Dealer.company_id == company_id))
    assert dealer is not None
    assert dealer.name == "Ram Traders"

    invoice = await db.scalar(select(Invoice).where(Invoice.company_id == company_id))
    assert invoice is not None
    assert invoice.invoice_number == "INV-1"
    assert invoice.total_amount == Decimal("10000.00")
    assert invoice.dealer_id == dealer.id
    assert invoice.status == InvoiceStatus.Pending

    event = await db.scalar(
        select(BusinessEvent).where(
            BusinessEvent.company_id == company_id,
            BusinessEvent.event_type == BusinessEventType.invoice_created,
        )
    )
    assert event is not None
    assert event.entity_id == invoice.id
    assert event.payload["invoice_number"] == "INV-1"


@pytest.mark.asyncio
async def test_import_matches_existing_dealer_case_insensitive(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    db.add(Dealer(company_id=company_id, name="Ram Traders"))
    await db.commit()

    contents = _csv(
        "INV-2,receivable,ram traders,2026-01-05,2026-02-04,5000.00,0.00,5000.00,dal"
    )
    await run_import(
        db,
        company_id=company_id,
        direction="receivable",
        file_kind="invoices",
        filename="test.csv",
        contents=contents,
    )

    dealers = (
        (await db.execute(select(Dealer).where(Dealer.company_id == company_id)))
        .scalars()
        .all()
    )
    assert len(dealers) == 1  # no duplicate dealer created


# ── Idempotency ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reimporting_same_file_is_idempotent(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    contents = _csv(
        "INV-3,receivable,Kumar Agency,2026-01-05,2026-02-04,8000.00,0.00,8000.00,oil"
    )

    first = await run_import(
        db, company_id=company_id, direction="receivable", file_kind="invoices",
        filename="test.csv", contents=contents,
    )
    assert first.rows_succeeded == 1
    assert first.rows_skipped == 0

    second = await run_import(
        db, company_id=company_id, direction="receivable", file_kind="invoices",
        filename="test.csv", contents=contents,
    )
    assert second.rows_succeeded == 0
    assert second.rows_skipped == 1
    assert second.rows_failed == 0

    invoices = (
        (await db.execute(select(Invoice).where(Invoice.company_id == company_id)))
        .scalars()
        .all()
    )
    assert len(invoices) == 1  # no duplicate invoice created


@pytest.mark.asyncio
async def test_conflicting_duplicate_invoice_number_fails(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    await run_import(
        db, company_id=company_id, direction="receivable", file_kind="invoices",
        filename="first.csv",
        contents=_csv(
            "INV-4,receivable,Ganesh Store,2026-01-05,2026-02-04,1000.00,0.00,1000.00,x"
        ),
    )

    # Same invoice_number, different amount -> real conflict, not a duplicate.
    result = await run_import(
        db, company_id=company_id, direction="receivable", file_kind="invoices",
        filename="second.csv",
        contents=_csv(
            "INV-4,receivable,Ganesh Store,2026-01-05,2026-02-04,9999.00,0.00,9999.00,x"
        ),
    )
    assert result.rows_failed == 1
    assert result.rows_succeeded == 0
    assert "different data" in result.errors[0].reason


# ── Row isolation ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bad_row_does_not_abort_batch(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    contents = _csv(
        "INV-5,receivable,Good Dealer,2026-01-05,2026-02-04,1000.00,0.00,1000.00,x",
        "INV-6,receivable,Bad Dealer,not-a-date,2026-02-04,1000.00,0.00,1000.00,x",
        "INV-7,receivable,Another Good Dealer,2026-01-06,2026-02-05,2000.00,0.00,2000.00,x",
    )

    result = await run_import(
        db, company_id=company_id, direction="receivable", file_kind="invoices",
        filename="test.csv", contents=contents,
    )

    assert result.rows_succeeded == 2
    assert result.rows_failed == 1
    assert result.errors[0].row_number == 2

    invoices = (
        (await db.execute(select(Invoice).where(Invoice.company_id == company_id)))
        .scalars()
        .all()
    )
    assert {inv.invoice_number for inv in invoices} == {"INV-5", "INV-7"}


# ── Whole-file rejection ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_missing_required_column_rejects_whole_file(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    contents = b"invoice_number,direction,party_name\nINV-8,receivable,X\n"

    with pytest.raises(UnrecognisedFormatError):
        await run_import(
            db, company_id=company_id, direction="receivable", file_kind="invoices",
            filename="test.csv", contents=contents,
        )


@pytest.mark.asyncio
async def test_unsupported_file_extension_rejected(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    with pytest.raises(UnsupportedFileError):
        await run_import(
            db, company_id=company_id, direction="receivable", file_kind="invoices",
            filename="test.pdf", contents=b"whatever",
        )


# ── due_date resolution (no hardcoded terms) ─────────────────────────────────


@pytest.mark.asyncio
async def test_blank_due_date_uses_party_payment_terms_days(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    db.add(Dealer(company_id=company_id, name="Termed Dealer", payment_terms_days=15))
    await db.commit()

    contents = _csv(
        "INV-9,receivable,Termed Dealer,2026-01-05,,4000.00,0.00,4000.00,x"
    )
    await run_import(
        db, company_id=company_id, direction="receivable", file_kind="invoices",
        filename="test.csv", contents=contents,
    )

    invoice = await db.scalar(
        select(Invoice).where(Invoice.company_id == company_id, Invoice.invoice_number == "INV-9")
    )
    assert invoice.due_date.isoformat() == "2026-01-20"  # +15 days, not a hardcoded 30


@pytest.mark.asyncio
async def test_blank_due_date_with_no_known_terms_defaults_to_invoice_date(
    db: AsyncSession,
) -> None:
    company_id = await _make_company(db)
    contents = _csv(
        "INV-10,receivable,No Terms Dealer,2026-01-05,,4000.00,0.00,4000.00,x"
    )
    await run_import(
        db, company_id=company_id, direction="receivable", file_kind="invoices",
        filename="test.csv", contents=contents,
    )

    invoice = await db.scalar(
        select(Invoice).where(Invoice.company_id == company_id, Invoice.invoice_number == "INV-10")
    )
    assert invoice.due_date.isoformat() == "2026-01-05"  # net-0, not an invented default


# ── Regression: xlsx native date cells (found in code review) ────────────────


@pytest.mark.asyncio
async def test_xlsx_native_date_cells_parse_correctly(db: AsyncSession) -> None:
    """openpyxl deserialises date-formatted cells as datetime.datetime, not a
    string — a real .xlsx export with actual date cells (the normal case, not
    text-formatted dates) must still import cleanly.
    """
    import io
    from datetime import date

    from openpyxl import Workbook

    company_id = await _make_company(db)

    wb = Workbook()
    ws = wb.active
    ws.append(
        [
            "invoice_number", "direction", "party_name", "invoice_date", "due_date",
            "subtotal", "gst_amount", "total_amount", "description",
        ]
    )
    ws.append(
        [
            "INV-XL-1", "receivable", "Excel Dealer", date(2026, 1, 5), date(2026, 2, 4),
            "6000.00", "0.00", "6000.00", "goods",
        ]
    )
    buf = io.BytesIO()
    wb.save(buf)

    result = await run_import(
        db, company_id=company_id, direction="receivable", file_kind="invoices",
        filename="native_dates.xlsx", contents=buf.getvalue(),
    )

    assert result.rows_failed == 0, result.errors
    assert result.rows_succeeded == 1

    invoice = await db.scalar(
        select(Invoice).where(
            Invoice.company_id == company_id, Invoice.invoice_number == "INV-XL-1"
        )
    )
    assert invoice.invoice_date.isoformat() == "2026-01-05"
    assert invoice.due_date.isoformat() == "2026-02-04"


# ── Regression: party name matching must not treat SQL wildcards as literal ──


@pytest.mark.asyncio
async def test_party_name_with_percent_sign_does_not_wildcard_match(db: AsyncSession) -> None:
    """find_or_create_party must do an exact case-insensitive match — a name
    containing '%' or '_' is not a LIKE pattern, it's a literal business name.
    """
    company_id = await _make_company(db)
    db.add(Dealer(company_id=company_id, name="Organic Traders"))
    await db.commit()

    contents = _csv(
        "INV-WILD-1,receivable,100% Organic Traders,2026-01-05,2026-02-04,"
        "3000.00,0.00,3000.00,x"
    )
    await run_import(
        db, company_id=company_id, direction="receivable", file_kind="invoices",
        filename="test.csv", contents=contents,
    )

    dealers = (
        (await db.execute(select(Dealer).where(Dealer.company_id == company_id)))
        .scalars()
        .all()
    )
    names = {d.name for d in dealers}
    # Must create a SEPARATE dealer, not silently match "Organic Traders" via
    # '%' being treated as a SQL LIKE wildcard.
    assert names == {"Organic Traders", "100% Organic Traders"}


# ── Regression: whole-file decode/format errors surface cleanly ──────────────


@pytest.mark.asyncio
async def test_non_utf8_csv_is_rejected_cleanly_not_as_a_crash(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    # A cp1252 "smart quote" (0x92 = U+2019 RIGHT SINGLE QUOTATION MARK) is a
    # byte sequence that is not valid UTF-8 on its own.
    bad_bytes = CANONICAL_HEADER.encode("utf-8") + b"INV-BAD,receivable,Ram\x92s Traders"

    # Should not raise UnicodeDecodeError — either decodes via the cp1252
    # fallback or raises the clean UnsupportedFileError, never a bare crash.
    try:
        await run_import(
            db, company_id=company_id, direction="receivable", file_kind="invoices",
            filename="bad_encoding.csv", contents=bad_bytes,
        )
    except UnsupportedFileError:
        pass  # acceptable clean rejection


@pytest.mark.asyncio
async def test_corrupt_xlsx_is_rejected_cleanly_not_as_a_crash(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    with pytest.raises(UnsupportedFileError):
        await run_import(
            db, company_id=company_id, direction="receivable", file_kind="invoices",
            filename="corrupt.xlsx", contents=b"this is not a real xlsx file",
        )
