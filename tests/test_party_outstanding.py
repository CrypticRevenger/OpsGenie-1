"""DealerOutstandingCalculator tests — Phase 5A.

Requires postgres running with migrations applied:

    uv run alembic upgrade head
    uv run pytest tests/test_party_outstanding.py -v
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
from app.services.party_outstanding import (
    calculate_outstanding_for_company,
    calculate_party_outstanding,
)
from sqlalchemy.ext.asyncio import AsyncSession


def _unique_phone() -> str:
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


async def _make_company(db: AsyncSession) -> uuid.UUID:
    company = Company(
        business_name="Outstanding Test Co", owner_name="Owner", whatsapp_number=_unique_phone()
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
    total_amount: Decimal,
    status: InvoiceStatus,
) -> Invoice:
    invoice = Invoice(
        company_id=company_id,
        invoice_number=invoice_number,
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        invoice_date=date(2026, 1, 5),
        due_date=date(2026, 1, 5),
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


async def _make_payment(
    db: AsyncSession, company_id: uuid.UUID, invoice_id: uuid.UUID, amount: Decimal
) -> None:
    db.add(
        Payment(
            company_id=company_id, invoice_id=invoice_id, amount=amount,
            payment_date=date(2026, 1, 10),
        )
    )
    await db.commit()


@pytest.mark.asyncio
async def test_pending_invoice_fully_outstanding(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id, "Dealer A")
    await _make_invoice(
        db, company_id, dealer_id, "INV-OUT-1", Decimal("10000.00"), InvoiceStatus.Pending
    )

    outstanding = await calculate_party_outstanding(db, direction="receivable", party_id=dealer_id)
    assert outstanding == Decimal("10000.00")


@pytest.mark.asyncio
async def test_partially_paid_invoice_reduces_outstanding(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id, "Dealer B")
    invoice = await _make_invoice(
        db, company_id, dealer_id, "INV-OUT-2", Decimal("10000.00"), InvoiceStatus.Partially_Paid
    )
    await _make_payment(db, company_id, invoice.id, Decimal("4000.00"))

    outstanding = await calculate_party_outstanding(db, direction="receivable", party_id=dealer_id)
    assert outstanding == Decimal("6000.00")


@pytest.mark.asyncio
async def test_paid_invoice_excluded_from_outstanding(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id, "Dealer C")
    invoice = await _make_invoice(
        db, company_id, dealer_id, "INV-OUT-3", Decimal("5000.00"), InvoiceStatus.Paid
    )
    await _make_payment(db, company_id, invoice.id, Decimal("5000.00"))

    outstanding = await calculate_party_outstanding(db, direction="receivable", party_id=dealer_id)
    assert outstanding == Decimal("0.00")


@pytest.mark.asyncio
async def test_overdue_status_included_in_outstanding(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id, "Dealer D")
    await _make_invoice(
        db, company_id, dealer_id, "INV-OUT-4", Decimal("7000.00"), InvoiceStatus.Overdue
    )

    outstanding = await calculate_party_outstanding(db, direction="receivable", party_id=dealer_id)
    assert outstanding == Decimal("7000.00")


@pytest.mark.asyncio
async def test_cancelled_invoice_excluded(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id, "Dealer E")
    await _make_invoice(
        db, company_id, dealer_id, "INV-OUT-5", Decimal("3000.00"), InvoiceStatus.Cancelled
    )

    outstanding = await calculate_party_outstanding(db, direction="receivable", party_id=dealer_id)
    assert outstanding == Decimal("0.00")


@pytest.mark.asyncio
async def test_dealer_with_no_invoices_has_zero_outstanding(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id, "Dealer F")

    outstanding = await calculate_party_outstanding(db, direction="receivable", party_id=dealer_id)
    assert outstanding == Decimal("0.00")


@pytest.mark.asyncio
async def test_batched_calculation_matches_single_party_calculation(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer_a = await _make_dealer(db, company_id, "Dealer G")
    dealer_b = await _make_dealer(db, company_id, "Dealer H")
    await _make_invoice(
        db, company_id, dealer_a, "INV-OUT-6", Decimal("1000.00"), InvoiceStatus.Pending
    )
    invoice_b = await _make_invoice(
        db, company_id, dealer_b, "INV-OUT-7", Decimal("2000.00"), InvoiceStatus.Partially_Paid
    )
    await _make_payment(db, company_id, invoice_b.id, Decimal("500.00"))

    batched = await calculate_outstanding_for_company(
        db, company_id=company_id, direction="receivable"
    )
    single_a = await calculate_party_outstanding(db, direction="receivable", party_id=dealer_a)
    single_b = await calculate_party_outstanding(db, direction="receivable", party_id=dealer_b)

    assert batched[dealer_a] == single_a == Decimal("1000.00")
    assert batched[dealer_b] == single_b == Decimal("1500.00")
