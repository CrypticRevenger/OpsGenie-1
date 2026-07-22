"""Advisory (party, date, amount) duplicate-lookup tests.

Requires postgres running with migrations applied:

    uv run alembic upgrade head
    uv run pytest tests/test_duplicate_check.py -v
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from app.models.company import Company
from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceDirection, InvoiceSource, InvoiceStatus
from app.models.payment import Payment
from app.models.supplier import Supplier
from app.services.duplicate_check import find_similar_order, find_similar_payment
from sqlalchemy.ext.asyncio import AsyncSession

TODAY = date(2026, 1, 15)


def _unique_phone() -> str:
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


async def _make_company(db: AsyncSession) -> uuid.UUID:
    company = Company(
        business_name="Duplicate Check Test Co", owner_name="Owner", whatsapp_number=_unique_phone()
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company.id


async def _make_dealer(db: AsyncSession, company_id: uuid.UUID) -> uuid.UUID:
    dealer = Dealer(company_id=company_id, name="Ram Traders")
    db.add(dealer)
    await db.commit()
    await db.refresh(dealer)
    return dealer.id


async def _make_supplier(db: AsyncSession, company_id: uuid.UUID) -> uuid.UUID:
    supplier = Supplier(company_id=company_id, name="Metro Distributors")
    db.add(supplier)
    await db.commit()
    await db.refresh(supplier)
    return supplier.id


async def _make_invoice(
    db: AsyncSession,
    company_id: uuid.UUID,
    *,
    direction: InvoiceDirection,
    dealer_id: uuid.UUID | None = None,
    supplier_id: uuid.UUID | None = None,
    invoice_date: date,
    total_amount: Decimal,
    status: InvoiceStatus = InvoiceStatus.Pending,
) -> Invoice:
    invoice = Invoice(
        company_id=company_id,
        invoice_number=f"INV-{uuid.uuid4().hex[:10]}",
        direction=direction,
        dealer_id=dealer_id,
        supplier_id=supplier_id,
        invoice_date=invoice_date,
        due_date=invoice_date + timedelta(days=14),
        subtotal=total_amount,
        gst_amount=Decimal("0.00"),
        total_amount=total_amount,
        status=status,
        source=InvoiceSource.csv_import,
    )
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)
    return invoice


@pytest.mark.asyncio
async def test_find_similar_payment_matches_exact_party_date_amount(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id)
    invoice = await _make_invoice(
        db,
        company_id,
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        invoice_date=TODAY,
        total_amount=Decimal("50000.00"),
    )
    db.add(
        Payment(
            company_id=company_id,
            invoice_id=invoice.id,
            amount=Decimal("10000.00"),
            payment_date=TODAY,
        )
    )
    await db.commit()

    match = await find_similar_payment(
        db,
        company_id=company_id,
        direction="receivable",
        party_id=dealer_id,
        payment_date=TODAY,
        amount=Decimal("10000.00"),
    )
    assert match is not None


@pytest.mark.asyncio
async def test_find_similar_payment_no_match_on_different_amount(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id)
    invoice = await _make_invoice(
        db,
        company_id,
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        invoice_date=TODAY,
        total_amount=Decimal("50000.00"),
    )
    db.add(
        Payment(
            company_id=company_id,
            invoice_id=invoice.id,
            amount=Decimal("10000.00"),
            payment_date=TODAY,
        )
    )
    await db.commit()

    match = await find_similar_payment(
        db,
        company_id=company_id,
        direction="receivable",
        party_id=dealer_id,
        payment_date=TODAY,
        amount=Decimal("20000.00"),  # different amount
    )
    assert match is None


@pytest.mark.asyncio
async def test_find_similar_payment_no_match_on_different_date(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id)
    invoice = await _make_invoice(
        db,
        company_id,
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        invoice_date=TODAY,
        total_amount=Decimal("50000.00"),
    )
    db.add(
        Payment(
            company_id=company_id,
            invoice_id=invoice.id,
            amount=Decimal("10000.00"),
            payment_date=TODAY,
        )
    )
    await db.commit()

    match = await find_similar_payment(
        db,
        company_id=company_id,
        direction="receivable",
        party_id=dealer_id,
        payment_date=TODAY - timedelta(days=1),
        amount=Decimal("10000.00"),
    )
    assert match is None


@pytest.mark.asyncio
async def test_find_similar_payment_no_match_on_different_party(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id)
    other_dealer = Dealer(company_id=company_id, name="Other Dealer")
    db.add(other_dealer)
    invoice = await _make_invoice(
        db,
        company_id,
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        invoice_date=TODAY,
        total_amount=Decimal("50000.00"),
    )
    await db.flush()
    db.add(
        Payment(
            company_id=company_id,
            invoice_id=invoice.id,
            amount=Decimal("10000.00"),
            payment_date=TODAY,
        )
    )
    await db.commit()

    match = await find_similar_payment(
        db,
        company_id=company_id,
        direction="receivable",
        party_id=other_dealer.id,
        payment_date=TODAY,
        amount=Decimal("10000.00"),
    )
    assert match is None


@pytest.mark.asyncio
async def test_find_similar_payment_supplier_direction(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    supplier_id = await _make_supplier(db, company_id)
    invoice = await _make_invoice(
        db,
        company_id,
        direction=InvoiceDirection.payable,
        supplier_id=supplier_id,
        invoice_date=TODAY,
        total_amount=Decimal("30000.00"),
    )
    db.add(
        Payment(
            company_id=company_id,
            invoice_id=invoice.id,
            amount=Decimal("15000.00"),
            payment_date=TODAY,
        )
    )
    await db.commit()

    match = await find_similar_payment(
        db,
        company_id=company_id,
        direction="payable",
        party_id=supplier_id,
        payment_date=TODAY,
        amount=Decimal("15000.00"),
    )
    assert match is not None


@pytest.mark.asyncio
async def test_find_similar_order_matches_exact_dealer_date_total(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id)
    await _make_invoice(
        db,
        company_id,
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        invoice_date=TODAY,
        total_amount=Decimal("5000.00"),
    )

    match = await find_similar_order(
        db,
        company_id=company_id,
        dealer_id=dealer_id,
        invoice_date=TODAY,
        total_amount=Decimal("5000.00"),
    )
    assert match is not None


@pytest.mark.asyncio
async def test_find_similar_order_no_match_on_different_total(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id)
    await _make_invoice(
        db,
        company_id,
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        invoice_date=TODAY,
        total_amount=Decimal("5000.00"),
    )

    match = await find_similar_order(
        db,
        company_id=company_id,
        dealer_id=dealer_id,
        invoice_date=TODAY,
        total_amount=Decimal("9999.00"),
    )
    assert match is None


@pytest.mark.asyncio
async def test_find_similar_order_excludes_cancelled_invoices(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id)
    await _make_invoice(
        db,
        company_id,
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        invoice_date=TODAY,
        total_amount=Decimal("5000.00"),
        status=InvoiceStatus.Cancelled,
    )

    match = await find_similar_order(
        db,
        company_id=company_id,
        dealer_id=dealer_id,
        invoice_date=TODAY,
        total_amount=Decimal("5000.00"),
    )
    assert match is None
