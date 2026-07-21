"""Stock-out forecasting — sales velocity vs current stock, per the
"Proactive early-warning alerts" item.

Deliberately separate from Snapshot/build_snapshot: this is a heavier
per-product query that only the stock-out NotificationEngine rule and the
briefing's "Watch this week" section need, and Snapshot is rebuilt on every
call by callers (agent read tools, evening brief, /dashboard) that never
need it — folding it in would slow down all of them for no benefit.

Pure query + pure dataclass. Whether a given days_of_cover is alert-worthy
is a decision for the caller (notifications.py / briefing.py), not this
module — it only reports what it can support from real sales history.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invoice import Invoice, InvoiceDirection
from app.models.invoice_item import InvoiceItem
from app.models.product import Product

_VELOCITY_WINDOW_DAYS = 30
# Minimum evidence required before a product gets a forecast at all — with a
# pilot company only weeks into real usage, a product with one or two sales
# would produce a wildly noisy "days of cover" estimate. Below either floor,
# stay silent rather than alert on a guess. Confirmed with the user as the
# concrete defaults to ship with (tunable later once more real data exists).
_MIN_SALE_DAYS = 3
_MIN_UNITS_SOLD = Decimal("10")


@dataclass
class StockOutForecast:
    product_id: uuid.UUID
    product_name: str
    stock_quantity: Decimal
    units_per_day: Decimal
    days_of_cover: int


async def _sales_velocity(
    db: AsyncSession, company_id: uuid.UUID, today: date
) -> dict[uuid.UUID, tuple[Decimal, int]]:
    """product_id -> (total units sold, distinct sale-days) over the trailing
    window. Receivable invoices only — that's actual sales; CSV-imported
    payables don't represent units leaving stock.
    """
    window_start = today - timedelta(days=_VELOCITY_WINDOW_DAYS)
    stmt = (
        select(
            InvoiceItem.product_id,
            func.sum(InvoiceItem.quantity),
            func.count(func.distinct(Invoice.invoice_date)),
        )
        .join(Invoice, InvoiceItem.invoice_id == Invoice.id)
        .where(
            Invoice.company_id == company_id,
            Invoice.direction == InvoiceDirection.receivable,
            Invoice.invoice_date >= window_start,
            Invoice.invoice_date <= today,
            InvoiceItem.product_id.is_not(None),
        )
        .group_by(InvoiceItem.product_id)
    )
    rows = (await db.execute(stmt)).all()
    return {product_id: (Decimal(total), sale_days) for product_id, total, sale_days in rows}


async def build_stock_out_forecasts(
    db: AsyncSession, company_id: uuid.UUID, today: date
) -> list[StockOutForecast]:
    velocity = await _sales_velocity(db, company_id, today)
    if not velocity:
        return []

    rows = (
        await db.execute(
            select(Product.id, Product.name, Product.stock_quantity).where(
                Product.company_id == company_id, Product.id.in_(velocity.keys())
            )
        )
    ).all()

    forecasts = []
    for product_id, name, stock_quantity in rows:
        units_sold, sale_days = velocity[product_id]
        if sale_days < _MIN_SALE_DAYS or units_sold < _MIN_UNITS_SOLD:
            continue
        units_per_day = units_sold / _VELOCITY_WINDOW_DAYS
        if units_per_day <= 0:
            continue
        forecasts.append(
            StockOutForecast(
                product_id=product_id,
                product_name=name,
                stock_quantity=stock_quantity,
                units_per_day=units_per_day,
                days_of_cover=int(stock_quantity / units_per_day),
            )
        )
    return forecasts
