"""BusinessSnapshotService — per SPEC.md TDD.

"Single function build_snapshot(company_id) returning complete structured
state." A plain dataclass, deliberately not a Pydantic/FastAPI model — the
snapshot is consumed by RecommendationEngine (pure Python) today and will be
consumed by the Claude narration layer in a later phase; neither needs it to
be an API schema.

No caching or staleness-flag machinery here (that belongs to BusinessEngine,
which doesn't exist yet — nothing currently marks a snapshot "stale" to begin
with, so recomputing on every call is correct until that changes).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import DEFAULT_LOCALE, Locale, resolve_locale
from app.models.company import Company
from app.models.dealer import Dealer
from app.models.import_log import ImportLog
from app.models.invoice import Invoice, InvoiceDirection, InvoiceStatus
from app.models.payment import Payment
from app.models.supplier import Supplier
from app.services.party_completeness import count_parties_missing_fields
from app.services.party_outstanding import calculate_outstanding_for_company

_OPEN_STATUSES = (InvoiceStatus.Pending, InvoiceStatus.Partially_Paid, InvoiceStatus.Overdue)
_LATE_PAYMENT_WINDOW_DAYS = 180  # "last 6 months", per TDD
DEFAULT_BUSINESS_TIMEZONE = "Asia/Kolkata"


def business_now(tz_name: str | None) -> datetime:
    """Current instant in a company's business timezone. Business-day
    boundaries (today, overdue, the 7-day window) must be computed here, not
    in UTC — an IST distributor's calendar day rolls over 5.5 hours before
    UTC's, so a UTC "today" would misclassify due/overdue invoices for hours
    around midnight. Falls back to the India default if the stored zone name
    is missing or somehow invalid (create-time validation should prevent the
    latter, but reading must never raise).
    """
    try:
        zone = ZoneInfo(tz_name or DEFAULT_BUSINESS_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo(DEFAULT_BUSINESS_TIMEZONE)
    return datetime.now(zone)


@dataclass
class DealerCollection:
    dealer_id: uuid.UUID
    dealer_name: str
    amount: Decimal
    due_date: date


@dataclass
class SupplierPayment:
    supplier_id: uuid.UUID
    supplier_name: str
    amount: Decimal
    due_date: date
    urgent: bool  # due within 48 hours
    # Which specific bill this is — added so a "yes I paid this" reply to a
    # reminder (app/services/workflows/payment_reminder_confirm.py) can target
    # this exact invoice instead of FIFO-guessing across the supplier's other
    # open invoices. Defaulted so existing test fixtures that build a
    # SupplierPayment without it don't break (same reason as Snapshot's
    # business_name/locale defaults above).
    invoice_id: uuid.UUID | None = None
    invoice_number: str = ""


@dataclass
class CashDeficitForecast:
    days_until: int
    trigger_payment: SupplierPayment | None  # largest single payment due by the deficit day


@dataclass
class OverdueDealer:
    dealer_id: uuid.UUID
    dealer_name: str
    outstanding: Decimal
    days_overdue: int
    late_payment_count_6mo: int
    risk_level: str  # "High" | "Medium" | "Low" — thresholds match RecommendationEngine's
    credit_limit: Decimal | None  # RecommendationEngine's "call_dealer" threshold


@dataclass
class Snapshot:
    company_id: uuid.UUID
    generated_at: datetime
    cash_available_today: Decimal
    expected_collections_7d: list[DealerCollection]
    expected_collections_7d_total: Decimal
    expected_payments_7d: list[SupplierPayment]
    expected_payments_7d_total: Decimal
    net_cash_position: Decimal
    cash_deficit: bool
    overdue_dealers: list[OverdueDealer]
    data_freshness_hours: float | None
    data_completeness_score: float | None  # stubbed None — no daily-import tracking yet
    confidence_score: float
    # Added so RecommendationEngine's company-level actions (cash_deficit_warning,
    # stale_data_warning) can name the business instead of surfacing its raw
    # UUID in customer-facing text — build_recommendations() stays a pure
    # function of a Snapshot (no DB access), it just gets more of what's
    # already fetched here. Defaulted so existing test fixtures that build a
    # Snapshot without it don't break.
    business_name: str = "Your Company"
    # The company's resolved display locale (language × script). Threaded here
    # alongside business_name for the same reason: the pure report builders in
    # query_menu.py localize their own labels via i18n.t() without a DB
    # round-trip. Defaulted to English so existing Snapshot(...) test fixtures
    # stay valid and unchanged (English behavior).
    locale: Locale = DEFAULT_LOCALE
    # How many dealers/suppliers still have no phone/credit-days on file —
    # commonly non-zero right after an "import existing data" onboarding
    # where the distributor picked "later" instead of filling these in on the
    # spot (see app/services/onboarding_flow.py's dealer_missing_*/
    # supplier_missing_* states). Feeds RecommendationEngine's
    # incomplete_party_data action so "later" doesn't mean "forgotten".
    # Defaulted to 0 for the same reason as business_name/locale above.
    dealers_missing_fields_count: int = 0
    suppliers_missing_fields_count: int = 0
    # Proactive early-warning alert (see app/services/notifications.py::
    # check_cash_shortage_forecast) — the day-by-day cumulative walk
    # net_cash_position/cash_deficit don't do: WHEN the deficit first hits,
    # and the single biggest payment behind it. None when no deficit is
    # projected within the 7-day window. Defaulted for the same reason as
    # business_name/locale above.
    cash_deficit_forecast: CashDeficitForecast | None = None


def is_cash_sufficient(cash_available: Decimal, amount: Decimal) -> bool:
    """Shared by RecommendationEngine's critical_payment_warning and the
    numbered menu's Suppliers reply — both need the same answer to "can we
    cover this payment with what's on hand today," so it's defined once here
    rather than duplicated as two independently-maintained comparisons.
    """
    return cash_available >= amount


def _risk_level(days_overdue: int) -> str:
    if days_overdue > 15:
        return "High"
    if days_overdue >= 5:
        return "Medium"
    return "Low"


def _confidence_score(data_freshness_hours: float | None) -> float:
    """First-pass placeholder — the TDD's WhatsApp examples show numbers like
    94%/91% but never specify a formula. 100 while fresher than 24h, degrading
    linearly to a 40-point floor by 72h stale. No data at all -> 0.
    """
    if data_freshness_hours is None:
        return 0.0
    if data_freshness_hours <= 24:
        return 100.0
    if data_freshness_hours >= 72:
        return 40.0
    # Linear interpolation from 100 at 24h to 40 at 72h.
    return round(100.0 - (data_freshness_hours - 24) * (60.0 / 48.0), 1)


async def _cash_available_today(db: AsyncSession, company: Company) -> Decimal:
    receivable_paid = await db.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0))
        .join(Invoice, Payment.invoice_id == Invoice.id)
        .where(Invoice.company_id == company.id, Invoice.direction == InvoiceDirection.receivable)
    )
    payable_paid = await db.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0))
        .join(Invoice, Payment.invoice_id == Invoice.id)
        .where(Invoice.company_id == company.id, Invoice.direction == InvoiceDirection.payable)
    )
    return company.opening_balance + Decimal(receivable_paid) - Decimal(payable_paid)


async def _paid_by_invoice(
    db: AsyncSession, invoice_ids: list[uuid.UUID]
) -> dict[uuid.UUID, Decimal]:
    """Sum of payments recorded against each invoice, one grouped query."""
    if not invoice_ids:
        return {}
    rows = await db.execute(
        select(Payment.invoice_id, func.sum(Payment.amount))
        .where(Payment.invoice_id.in_(invoice_ids))
        .group_by(Payment.invoice_id)
    )
    return dict(rows.all())


async def _expected_collections_7d(
    db: AsyncSession, company_id: uuid.UUID, today: date
) -> list[DealerCollection]:
    stmt = (
        select(Invoice, Dealer.name)
        .join(Dealer, Invoice.dealer_id == Dealer.id)
        .where(
            Invoice.company_id == company_id,
            Invoice.direction == InvoiceDirection.receivable,
            Invoice.status.in_(_OPEN_STATUSES),
            Invoice.due_date >= today,
            Invoice.due_date <= today + timedelta(days=7),
        )
        .order_by(Invoice.due_date)
    )
    rows = (await db.execute(stmt)).all()
    # Expected collection is the *outstanding* balance, not the gross invoice
    # total — a partially-paid invoice only has its remaining balance left to
    # collect. Using total_amount here would overstate the 7-day inflow (and
    # therefore net_cash_position and the cash-deficit warning).
    paid_by_invoice = await _paid_by_invoice(db, [invoice.id for invoice, _ in rows])
    result = []
    for invoice, dealer_name in rows:
        outstanding = invoice.total_amount - paid_by_invoice.get(invoice.id, Decimal("0.00"))
        if outstanding <= 0:
            continue  # nothing left to collect on this invoice
        result.append(
            DealerCollection(
                dealer_id=invoice.dealer_id,
                dealer_name=dealer_name,
                amount=outstanding,
                due_date=invoice.due_date,
            )
        )
    return result


async def _expected_payments_7d(
    db: AsyncSession, company_id: uuid.UUID, today: date
) -> list[SupplierPayment]:
    stmt = (
        select(Invoice, Supplier.name)
        .join(Supplier, Invoice.supplier_id == Supplier.id)
        .where(
            Invoice.company_id == company_id,
            Invoice.direction == InvoiceDirection.payable,
            Invoice.status.in_(_OPEN_STATUSES),
            Invoice.due_date >= today,
            Invoice.due_date <= today + timedelta(days=7),
        )
        .order_by(Invoice.due_date)
    )
    rows = (await db.execute(stmt)).all()
    # Same as collections: the remaining balance owed, not the gross total, is
    # what still has to be paid out in the window.
    paid_by_invoice = await _paid_by_invoice(db, [invoice.id for invoice, _ in rows])
    result = []
    for invoice, supplier_name in rows:
        outstanding = invoice.total_amount - paid_by_invoice.get(invoice.id, Decimal("0.00"))
        if outstanding <= 0:
            continue  # nothing left to pay on this invoice
        result.append(
            SupplierPayment(
                supplier_id=invoice.supplier_id,
                supplier_name=supplier_name,
                amount=outstanding,
                due_date=invoice.due_date,
                urgent=(invoice.due_date - today) <= timedelta(days=2),
                invoice_id=invoice.id,
                invoice_number=invoice.invoice_number,
            )
        )
    return result


def forecast_cash_deficit(
    cash_available_today: Decimal,
    collections: list[DealerCollection],
    payments: list[SupplierPayment],
    today: date,
) -> CashDeficitForecast | None:
    """Cumulative day-by-day walk (not the flat 7-day totals) to find the
    first day the running cash position goes negative, plus the biggest
    single payment due by that day. net_cash_position/cash_deficit only
    answer "does a deficit exist by day 7" — not "when" or "caused by what",
    which is what makes the forward-looking alert actionable rather than
    just informative.
    """
    events = sorted(
        [(c.due_date, c.amount) for c in collections]
        + [(p.due_date, -p.amount) for p in payments],
        key=lambda event: event[0],
    )
    running = cash_available_today
    deficit_due_date: date | None = None
    for due_date, delta in events:
        running += delta
        if running < 0:
            deficit_due_date = due_date
            break
    if deficit_due_date is None:
        return None

    contributing = [p for p in payments if p.due_date <= deficit_due_date]
    trigger = max(contributing, key=lambda p: p.amount, default=None)
    return CashDeficitForecast(
        days_until=(deficit_due_date - today).days,
        trigger_payment=trigger,
    )


async def _overdue_dealers(
    db: AsyncSession, company_id: uuid.UUID, today: date
) -> list[OverdueDealer]:
    stmt = (
        select(Invoice.dealer_id, Dealer.name, Dealer.credit_limit, Invoice.due_date)
        .join(Dealer, Invoice.dealer_id == Dealer.id)
        .where(
            Invoice.company_id == company_id,
            Invoice.direction == InvoiceDirection.receivable,
            Invoice.status.in_(_OPEN_STATUSES),
            Invoice.due_date < today,
        )
    )
    rows = (await db.execute(stmt)).all()
    if not rows:
        return []

    oldest_due_date_by_dealer: dict[uuid.UUID, date] = {}
    name_by_dealer: dict[uuid.UUID, str] = {}
    credit_limit_by_dealer: dict[uuid.UUID, Decimal | None] = {}
    for dealer_id, dealer_name, credit_limit, due_date in rows:
        name_by_dealer[dealer_id] = dealer_name
        credit_limit_by_dealer[dealer_id] = credit_limit
        current_oldest = oldest_due_date_by_dealer.get(dealer_id)
        if current_oldest is None or due_date < current_oldest:
            oldest_due_date_by_dealer[dealer_id] = due_date

    outstanding_by_dealer = await calculate_outstanding_for_company(
        db, company_id=company_id, direction="receivable"
    )
    late_counts = await _late_payment_counts(db, company_id, today)

    result = []
    for dealer_id, oldest_due_date in oldest_due_date_by_dealer.items():
        days_overdue = (today - oldest_due_date).days
        result.append(
            OverdueDealer(
                dealer_id=dealer_id,
                dealer_name=name_by_dealer[dealer_id],
                outstanding=outstanding_by_dealer.get(dealer_id, Decimal("0.00")),
                days_overdue=days_overdue,
                late_payment_count_6mo=late_counts.get(dealer_id, 0),
                risk_level=_risk_level(days_overdue),
                credit_limit=credit_limit_by_dealer[dealer_id],
            )
        )
    result.sort(key=lambda d: d.outstanding, reverse=True)
    return result


async def _late_payment_counts(
    db: AsyncSession, company_id: uuid.UUID, today: date
) -> dict[uuid.UUID, int]:
    window_start = today - timedelta(days=_LATE_PAYMENT_WINDOW_DAYS)
    stmt = (
        select(Invoice.dealer_id, func.count(Payment.id))
        .join(Payment, Payment.invoice_id == Invoice.id)
        .where(
            Invoice.company_id == company_id,
            Invoice.direction == InvoiceDirection.receivable,
            Payment.payment_date > Invoice.due_date,
            Payment.payment_date >= window_start,
        )
        .group_by(Invoice.dealer_id)
    )
    rows = (await db.execute(stmt)).all()
    return dict(rows)


async def data_freshness_hours(
    db: AsyncSession, company_id: uuid.UUID, now: datetime
) -> float | None:
    """Hours since this company's most recent Tally import, or None if it has
    never imported. The single source of truth for "how stale is this company's
    data" — reused by build_snapshot below and by the NotificationEngine's
    founder stale-data digest, so the briefing footer and the founder nudge can
    never disagree about freshness.
    """
    latest = await db.scalar(
        select(func.max(ImportLog.imported_at)).where(ImportLog.company_id == company_id)
    )
    if latest is None:
        return None
    return (now - latest).total_seconds() / 3600.0


async def build_snapshot(db: AsyncSession, company_id: uuid.UUID) -> Snapshot:
    company = await db.get(Company, company_id)
    if company is None:
        raise ValueError(f"Company {company_id} not found")

    now = business_now(company.timezone)
    today = now.date()

    cash_available_today = await _cash_available_today(db, company)
    collections = await _expected_collections_7d(db, company_id, today)
    payments = await _expected_payments_7d(db, company_id, today)
    overdue_dealers = await _overdue_dealers(db, company_id, today)
    freshness_hours = await data_freshness_hours(db, company_id, now)
    dealers_missing_fields_count = await count_parties_missing_fields(db, Dealer, company_id)
    suppliers_missing_fields_count = await count_parties_missing_fields(db, Supplier, company_id)

    collections_total = sum((c.amount for c in collections), Decimal("0.00"))
    payments_total = sum((p.amount for p in payments), Decimal("0.00"))
    net_cash_position = cash_available_today + collections_total - payments_total
    deficit_forecast = forecast_cash_deficit(cash_available_today, collections, payments, today)

    return Snapshot(
        company_id=company_id,
        generated_at=now,
        cash_available_today=cash_available_today,
        expected_collections_7d=collections,
        expected_collections_7d_total=collections_total,
        expected_payments_7d=payments,
        expected_payments_7d_total=payments_total,
        net_cash_position=net_cash_position,
        cash_deficit=net_cash_position < 0,
        overdue_dealers=overdue_dealers,
        data_freshness_hours=freshness_hours,
        data_completeness_score=None,
        confidence_score=_confidence_score(freshness_hours),
        business_name=company.business_name,
        locale=resolve_locale(company),
        dealers_missing_fields_count=dealers_missing_fields_count,
        suppliers_missing_fields_count=suppliers_missing_fields_count,
        cash_deficit_forecast=deficit_forecast,
    )
