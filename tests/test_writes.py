"""record_payment (Phase 2A deterministic write service) tests.

Same convention as tests/test_import_engine_payments.py: live DB, each test
gets its own Company via a unique whatsapp_number. Never touches the real
AP BIOCARE company — that data is this project's standing read-only
reconciliation baseline.

    uv run alembic upgrade head
    uv run pytest tests/test_writes.py -v
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from app.models.company import Company
from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceDirection, InvoiceSource, InvoiceStatus
from app.models.payment import Payment, PaymentSource
from app.services.writes.payments import record_payment
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _unique_phone() -> str:
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


async def _make_company(db: AsyncSession) -> Company:
    company = Company(
        business_name="Writes Test Co", owner_name="Owner", whatsapp_number=_unique_phone()
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company


async def _make_dealer(db: AsyncSession, company_id: uuid.UUID, name: str) -> Dealer:
    dealer = Dealer(company_id=company_id, name=name)
    db.add(dealer)
    await db.commit()
    await db.refresh(dealer)
    return dealer


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


@pytest.mark.asyncio
async def test_record_payment_fully_pays_single_invoice(db: AsyncSession) -> None:
    company = await _make_company(db)
    dealer = await _make_dealer(db, company.id, "Ram Traders")
    invoice = await _make_invoice(
        db, company.id, dealer.id, "INV-W1", date(2026, 1, 5), Decimal("10000.00")
    )

    result = await record_payment(
        db,
        company,
        direction="receivable",
        party_name="Ram Traders",
        amount=Decimal("10000.00"),
        payment_date=date(2026, 1, 10),
    )
    await db.commit()

    assert result.party_name == "Ram Traders"
    assert result.amount_allocated == Decimal("10000.00")
    assert result.invoice_numbers == ["INV-W1"]
    assert result.remaining_outstanding == Decimal("0.00")

    await db.refresh(invoice)
    assert invoice.status == InvoiceStatus.Paid
    payment = await db.scalar(select(Payment).where(Payment.invoice_id == invoice.id))
    assert payment is not None
    assert payment.source == PaymentSource.whatsapp


@pytest.mark.asyncio
async def test_record_payment_splits_fifo_across_two_invoices(db: AsyncSession) -> None:
    company = await _make_company(db)
    dealer = await _make_dealer(db, company.id, "Kumar Agency")
    older = await _make_invoice(
        db, company.id, dealer.id, "INV-W2", date(2026, 1, 5), Decimal("6000.00")
    )
    newer = await _make_invoice(
        db, company.id, dealer.id, "INV-W3", date(2026, 1, 10), Decimal("6000.00")
    )

    result = await record_payment(
        db,
        company,
        direction="receivable",
        party_name="Kumar Agency",
        amount=Decimal("8000.00"),
        payment_date=date(2026, 1, 15),
    )
    await db.commit()

    assert set(result.invoice_numbers) == {"INV-W2", "INV-W3"}
    assert result.remaining_outstanding == Decimal("4000.00")

    await db.refresh(older)
    await db.refresh(newer)
    assert older.status == InvoiceStatus.Paid
    assert newer.status == InvoiceStatus.Partially_Paid


@pytest.mark.asyncio
async def test_record_payment_no_open_invoice_raises(db: AsyncSession) -> None:
    company = await _make_company(db)

    with pytest.raises(ValueError, match="no outstanding invoice on file"):
        await record_payment(
            db,
            company,
            direction="payable",
            party_name="Brand New Supplier",
            amount=Decimal("5000.00"),
            payment_date=date(2026, 1, 10),
        )


@pytest.mark.asyncio
async def test_record_payment_exceeding_outstanding_raises(db: AsyncSession) -> None:
    company = await _make_company(db)
    dealer = await _make_dealer(db, company.id, "Ganesh Store")
    invoice = await _make_invoice(
        db, company.id, dealer.id, "INV-W4", date(2026, 1, 5), Decimal("5000.00")
    )

    with pytest.raises(ValueError, match="exceeds total outstanding"):
        await record_payment(
            db,
            company,
            direction="receivable",
            party_name="Ganesh Store",
            amount=Decimal("9000.00"),
            payment_date=date(2026, 1, 10),
        )

    await db.refresh(invoice)
    assert invoice.status == InvoiceStatus.Pending  # untouched


@pytest.mark.asyncio
async def test_record_payment_creates_unknown_party(db: AsyncSession) -> None:
    """A dealer/supplier not yet on file gets created by find_or_create_party
    inside record_payment — the guided flow only confirms intent beforehand,
    the actual DB row is written here at execute time.
    """
    company = await _make_company(db)

    with pytest.raises(ValueError, match="no outstanding invoice on file"):
        await record_payment(
            db,
            company,
            direction="receivable",
            party_name="Brand New Dealer",
            amount=Decimal("1000.00"),
            payment_date=date(2026, 1, 10),
        )

    dealer = await db.scalar(
        select(Dealer).where(Dealer.company_id == company.id, Dealer.name == "Brand New Dealer")
    )
    assert dealer is not None  # party persisted despite the payment failing
