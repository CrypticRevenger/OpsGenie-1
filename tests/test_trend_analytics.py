"""Trend analytics tests — week-over-week cash, 30d dealer/product movement.

Requires postgres running with migrations applied:

    uv run alembic upgrade head
    uv run pytest tests/test_trend_analytics.py -v
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from app.models.company import Company
from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceDirection, InvoiceSource, InvoiceStatus
from app.models.invoice_item import InvoiceItem
from app.models.payment import Payment, PaymentSource
from app.models.product import Product
from app.services.party_outstanding import calculate_outstanding_for_company_as_of
from app.services.snapshot import DEFAULT_BUSINESS_TIMEZONE, business_now
from app.services.trend_analytics import (
    build_cash_trend,
    build_dealer_trends,
    build_product_sales_trends,
)
from sqlalchemy.ext.asyncio import AsyncSession

TODAY = business_now(DEFAULT_BUSINESS_TIMEZONE).date()


def _unique_phone() -> str:
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


async def _make_company(db: AsyncSession) -> uuid.UUID:
    company = Company(
        business_name="Trend Test Co", owner_name="Owner", whatsapp_number=_unique_phone()
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company.id


async def _make_dealer(
    db: AsyncSession, company_id: uuid.UUID, name: str = "Trend Dealer"
) -> Dealer:
    dealer = Dealer(company_id=company_id, name=name)
    db.add(dealer)
    await db.commit()
    await db.refresh(dealer)
    return dealer


async def _make_product(db: AsyncSession, company_id: uuid.UUID, name: str) -> Product:
    product = Product(company_id=company_id, name=name, stock_quantity=Decimal("1000"))
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


async def _make_invoice(
    db: AsyncSession,
    company_id: uuid.UUID,
    *,
    dealer_id: uuid.UUID,
    total: Decimal,
    invoice_date: date,
    status: InvoiceStatus = InvoiceStatus.Pending,
    product_id: uuid.UUID | None = None,
    quantity: Decimal = Decimal("10"),
) -> Invoice:
    invoice = Invoice(
        company_id=company_id,
        invoice_number=f"INV-{uuid.uuid4().hex[:10]}",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        invoice_date=invoice_date,
        due_date=invoice_date + timedelta(days=14),
        subtotal=total,
        gst_amount=Decimal("0.00"),
        total_amount=total,
        status=status,
        source=InvoiceSource.csv_import,
    )
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)
    if product_id is not None:
        db.add(
            InvoiceItem(
                invoice_id=invoice.id,
                product_id=product_id,
                description="line",
                quantity=quantity,
                unit_price=total / quantity,
                line_total=total,
            )
        )
        await db.commit()
    return invoice


async def _make_payment(
    db: AsyncSession,
    company_id: uuid.UUID,
    invoice_id: uuid.UUID,
    amount: Decimal,
    payment_date: date,
) -> None:
    db.add(
        Payment(
            company_id=company_id,
            invoice_id=invoice_id,
            amount=amount,
            payment_date=payment_date,
            source=PaymentSource.csv_import,
        )
    )
    await db.commit()


@pytest.mark.asyncio
async def test_cash_trend_window_boundary(db: AsyncSession) -> None:
    """A payment dated exactly on the current-window/prior-window boundary
    lands in the current window (current_start), not the prior one.
    """
    company_id = await _make_company(db)
    dealer = await _make_dealer(db, company_id)
    invoice = await _make_invoice(
        db,
        company_id,
        dealer_id=dealer.id,
        total=Decimal("1000"),
        invoice_date=TODAY - timedelta(days=20),
    )
    # 7-day window: current = [today-6, today], prior = [today-13, today-7].
    boundary_date = TODAY - timedelta(days=6)  # first day of the current window
    await _make_payment(db, company_id, invoice.id, Decimal("300"), boundary_date)
    just_before = TODAY - timedelta(days=7)  # last day of the prior window
    await _make_payment(db, company_id, invoice.id, Decimal("150"), just_before)

    trend = await build_cash_trend(db, company_id, TODAY)
    assert trend.collections_current == Decimal("300.00")
    assert trend.collections_prior == Decimal("150.00")


@pytest.mark.asyncio
async def test_cash_trend_never_blends_sales_into_cash(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer = await _make_dealer(db, company_id)
    invoice = await _make_invoice(
        db, company_id, dealer_id=dealer.id, total=Decimal("5000"), invoice_date=TODAY
    )
    await _make_payment(db, company_id, invoice.id, Decimal("2000"), TODAY)

    trend = await build_cash_trend(db, company_id, TODAY)
    assert trend.collections_current == Decimal("2000.00")
    assert trend.sales_current == Decimal("5000.00")
    assert trend.net_cash_current == Decimal("2000.00")


@pytest.mark.asyncio
async def test_dealer_trend_evidence_floor_excludes_thin_data(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer = await _make_dealer(db, company_id, "One Order Dealer")
    await _make_invoice(
        db, company_id, dealer_id=dealer.id, total=Decimal("500"), invoice_date=TODAY
    )

    trends = await build_dealer_trends(db, company_id, TODAY)
    assert trends == []


@pytest.mark.asyncio
async def test_dealer_trend_counts_and_values(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer = await _make_dealer(db, company_id, "Active Dealer")
    # Current 30d window: 2 orders totaling 3000.
    await _make_invoice(
        db, company_id, dealer_id=dealer.id, total=Decimal("1000"), invoice_date=TODAY
    )
    await _make_invoice(
        db,
        company_id,
        dealer_id=dealer.id,
        total=Decimal("2000"),
        invoice_date=TODAY - timedelta(days=5),
    )
    # Prior 30d window: 1 order totaling 500.
    await _make_invoice(
        db,
        company_id,
        dealer_id=dealer.id,
        total=Decimal("500"),
        invoice_date=TODAY - timedelta(days=35),
    )

    trends = await build_dealer_trends(db, company_id, TODAY)
    trend = next(t for t in trends if t.dealer_id == dealer.id)
    assert trend.orders_current == 2
    assert trend.orders_prior == 1
    assert trend.value_current == Decimal("3000.00")
    assert trend.value_prior == Decimal("500.00")
    assert trend.value_delta == Decimal("2500.00")


@pytest.mark.asyncio
async def test_dealer_trend_excludes_cancelled_invoices(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer = await _make_dealer(db, company_id, "Cancelled Order Dealer")
    await _make_invoice(
        db, company_id, dealer_id=dealer.id, total=Decimal("1000"), invoice_date=TODAY
    )
    await _make_invoice(
        db,
        company_id,
        dealer_id=dealer.id,
        total=Decimal("9999"),
        invoice_date=TODAY,
        status=InvoiceStatus.Cancelled,
    )

    trends = await build_dealer_trends(db, company_id, TODAY)
    trend = next((t for t in trends if t.dealer_id == dealer.id), None)
    # Only 1 non-cancelled invoice exists -> below the 2-order evidence floor.
    assert trend is None


@pytest.mark.asyncio
async def test_outstanding_as_of_ignores_future_payments(db: AsyncSession) -> None:
    """A payment recorded today against an invoice from 45 days ago must not
    reduce the 30-days-ago outstanding figure — proves the point-in-time
    cutoff is real, not today's snapshot relabeled.
    """
    company_id = await _make_company(db)
    dealer = await _make_dealer(db, company_id, "Backdated Dealer")
    invoice = await _make_invoice(
        db,
        company_id,
        dealer_id=dealer.id,
        total=Decimal("4000"),
        invoice_date=TODAY - timedelta(days=45),
    )
    await _make_payment(db, company_id, invoice.id, Decimal("4000"), TODAY)

    as_of_30d_ago = TODAY - timedelta(days=30)
    outstanding = await calculate_outstanding_for_company_as_of(
        db, company_id=company_id, direction="receivable", as_of_date=as_of_30d_ago
    )
    # As of 30 days ago the invoice existed (45d old) but the payment (made
    # today) hadn't happened yet -> full 4000 was still outstanding then.
    assert outstanding[dealer.id] == Decimal("4000.00")


@pytest.mark.asyncio
async def test_dealer_trend_outstanding_delta(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer = await _make_dealer(db, company_id, "Growing Debt Dealer")
    # Two orders so the evidence floor is cleared.
    await _make_invoice(
        db,
        company_id,
        dealer_id=dealer.id,
        total=Decimal("6000"),
        invoice_date=TODAY - timedelta(days=45),
    )
    await _make_invoice(
        db, company_id, dealer_id=dealer.id, total=Decimal("1000"), invoice_date=TODAY
    )
    # Only partially paid, and only very recently -> outstanding was higher
    # 30 days ago than it is "now" is false here (nothing was paid back
    # then either) — assert both current and prior reflect the unpaid amount.
    trends = await build_dealer_trends(db, company_id, TODAY)
    trend = next(t for t in trends if t.dealer_id == dealer.id)
    assert trend.outstanding_current == Decimal("7000.00")
    assert trend.outstanding_prior == Decimal("6000.00")
    assert trend.outstanding_delta == Decimal("1000.00")


@pytest.mark.asyncio
async def test_product_sales_trend_evidence_floor_and_values(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer = await _make_dealer(db, company_id)
    thin_product = await _make_product(db, company_id, "Thin Product")
    active_product = await _make_product(db, company_id, "Active Product")

    # Below the 5-unit combined floor -> excluded.
    await _make_invoice(
        db,
        company_id,
        dealer_id=dealer.id,
        total=Decimal("20"),
        invoice_date=TODAY,
        product_id=thin_product.id,
        quantity=Decimal("2"),
    )
    # Clears the floor: 6 current + 4 prior = 10 units.
    await _make_invoice(
        db,
        company_id,
        dealer_id=dealer.id,
        total=Decimal("600"),
        invoice_date=TODAY,
        product_id=active_product.id,
        quantity=Decimal("6"),
    )
    await _make_invoice(
        db,
        company_id,
        dealer_id=dealer.id,
        total=Decimal("400"),
        invoice_date=TODAY - timedelta(days=35),
        product_id=active_product.id,
        quantity=Decimal("4"),
    )

    trends = await build_product_sales_trends(db, company_id, TODAY)
    names = {t.product_name for t in trends}
    assert "Thin Product" not in names
    active_trend = next(t for t in trends if t.product_name == "Active Product")
    assert active_trend.units_current == Decimal("6")
    assert active_trend.units_prior == Decimal("4")
    assert active_trend.units_delta == Decimal("2")
    assert active_trend.revenue_current == Decimal("600.00")
    assert active_trend.revenue_prior == Decimal("400.00")


@pytest.mark.asyncio
async def test_product_sales_trend_excludes_cancelled(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer = await _make_dealer(db, company_id)
    product = await _make_product(db, company_id, "Voided Product")
    await _make_invoice(
        db,
        company_id,
        dealer_id=dealer.id,
        total=Decimal("999"),
        invoice_date=TODAY,
        status=InvoiceStatus.Cancelled,
        product_id=product.id,
        quantity=Decimal("50"),
    )

    trends = await build_product_sales_trends(db, company_id, TODAY)
    assert trends == []
