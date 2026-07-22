"""Trend analytics — week-over-week cash, dealer, and product movement.

Pure query + dataclass module, same layering as app/services/stock_forecast.py
(no LLM, no caching, nothing persisted). Deliberately computed directly from
Invoice/Payment/InvoiceItem rather than DailyBusinessSnapshot: that table only
exists since migration c2d94b6e15f7 (2026-07-12), too shallow a history for a
reliable week-over-week comparison, whereas Invoice/Payment carry a company's
full history (including backdated CSV-imported rows).

Cash figures (collections/payments/net) and accrual figures (sales) are kept
in separate fields on CashTrend, never blended into one number — this
project's standing "no blended financial metrics" rule.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceDirection
from app.models.invoice_item import InvoiceItem
from app.models.payment import Payment
from app.models.product import Product
from app.services.party_outstanding import (
    calculate_outstanding_for_company,
    calculate_outstanding_for_company_as_of,
)
from app.services.reports.statuses import EXCLUDED_STATUSES

_CASH_WINDOW_DAYS = 7
# Mirrors stock_forecast.py's _VELOCITY_WINDOW_DAYS=30 convention — not
# imported from there directly, that constant is private to stock-out
# forecasting and the two are free to diverge independently later.
_ACTIVITY_WINDOW_DAYS = 30
# Evidence floor so a dealer/product isn't flagged as "trending" off one
# order becoming two — mirrors stock_forecast.py's _MIN_SALE_DAYS/
# _MIN_UNITS_SOLD floor pattern.
_MIN_DEALER_ORDERS_TO_LIST = 2
_MIN_PRODUCT_UNITS_TO_LIST = Decimal("5")


@dataclass(frozen=True)
class WindowPair:
    current_start: date
    current_end: date
    prior_start: date
    prior_end: date


def _window_pair(today: date, window_days: int) -> WindowPair:
    current_start = today - timedelta(days=window_days - 1)
    prior_end = current_start - timedelta(days=1)
    prior_start = prior_end - timedelta(days=window_days - 1)
    return WindowPair(current_start, today, prior_start, prior_end)


@dataclass(frozen=True)
class CashTrend:
    window: WindowPair
    collections_current: Decimal
    collections_prior: Decimal
    payments_current: Decimal
    payments_prior: Decimal
    net_cash_current: Decimal
    net_cash_prior: Decimal
    # Accrual (invoiced, not collected) — reported alongside the cash figures
    # above but never summed with them.
    sales_current: Decimal
    sales_prior: Decimal


@dataclass(frozen=True)
class DealerTrend:
    dealer_id: uuid.UUID
    dealer_name: str
    orders_current: int
    orders_prior: int
    value_current: Decimal
    value_prior: Decimal
    outstanding_current: Decimal
    outstanding_prior: Decimal

    @property
    def value_delta(self) -> Decimal:
        return self.value_current - self.value_prior

    @property
    def outstanding_delta(self) -> Decimal:
        return self.outstanding_current - self.outstanding_prior


@dataclass(frozen=True)
class ProductSalesTrend:
    product_id: uuid.UUID
    product_name: str
    units_current: Decimal
    units_prior: Decimal
    revenue_current: Decimal
    revenue_prior: Decimal

    @property
    def units_delta(self) -> Decimal:
        return self.units_current - self.units_prior


@dataclass(frozen=True)
class TrendReport:
    generated_at_date: date
    cash_window: WindowPair
    activity_window: WindowPair
    cash: CashTrend
    dealers: list[DealerTrend]
    products: list[ProductSalesTrend]


async def _cash_totals(
    db: AsyncSession, company_id: uuid.UUID, start: date, end: date
) -> tuple[Decimal, Decimal]:
    rows = await db.execute(
        select(Invoice.direction, func.coalesce(func.sum(Payment.amount), 0))
        .join(Invoice, Payment.invoice_id == Invoice.id)
        .where(
            Invoice.company_id == company_id,
            Payment.payment_date >= start,
            Payment.payment_date <= end,
        )
        .group_by(Invoice.direction)
    )
    totals = dict(rows.all())
    collections = Decimal(totals.get(InvoiceDirection.receivable, 0))
    payments = Decimal(totals.get(InvoiceDirection.payable, 0))
    return collections, payments


async def _sales_total(db: AsyncSession, company_id: uuid.UUID, start: date, end: date) -> Decimal:
    total = await db.scalar(
        select(func.coalesce(func.sum(Invoice.total_amount), 0)).where(
            Invoice.company_id == company_id,
            Invoice.direction == InvoiceDirection.receivable,
            Invoice.invoice_date >= start,
            Invoice.invoice_date <= end,
            Invoice.status.notin_(EXCLUDED_STATUSES),
        )
    )
    return Decimal(total)


async def build_cash_trend(db: AsyncSession, company_id: uuid.UUID, today: date) -> CashTrend:
    window = _window_pair(today, _CASH_WINDOW_DAYS)
    collections_current, payments_current = await _cash_totals(
        db, company_id, window.current_start, window.current_end
    )
    collections_prior, payments_prior = await _cash_totals(
        db, company_id, window.prior_start, window.prior_end
    )
    sales_current = await _sales_total(db, company_id, window.current_start, window.current_end)
    sales_prior = await _sales_total(db, company_id, window.prior_start, window.prior_end)
    return CashTrend(
        window=window,
        collections_current=collections_current,
        collections_prior=collections_prior,
        payments_current=payments_current,
        payments_prior=payments_prior,
        net_cash_current=collections_current - payments_current,
        net_cash_prior=collections_prior - payments_prior,
        sales_current=sales_current,
        sales_prior=sales_prior,
    )


async def _dealer_order_totals(
    db: AsyncSession, company_id: uuid.UUID, start: date, end: date
) -> dict[uuid.UUID, tuple[str, int, Decimal]]:
    stmt = (
        select(
            Invoice.dealer_id,
            Dealer.name,
            func.count(Invoice.id),
            func.coalesce(func.sum(Invoice.total_amount), 0),
        )
        .join(Dealer, Invoice.dealer_id == Dealer.id)
        .where(
            Invoice.company_id == company_id,
            Invoice.direction == InvoiceDirection.receivable,
            Invoice.invoice_date >= start,
            Invoice.invoice_date <= end,
            Invoice.status.notin_(EXCLUDED_STATUSES),
        )
        .group_by(Invoice.dealer_id, Dealer.name)
    )
    rows = (await db.execute(stmt)).all()
    return {dealer_id: (name, count, Decimal(total)) for dealer_id, name, count, total in rows}


async def build_dealer_trends(
    db: AsyncSession, company_id: uuid.UUID, today: date
) -> list[DealerTrend]:
    window = _window_pair(today, _ACTIVITY_WINDOW_DAYS)
    current = await _dealer_order_totals(db, company_id, window.current_start, window.current_end)
    prior = await _dealer_order_totals(db, company_id, window.prior_start, window.prior_end)

    outstanding_now = await calculate_outstanding_for_company(
        db, company_id=company_id, direction="receivable"
    )
    outstanding_30d_ago = await calculate_outstanding_for_company_as_of(
        db, company_id=company_id, direction="receivable", as_of_date=window.prior_end
    )

    trends: list[DealerTrend] = []
    for dealer_id in set(current) | set(prior):
        name_current, count_current, value_current = current.get(
            dealer_id, (None, 0, Decimal("0"))
        )
        name_prior, count_prior, value_prior = prior.get(dealer_id, (None, 0, Decimal("0")))
        if count_current + count_prior < _MIN_DEALER_ORDERS_TO_LIST:
            continue
        trends.append(
            DealerTrend(
                dealer_id=dealer_id,
                dealer_name=name_current or name_prior,
                orders_current=count_current,
                orders_prior=count_prior,
                value_current=value_current,
                value_prior=value_prior,
                outstanding_current=outstanding_now.get(dealer_id, Decimal("0")),
                outstanding_prior=outstanding_30d_ago.get(dealer_id, Decimal("0")),
            )
        )
    return trends


async def _product_sales_totals(
    db: AsyncSession, company_id: uuid.UUID, start: date, end: date
) -> dict[uuid.UUID, tuple[str, Decimal, Decimal]]:
    stmt = (
        select(
            InvoiceItem.product_id,
            Product.name,
            func.coalesce(func.sum(InvoiceItem.quantity), 0),
            func.coalesce(func.sum(InvoiceItem.line_total), 0),
        )
        .join(Invoice, InvoiceItem.invoice_id == Invoice.id)
        .join(Product, InvoiceItem.product_id == Product.id)
        .where(
            Invoice.company_id == company_id,
            Invoice.direction == InvoiceDirection.receivable,
            Invoice.invoice_date >= start,
            Invoice.invoice_date <= end,
            Invoice.status.notin_(EXCLUDED_STATUSES),
            InvoiceItem.product_id.is_not(None),
        )
        .group_by(InvoiceItem.product_id, Product.name)
    )
    rows = (await db.execute(stmt)).all()
    return {
        product_id: (name, Decimal(units), Decimal(revenue))
        for product_id, name, units, revenue in rows
    }


async def build_product_sales_trends(
    db: AsyncSession, company_id: uuid.UUID, today: date
) -> list[ProductSalesTrend]:
    window = _window_pair(today, _ACTIVITY_WINDOW_DAYS)
    current = await _product_sales_totals(db, company_id, window.current_start, window.current_end)
    prior = await _product_sales_totals(db, company_id, window.prior_start, window.prior_end)

    trends: list[ProductSalesTrend] = []
    for product_id in set(current) | set(prior):
        name_current, units_current, revenue_current = current.get(
            product_id, (None, Decimal("0"), Decimal("0"))
        )
        name_prior, units_prior, revenue_prior = prior.get(
            product_id, (None, Decimal("0"), Decimal("0"))
        )
        if units_current + units_prior < _MIN_PRODUCT_UNITS_TO_LIST:
            continue
        trends.append(
            ProductSalesTrend(
                product_id=product_id,
                product_name=name_current or name_prior,
                units_current=units_current,
                units_prior=units_prior,
                revenue_current=revenue_current,
                revenue_prior=revenue_prior,
            )
        )
    return trends


async def build_trend_report(db: AsyncSession, company_id: uuid.UUID, today: date) -> TrendReport:
    cash = await build_cash_trend(db, company_id, today)
    dealers = await build_dealer_trends(db, company_id, today)
    products = await build_product_sales_trends(db, company_id, today)
    return TrendReport(
        generated_at_date=today,
        cash_window=cash.window,
        activity_window=_window_pair(today, _ACTIVITY_WINDOW_DAYS),
        cash=cash,
        dealers=dealers,
        products=products,
    )
