"""Daily Business Summary — compute + persist.

Deliberately keeps every metric separate rather than blending accrual
(margin) and cash-basis (collections/payments) figures into one derived
"profit/loss" number: mixing the two produces misleading results (selling on
credit today looks like "profit" before any cash moves; collecting on an old
invoice looks like "profit" from a day with no sales at all). Each field here
measures exactly one thing.

compute_daily_snapshot is a pure read — used both for a live "today" view
(dashboard) and as the computation finalize_daily_snapshot persists. A row is
only ever written by finalize_daily_snapshot, called by the evening scheduler
job (app/services/evening_brief.py) or a manual admin trigger — never on a
plain dashboard page view.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.daily_business_snapshot import DailyBusinessSnapshot
from app.models.invoice import Invoice, InvoiceDirection, InvoiceSource
from app.models.invoice_item import InvoiceItem
from app.models.payment import Payment
from app.models.product import Product
from app.services.party_outstanding import calculate_outstanding_for_company
from app.services.snapshot import business_now

_CENTS = Decimal("0.01")


@dataclass(frozen=True)
class DailySnapshotResult:
    business_date: date
    sales_amount: Decimal
    sales_margin: Decimal
    items_missing_cost_data: int
    revenue_excluded_no_cost_data: Decimal
    collections_amount: Decimal
    supplier_payments_amount: Decimal
    net_cash_movement: Decimal
    outstanding_receivables: Decimal
    invoices_created: int
    payments_recorded: int
    orders_created: int


async def _sales_and_margin(
    db: AsyncSession, company_id, business_date: date
) -> tuple[Decimal, Decimal, int, Decimal]:
    rows = (
        await db.execute(
            select(
                InvoiceItem.line_total,
                InvoiceItem.quantity,
                InvoiceItem.unit_price,
                Product.purchase_price,
            )
            .join(Invoice, InvoiceItem.invoice_id == Invoice.id)
            .outerjoin(Product, InvoiceItem.product_id == Product.id)
            .where(
                Invoice.company_id == company_id,
                Invoice.direction == InvoiceDirection.receivable,
                Invoice.invoice_date == business_date,
            )
        )
    ).all()

    sales_amount = Decimal("0.00")
    sales_margin = Decimal("0.00")
    items_missing_cost_data = 0
    revenue_excluded_no_cost_data = Decimal("0.00")

    for line_total, quantity, unit_price, purchase_price in rows:
        sales_amount += line_total
        if purchase_price is None:
            items_missing_cost_data += 1
            revenue_excluded_no_cost_data += line_total
        else:
            sales_margin += ((unit_price - purchase_price) * quantity).quantize(_CENTS)

    return sales_amount, sales_margin, items_missing_cost_data, revenue_excluded_no_cost_data


async def _cash_movement(
    db: AsyncSession, company_id, business_date: date
) -> tuple[Decimal, Decimal]:
    rows = await db.execute(
        select(Invoice.direction, func.coalesce(func.sum(Payment.amount), 0))
        .join(Invoice, Payment.invoice_id == Invoice.id)
        .where(Payment.company_id == company_id, Payment.payment_date == business_date)
        .group_by(Invoice.direction)
    )
    by_direction = dict(rows.all())
    collections = Decimal(by_direction.get(InvoiceDirection.receivable, 0))
    payments_out = Decimal(by_direction.get(InvoiceDirection.payable, 0))
    return collections, payments_out


async def compute_daily_snapshot(
    db: AsyncSession, company: Company, business_date: date
) -> DailySnapshotResult:
    company_id = company.id
    sales_amount, sales_margin, items_missing_cost_data, revenue_excluded_no_cost_data = (
        await _sales_and_margin(db, company_id, business_date)
    )
    collections_amount, supplier_payments_amount = await _cash_movement(
        db, company_id, business_date
    )

    outstanding_by_dealer = await calculate_outstanding_for_company(
        db, company_id=company_id, direction="receivable"
    )
    outstanding_receivables = sum(outstanding_by_dealer.values(), Decimal("0.00"))

    invoices_created = await db.scalar(
        select(func.count())
        .select_from(Invoice)
        .where(Invoice.company_id == company_id, Invoice.invoice_date == business_date)
    )
    payments_recorded = await db.scalar(
        select(func.count())
        .select_from(Payment)
        .where(Payment.company_id == company_id, Payment.payment_date == business_date)
    )
    orders_created = await db.scalar(
        select(func.count())
        .select_from(Invoice)
        .where(
            Invoice.company_id == company_id,
            Invoice.direction == InvoiceDirection.receivable,
            Invoice.source == InvoiceSource.whatsapp,
            Invoice.invoice_date == business_date,
        )
    )

    return DailySnapshotResult(
        business_date=business_date,
        sales_amount=sales_amount,
        sales_margin=sales_margin,
        items_missing_cost_data=items_missing_cost_data,
        revenue_excluded_no_cost_data=revenue_excluded_no_cost_data,
        collections_amount=collections_amount,
        supplier_payments_amount=supplier_payments_amount,
        net_cash_movement=collections_amount - supplier_payments_amount,
        outstanding_receivables=outstanding_receivables,
        invoices_created=invoices_created or 0,
        payments_recorded=payments_recorded or 0,
        orders_created=orders_created or 0,
    )


async def finalize_daily_snapshot(
    db: AsyncSession, company: Company, business_date: date
) -> DailyBusinessSnapshot:
    """Computes fresh, then upserts — a day can be re-finalized (e.g. a retry
    after a failed evening-brief send) without creating a duplicate row.
    Never commits (caller commits), same contract as every other write
    service in this codebase.
    """
    result = await compute_daily_snapshot(db, company, business_date)
    finalized_at = datetime.now(UTC)

    values = {
        "company_id": company.id,
        "business_date": result.business_date,
        "sales_amount": result.sales_amount,
        "sales_margin": result.sales_margin,
        "items_missing_cost_data": result.items_missing_cost_data,
        "revenue_excluded_no_cost_data": result.revenue_excluded_no_cost_data,
        "collections_amount": result.collections_amount,
        "supplier_payments_amount": result.supplier_payments_amount,
        "net_cash_movement": result.net_cash_movement,
        "outstanding_receivables": result.outstanding_receivables,
        "invoices_created": result.invoices_created,
        "payments_recorded": result.payments_recorded,
        "orders_created": result.orders_created,
        "finalized_at": finalized_at,
    }
    stmt = pg_insert(DailyBusinessSnapshot).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[DailyBusinessSnapshot.company_id, DailyBusinessSnapshot.business_date],
        set_=values,
    ).returning(DailyBusinessSnapshot)
    row = (await db.execute(stmt)).scalar_one()
    return row


async def month_to_date_totals(db: AsyncSession, company: Company, year: int, month: int) -> dict:
    """SUM over this month's finalized rows, plus today's live snapshot
    folded in when today falls in the requested month and isn't finalized
    yet — so the running total is accurate in real time without writing a
    row on every dashboard view.
    """
    month_start = date(year, month, 1)
    month_end = date(year, month, monthrange(year, month)[1])

    rows = await db.execute(
        select(
            func.coalesce(func.sum(DailyBusinessSnapshot.sales_amount), 0),
            func.coalesce(func.sum(DailyBusinessSnapshot.sales_margin), 0),
            func.coalesce(func.sum(DailyBusinessSnapshot.net_cash_movement), 0),
            func.coalesce(func.sum(DailyBusinessSnapshot.invoices_created), 0),
            func.coalesce(func.sum(DailyBusinessSnapshot.payments_recorded), 0),
            func.coalesce(func.sum(DailyBusinessSnapshot.orders_created), 0),
        ).where(
            DailyBusinessSnapshot.company_id == company.id,
            DailyBusinessSnapshot.business_date >= month_start,
            DailyBusinessSnapshot.business_date <= month_end,
        )
    )
    sales, margin, net_cash, invoices, payments, orders = rows.one()
    totals = {
        "sales_amount": Decimal(sales),
        "sales_margin": Decimal(margin),
        "net_cash_movement": Decimal(net_cash),
        "invoices_created": invoices,
        "payments_recorded": payments,
        "orders_created": orders,
    }

    today = business_now(company.timezone).date()
    if month_start <= today <= month_end:
        already_finalized = await db.scalar(
            select(DailyBusinessSnapshot.id).where(
                DailyBusinessSnapshot.company_id == company.id,
                DailyBusinessSnapshot.business_date == today,
            )
        )
        if already_finalized is None:
            live = await compute_daily_snapshot(db, company, today)
            totals["sales_amount"] += live.sales_amount
            totals["sales_margin"] += live.sales_margin
            totals["net_cash_movement"] += live.net_cash_movement
            totals["invoices_created"] += live.invoices_created
            totals["payments_recorded"] += live.payments_recorded
            totals["orders_created"] += live.orders_created

    return totals
