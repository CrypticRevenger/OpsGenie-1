"""Daily Business Summary compute/finalize/month-to-date tests.

Same convention as tests/test_writes.py: live DB, each test gets its own
Company via a unique whatsapp_number.

    uv run alembic upgrade head
    uv run pytest tests/test_daily_snapshot.py -v
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from app.models.company import Company
from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceDirection, InvoiceSource, InvoiceStatus
from app.models.invoice_item import InvoiceItem
from app.models.payment import Payment, PaymentSource
from app.models.product import Product
from app.services.daily_snapshot import (
    compute_daily_snapshot,
    finalize_daily_snapshot,
    month_to_date_totals,
)
from sqlalchemy.ext.asyncio import AsyncSession


def _unique_phone() -> str:
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


async def _make_company(db: AsyncSession) -> Company:
    company = Company(
        business_name="Snapshot Test Co", owner_name="Owner", whatsapp_number=_unique_phone()
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company


async def _make_dealer(db: AsyncSession, company: Company, name: str = "Ram Traders") -> Dealer:
    dealer = Dealer(company_id=company.id, name=name)
    db.add(dealer)
    await db.commit()
    await db.refresh(dealer)
    return dealer


async def _make_product(
    db: AsyncSession, company: Company, name: str, *, selling_price: Decimal, purchase_price=None
) -> Product:
    product = Product(
        company_id=company.id, name=name, selling_price=selling_price, purchase_price=purchase_price
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


async def _make_invoice_with_items(
    db: AsyncSession,
    company: Company,
    dealer: Dealer,
    items: list[tuple[Product, Decimal, Decimal]],  # (product, quantity, unit_price)
    *,
    invoice_date: date,
    source: InvoiceSource = InvoiceSource.whatsapp,
) -> Invoice:
    subtotal = sum((qty * price for _, qty, price in items), Decimal("0.00"))
    invoice = Invoice(
        company_id=company.id,
        invoice_number=f"WA-{uuid.uuid4().hex[:10]}",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer.id,
        invoice_date=invoice_date,
        due_date=invoice_date,
        subtotal=subtotal,
        gst_amount=Decimal("0.00"),
        total_amount=subtotal,
        status=InvoiceStatus.Pending,
        source=source,
    )
    db.add(invoice)
    await db.flush()
    for product, qty, price in items:
        db.add(
            InvoiceItem(
                invoice_id=invoice.id,
                product_id=product.id,
                description=product.name,
                quantity=qty,
                unit_price=price,
                line_total=(qty * price).quantize(Decimal("0.01")),
            )
        )
    await db.commit()
    await db.refresh(invoice)
    return invoice


@pytest.mark.asyncio
async def test_sales_margin_computed_when_cost_price_on_file(db: AsyncSession) -> None:
    company = await _make_company(db)
    dealer = await _make_dealer(db, company)
    rice = await _make_product(
        db, company, "Rice", selling_price=Decimal("100.00"), purchase_price=Decimal("70.00")
    )
    today = date.today()
    await _make_invoice_with_items(
        db, company, dealer, [(rice, Decimal("10"), Decimal("100.00"))], invoice_date=today
    )

    result = await compute_daily_snapshot(db, company, today)
    assert result.sales_amount == Decimal("1000.00")
    assert result.sales_margin == Decimal("300.00")  # 10 * (100 - 70)
    assert result.items_missing_cost_data == 0
    assert result.revenue_excluded_no_cost_data == Decimal("0.00")


@pytest.mark.asyncio
async def test_items_without_cost_price_excluded_from_margin(db: AsyncSession) -> None:
    company = await _make_company(db)
    dealer = await _make_dealer(db, company)
    oil = await _make_product(
        db, company, "Oil", selling_price=Decimal("50.00"), purchase_price=None
    )
    today = date.today()
    await _make_invoice_with_items(
        db, company, dealer, [(oil, Decimal("10"), Decimal("50.00"))], invoice_date=today
    )

    result = await compute_daily_snapshot(db, company, today)
    assert result.sales_amount == Decimal("500.00")
    assert result.sales_margin == Decimal("0.00")
    assert result.items_missing_cost_data == 1
    assert result.revenue_excluded_no_cost_data == Decimal("500.00")


async def _make_csv_invoice_without_items(
    db: AsyncSession,
    company: Company,
    dealer: Dealer,
    *,
    subtotal: Decimal,
    invoice_date: date,
) -> Invoice:
    """A CSV-imported receivable invoice — no InvoiceItem rows, exactly like the
    real import pipeline produces (only the WhatsApp order flow writes items).
    """
    invoice = Invoice(
        company_id=company.id,
        invoice_number=f"CSV-{uuid.uuid4().hex[:10]}",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer.id,
        invoice_date=invoice_date,
        due_date=invoice_date,
        subtotal=subtotal,
        gst_amount=Decimal("0.00"),
        total_amount=subtotal,
        status=InvoiceStatus.Pending,
        source=InvoiceSource.csv_import,
    )
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)
    return invoice


@pytest.mark.asyncio
async def test_csv_invoice_without_items_counts_as_sales(db: AsyncSession) -> None:
    # Regression: CSV-imported invoices carry no InvoiceItem rows, so an
    # item-level sales sum reported them as ₹0 even while invoices_created
    # counted them — two contradicting figures in the same evening brief.
    company = await _make_company(db)
    dealer = await _make_dealer(db, company)
    today = date.today()
    await _make_csv_invoice_without_items(
        db, company, dealer, subtotal=Decimal("20000.00"), invoice_date=today
    )

    result = await compute_daily_snapshot(db, company, today)
    assert result.sales_amount == Decimal("20000.00")  # counted, not dropped
    assert result.invoices_created == 1
    # No per-item cost basis → no margin, whole revenue reported as excluded.
    assert result.sales_margin == Decimal("0.00")
    assert result.items_missing_cost_data == 1
    assert result.revenue_excluded_no_cost_data == Decimal("20000.00")


@pytest.mark.asyncio
async def test_sales_never_counted_from_a_different_day(db: AsyncSession) -> None:
    company = await _make_company(db)
    dealer = await _make_dealer(db, company)
    rice = await _make_product(
        db, company, "Rice", selling_price=Decimal("100.00"), purchase_price=Decimal("70.00")
    )
    yesterday = date(2020, 1, 1)
    await _make_invoice_with_items(
        db, company, dealer, [(rice, Decimal("10"), Decimal("100.00"))], invoice_date=yesterday
    )

    result = await compute_daily_snapshot(db, company, date.today())
    assert result.sales_amount == Decimal("0.00")
    assert result.invoices_created == 0


@pytest.mark.asyncio
async def test_collections_and_supplier_payments_independent(db: AsyncSession) -> None:
    company = await _make_company(db)
    dealer = await _make_dealer(db, company)
    rice = await _make_product(db, company, "Rice", selling_price=Decimal("100.00"))
    today = date.today()
    invoice = await _make_invoice_with_items(
        db, company, dealer, [(rice, Decimal("10"), Decimal("100.00"))], invoice_date=today
    )
    db.add(
        Payment(
            company_id=company.id,
            invoice_id=invoice.id,
            amount=Decimal("400.00"),
            payment_date=today,
            source=PaymentSource.whatsapp,
        )
    )
    await db.commit()

    result = await compute_daily_snapshot(db, company, today)
    assert result.collections_amount == Decimal("400.00")
    assert result.supplier_payments_amount == Decimal("0.00")
    assert result.net_cash_movement == Decimal("400.00")
    assert result.payments_recorded == 1
    # No blended profit/loss field exists — every metric stays separate.
    assert not hasattr(result, "profit")
    assert not hasattr(result, "loss")


@pytest.mark.asyncio
async def test_orders_created_only_counts_whatsapp_receivable_invoices(db: AsyncSession) -> None:
    company = await _make_company(db)
    dealer = await _make_dealer(db, company)
    rice = await _make_product(db, company, "Rice", selling_price=Decimal("100.00"))
    today = date.today()
    await _make_invoice_with_items(
        db,
        company,
        dealer,
        [(rice, Decimal("10"), Decimal("100.00"))],
        invoice_date=today,
        source=InvoiceSource.csv_import,
    )
    await _make_invoice_with_items(
        db,
        company,
        dealer,
        [(rice, Decimal("5"), Decimal("100.00"))],
        invoice_date=today,
        source=InvoiceSource.whatsapp,
    )

    result = await compute_daily_snapshot(db, company, today)
    assert result.invoices_created == 2
    assert result.orders_created == 1


@pytest.mark.asyncio
async def test_finalize_upserts_not_duplicates(db: AsyncSession) -> None:
    company = await _make_company(db)
    today = date.today()

    first = await finalize_daily_snapshot(db, company, today)
    await db.commit()
    second = await finalize_daily_snapshot(db, company, today)
    await db.commit()

    assert first.id == second.id


@pytest.mark.asyncio
async def test_month_to_date_totals_includes_live_today_when_not_finalized(
    db: AsyncSession,
) -> None:
    company = await _make_company(db)
    dealer = await _make_dealer(db, company)
    rice = await _make_product(
        db, company, "Rice", selling_price=Decimal("100.00"), purchase_price=Decimal("70.00")
    )
    today = date.today()
    await _make_invoice_with_items(
        db, company, dealer, [(rice, Decimal("10"), Decimal("100.00"))], invoice_date=today
    )

    totals = await month_to_date_totals(db, company, today.year, today.month)
    assert totals["sales_amount"] == Decimal("1000.00")
    assert totals["sales_margin"] == Decimal("300.00")


@pytest.mark.asyncio
async def test_month_to_date_totals_no_double_counting_once_finalized(db: AsyncSession) -> None:
    company = await _make_company(db)
    dealer = await _make_dealer(db, company)
    rice = await _make_product(
        db, company, "Rice", selling_price=Decimal("100.00"), purchase_price=Decimal("70.00")
    )
    today = date.today()
    await _make_invoice_with_items(
        db, company, dealer, [(rice, Decimal("10"), Decimal("100.00"))], invoice_date=today
    )
    await finalize_daily_snapshot(db, company, today)
    await db.commit()

    totals = await month_to_date_totals(db, company, today.year, today.month)
    assert totals["sales_amount"] == Decimal("1000.00")  # not doubled
