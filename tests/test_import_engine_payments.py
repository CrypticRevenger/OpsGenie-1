"""ImportEngine integration tests — Phase 3B (payment reconciliation).

Same convention as test_import_engine.py: live DB, each test gets its own
Company via a unique whatsapp_number.

Requires postgres running with migrations applied:

    uv run alembic upgrade head
    uv run pytest tests/test_import_engine_payments.py -v
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from app.models.company import Company
from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceDirection, InvoiceSource, InvoiceStatus
from app.models.payment import Payment
from app.services.importer.engine import run_import
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

PAYMENT_HEADER = "party_name,payment_date,amount,method\n"


def _unique_phone() -> str:
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


async def _make_company(db: AsyncSession) -> uuid.UUID:
    company = Company(
        business_name="Payment Test Co", owner_name="Owner", whatsapp_number=_unique_phone()
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company.id


async def _make_dealer(db: AsyncSession, company_id: uuid.UUID, name: str) -> uuid.UUID:
    dealer = Dealer(company_id=company_id, name=name)
    db.add(dealer)
    await db.commit()
    await db.refresh(dealer)
    return dealer.id


async def _make_invoice(
    db: AsyncSession,
    company_id: uuid.UUID,
    dealer_id: uuid.UUID,
    invoice_number: str,
    invoice_date: date,
    total_amount: Decimal,
) -> Invoice:
    invoice = Invoice(
        company_id=company_id,
        invoice_number=invoice_number,
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        invoice_date=invoice_date,
        due_date=invoice_date,
        subtotal=total_amount,
        gst_amount=Decimal("0.00"),
        total_amount=total_amount,
        status=InvoiceStatus.Pending,
        source=InvoiceSource.csv_import,
    )
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)
    return invoice


def _csv(*rows: str) -> bytes:
    return (PAYMENT_HEADER + "\n".join(rows) + "\n").encode("utf-8")


# ── Basic allocation ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_payment_fully_pays_single_invoice(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id, "Ram Traders")
    invoice = await _make_invoice(
        db, company_id, dealer_id, "INV-P1", date(2026, 1, 5), Decimal("10000.00")
    )

    result = await run_import(
        db,
        company_id=company_id,
        direction="receivable",
        file_kind="payments",
        filename="payments.csv",
        contents=_csv("Ram Traders,2026-01-10,10000.00,Bank"),
    )

    assert result.rows_succeeded == 1
    assert result.rows_failed == 0

    await db.refresh(invoice)
    assert invoice.status == InvoiceStatus.Paid

    payment = await db.scalar(select(Payment).where(Payment.invoice_id == invoice.id))
    assert payment is not None
    assert payment.amount == Decimal("10000.00")


@pytest.mark.asyncio
async def test_payment_splits_fifo_across_two_invoices(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id, "Kumar Agency")
    older = await _make_invoice(
        db, company_id, dealer_id, "INV-P2", date(2026, 1, 5), Decimal("6000.00")
    )
    newer = await _make_invoice(
        db, company_id, dealer_id, "INV-P3", date(2026, 1, 10), Decimal("6000.00")
    )

    # Payment of 8000 should fully pay the older (6000) and partially pay the
    # newer (2000 of 6000), oldest invoice_date first.
    result = await run_import(
        db,
        company_id=company_id,
        direction="receivable",
        file_kind="payments",
        filename="payments.csv",
        contents=_csv("Kumar Agency,2026-01-15,8000.00,Bank"),
    )
    assert result.rows_succeeded == 1

    await db.refresh(older)
    await db.refresh(newer)
    assert older.status == InvoiceStatus.Paid
    assert newer.status == InvoiceStatus.Partially_Paid

    older_paid = await db.scalar(select(Payment).where(Payment.invoice_id == older.id))
    newer_paid = await db.scalar(select(Payment).where(Payment.invoice_id == newer.id))
    assert older_paid.amount == Decimal("6000.00")
    assert newer_paid.amount == Decimal("2000.00")


# ── Rejections ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_payment_exceeding_outstanding_rejected(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id, "Ganesh Store")
    invoice = await _make_invoice(
        db, company_id, dealer_id, "INV-P4", date(2026, 1, 5), Decimal("5000.00")
    )

    result = await run_import(
        db,
        company_id=company_id,
        direction="receivable",
        file_kind="payments",
        filename="payments.csv",
        contents=_csv("Ganesh Store,2026-01-10,9000.00,Bank"),
    )
    assert result.rows_failed == 1
    assert "exceeds total outstanding" in result.errors[0].reason

    await db.refresh(invoice)
    assert invoice.status == InvoiceStatus.Pending  # untouched


@pytest.mark.asyncio
async def test_payment_with_no_invoice_on_file_rejected_but_party_created(
    db: AsyncSession,
) -> None:
    """The NUTRICROP case: no invoice on file yet, so the payment fails — but
    the supplier record itself should still exist afterwards.
    """
    company_id = await _make_company(db)

    result = await run_import(
        db,
        company_id=company_id,
        direction="payable",
        file_kind="payments",
        filename="payments.csv",
        contents=_csv("NUTRICROP BIOSCIENCES,2026-01-08,45000.00,Bank"),
    )
    assert result.rows_failed == 1
    assert "no outstanding invoice on file" in result.errors[0].reason

    from app.models.supplier import Supplier

    supplier = await db.scalar(
        select(Supplier).where(
            Supplier.company_id == company_id, Supplier.name == "NUTRICROP BIOSCIENCES"
        )
    )
    assert supplier is not None  # party persisted despite the payment failing


@pytest.mark.asyncio
async def test_zero_amount_payment_fails_the_row_not_a_silent_success(db: AsyncSession) -> None:
    """Regression: a zero/negative amount used to slip past parse_amount (no
    guard), then allocate_payment_fifo's allocation loop exited immediately
    with zero Payments written — but the row was still recorded as a
    *success*, since nothing ever raised. Must now fail the row instead.
    """
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id, "Zero Amount Traders")
    await _make_invoice(
        db, company_id, dealer_id, "INV-P6", date(2026, 1, 5), Decimal("5000.00")
    )

    result = await run_import(
        db,
        company_id=company_id,
        direction="receivable",
        file_kind="payments",
        filename="payments.csv",
        contents=_csv("Zero Amount Traders,2026-01-10,0.00,Bank"),
    )
    assert result.rows_succeeded == 0
    assert result.rows_failed == 1

    payments = (
        (await db.execute(select(Payment).where(Payment.company_id == company_id))).scalars().all()
    )
    assert len(payments) == 0


@pytest.mark.asyncio
async def test_allocate_payment_fifo_rejects_zero_amount_directly(db: AsyncSession) -> None:
    """Defense-in-depth: the guard lives inside allocate_payment_fifo itself,
    not just at the CSV row-parsing call site, so writes/payments.py's
    record_payment (the WhatsApp path) is protected too.
    """
    from app.services.importer.payment_row import allocate_payment_fifo

    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id, "Direct Call Traders")
    await _make_invoice(
        db, company_id, dealer_id, "INV-P7", date(2026, 1, 5), Decimal("5000.00")
    )

    with pytest.raises(ValueError, match="greater than zero"):
        await allocate_payment_fifo(
            db,
            company_id=company_id,
            direction="receivable",
            party_id=dealer_id,
            party_name="Direct Call Traders",
            amount=Decimal("0.00"),
            payment_date=date(2026, 1, 10),
            method="Bank",
            voucher_reference="",
            source_file="test.csv",
            row_number=1,
            source_row_key="test-key",
        )


# ── Idempotency ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reimporting_same_payments_file_is_idempotent(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id, "Sharma Traders")
    await _make_invoice(db, company_id, dealer_id, "INV-P5", date(2026, 1, 5), Decimal("7000.00"))

    contents = _csv("Sharma Traders,2026-01-10,7000.00,Bank")

    first = await run_import(
        db,
        company_id=company_id,
        direction="receivable",
        file_kind="payments",
        filename="payments.csv",
        contents=contents,
    )
    assert first.rows_succeeded == 1
    assert first.rows_skipped == 0

    second = await run_import(
        db,
        company_id=company_id,
        direction="receivable",
        file_kind="payments",
        filename="payments.csv",
        contents=contents,
    )
    assert second.rows_succeeded == 0
    assert second.rows_skipped == 1

    payments = (
        (await db.execute(select(Payment).where(Payment.company_id == company_id))).scalars().all()
    )
    assert len(payments) == 1  # no duplicate payment created


# ── PDF import (Tally Receipt/Payment Voucher printouts) ───────────────────────


def _voucher_pdf(*pages: list[str]) -> bytes:
    from fpdf import FPDF

    pdf = FPDF()
    for lines in pages:
        pdf.add_page()
        pdf.set_font("Helvetica", size=11)
        for line in lines:
            pdf.cell(0, 6, text=line, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


@pytest.mark.asyncio
async def test_pdf_receipt_voucher_allocates_against_open_invoice(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id, "Reliable Medical Store")
    invoice = await _make_invoice(
        db, company_id, dealer_id, "785", date(2026, 1, 23), Decimal("23992.00")
    )

    contents = _voucher_pdf(
        [
            "ACME AGRI SUPPLIES",
            "1 Market Road,",
            "Sometown-560001",
            "Receipt Voucher",
            "No. : 9 Dated : 6-Jan-26",
            "Particulars Amount",
            "Account :",
            "M/s.Reliable Medical Store 23,992.00",
            "Through :",
            "IDFC FIRST BANK",
        ]
    )

    result = await run_import(
        db,
        company_id=company_id,
        direction="receivable",
        file_kind="payments",
        filename="receipts.pdf",
        contents=contents,
    )

    assert result.rows_succeeded == 1
    assert result.rows_failed == 0
    assert result.source_format == "pdf"

    await db.refresh(invoice)
    assert invoice.status == InvoiceStatus.Paid
    payment = await db.scalar(select(Payment).where(Payment.invoice_id == invoice.id))
    assert payment is not None
    assert payment.amount == Decimal("23992.00")
