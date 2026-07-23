"""Stock-out forecast tests — sales velocity vs current stock.

Requires postgres running with migrations applied:

    uv run alembic upgrade head
    uv run pytest tests/test_stock_forecast.py -v
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
from app.models.product import Product
from app.models.supplier import Supplier
from app.services.snapshot import DEFAULT_BUSINESS_TIMEZONE, business_now
from app.services.stock_forecast import build_stock_out_forecasts
from sqlalchemy.ext.asyncio import AsyncSession

TODAY = business_now(DEFAULT_BUSINESS_TIMEZONE).date()


def _unique_phone() -> str:
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


async def _make_company(db: AsyncSession) -> uuid.UUID:
    company = Company(
        business_name="Stock Forecast Test Co", owner_name="Owner", whatsapp_number=_unique_phone()
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company.id


async def _make_dealer(db: AsyncSession, company_id: uuid.UUID) -> uuid.UUID:
    dealer = Dealer(company_id=company_id, name="Velocity Dealer")
    db.add(dealer)
    await db.commit()
    await db.refresh(dealer)
    return dealer.id


async def _make_product(
    db: AsyncSession, company_id: uuid.UUID, name: str, stock_quantity: Decimal
) -> uuid.UUID:
    product = Product(company_id=company_id, name=name, stock_quantity=stock_quantity)
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product.id


async def _make_sale(
    db: AsyncSession,
    company_id: uuid.UUID,
    dealer_id: uuid.UUID,
    product_id: uuid.UUID,
    quantity: Decimal,
    invoice_date: date,
    *,
    status: InvoiceStatus = InvoiceStatus.Paid,
) -> None:
    invoice = Invoice(
        company_id=company_id,
        invoice_number=f"INV-{uuid.uuid4().hex[:10]}",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        invoice_date=invoice_date,
        due_date=invoice_date + timedelta(days=7),
        subtotal=Decimal("100.00"),
        gst_amount=Decimal("0.00"),
        total_amount=Decimal("100.00"),
        status=status,
        source=InvoiceSource.csv_import,
    )
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)
    db.add(
        InvoiceItem(
            invoice_id=invoice.id,
            product_id=product_id,
            description="line",
            quantity=quantity,
            unit_price=Decimal("10.00"),
            line_total=Decimal("100.00"),
        )
    )
    await db.commit()


@pytest.mark.asyncio
async def test_velocity_and_days_of_cover(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id)
    product_id = await _make_product(db, company_id, "Paracetamol", Decimal("120"))
    for i in range(4):
        await _make_sale(
            db, company_id, dealer_id, product_id, Decimal("30"), TODAY - timedelta(days=i)
        )

    forecasts = await build_stock_out_forecasts(db, company_id, TODAY)
    forecast = next(f for f in forecasts if f.product_name == "Paracetamol")
    # 4 sales x 30 units = 120 units over the 30-day window -> 4 units/day.
    assert forecast.units_per_day == Decimal("4")
    # 120 in stock / 4 per day = 30 days of cover.
    assert forecast.days_of_cover == 30


@pytest.mark.asyncio
async def test_min_sale_days_guard_suppresses_thin_data(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id)
    product_id = await _make_product(db, company_id, "Rare Item", Decimal("5"))
    # Well above the units floor but only 1 sale-day — below the 3-sale-day guard.
    await _make_sale(db, company_id, dealer_id, product_id, Decimal("50"), TODAY)

    forecasts = await build_stock_out_forecasts(db, company_id, TODAY)
    assert forecasts == []


@pytest.mark.asyncio
async def test_min_units_guard_suppresses_thin_data(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id)
    product_id = await _make_product(db, company_id, "Barely Sold", Decimal("5"))
    # 4 distinct sale-days (clears that guard) but only 1 unit each — below
    # the 10-unit floor.
    for i in range(4):
        await _make_sale(
            db, company_id, dealer_id, product_id, Decimal("1"), TODAY - timedelta(days=i)
        )

    forecasts = await build_stock_out_forecasts(db, company_id, TODAY)
    assert forecasts == []


@pytest.mark.asyncio
async def test_cancelled_invoices_excluded_from_velocity(db: AsyncSession) -> None:
    """A voided order's items still exist on InvoiceItem (void_order soft-
    cancels, never deletes) — they must not inflate sales velocity, or a
    cancelled order would trigger a false stock-out alert even though the
    stock it consumed was already restored."""
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id)
    product_id = await _make_product(db, company_id, "Voided Item", Decimal("120"))
    for i in range(4):
        await _make_sale(
            db,
            company_id,
            dealer_id,
            product_id,
            Decimal("30"),
            TODAY - timedelta(days=i),
            status=InvoiceStatus.Cancelled,
        )

    forecasts = await build_stock_out_forecasts(db, company_id, TODAY)
    assert forecasts == []


@pytest.mark.asyncio
async def test_payable_invoices_excluded_from_velocity(db: AsyncSession) -> None:
    """CSV-imported purchases aren't sales — only receivable invoices count."""
    company_id = await _make_company(db)
    product_id = await _make_product(db, company_id, "Purchased Only", Decimal("100"))
    supplier = Supplier(company_id=company_id, name="Some Supplier")
    db.add(supplier)
    await db.commit()
    await db.refresh(supplier)

    invoice = Invoice(
        company_id=company_id,
        invoice_number="INV-PAYABLE-ONLY",
        direction=InvoiceDirection.payable,
        supplier_id=supplier.id,
        invoice_date=TODAY,
        due_date=TODAY + timedelta(days=7),
        subtotal=Decimal("100.00"),
        gst_amount=Decimal("0.00"),
        total_amount=Decimal("100.00"),
        status=InvoiceStatus.Paid,
        source=InvoiceSource.csv_import,
    )
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)
    db.add(
        InvoiceItem(
            invoice_id=invoice.id,
            product_id=product_id,
            description="line",
            quantity=Decimal("50"),
            unit_price=Decimal("10.00"),
            line_total=Decimal("100.00"),
        )
    )
    await db.commit()

    forecasts = await build_stock_out_forecasts(db, company_id, TODAY)
    assert forecasts == []
