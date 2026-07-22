"""Deterministic WhatsApp report replies — no LLM involved.

Every one of these answers a *fixed, tappable menu option* (Reports &
Overview / Dealers & Suppliers / Inventory & Transactions), not a free-form
question — so none of them should ever depend on an LLM call succeeding.
Reuses the exact same data sources the LLM assistant's tools do
(app/services/agent/read_tools.py's private query functions, and
app/services/query_menu.py's Snapshot-based report builders for the four
numbered-menu reports) so the numbers are identical either way; only the
delivery path differs. See app/api/webhooks/whatsapp.py's _INSTANT_COMMANDS
registry for how these get wired to keywords/menu-row taps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.i18n import resolve_locale, t
from app.models.company import Company
from app.models.dealer import Dealer
from app.models.faq import FAQ
from app.models.invoice import Invoice
from app.models.notification_log import NotificationLog
from app.models.payment import Payment
from app.models.product import Product
from app.models.supplier import Supplier
from app.services.agent.read_tools import (
    _calculate_sales_impact,
    _find_product,
    _get_party_balance,
    _list_dealers,
    _list_suppliers,
    _list_top_creditors,
    _list_top_debtors,
)
from app.services.company_export import generate_export_link
from app.services.importer.normalizer import parse_amount
from app.services.money_format import format_inr, format_signed_inr
from app.services.onboarding_flow import _format_quantity
from app.services.priority_actions import get_priority_actions
from app.services.query_menu import (
    build_cash_position_report,
    build_collections_report,
    build_dealer_risk_report,
    build_suppliers_report,
)
from app.services.sales_impact_parser import parse_sales_impact_query
from app.services.snapshot import build_snapshot, business_now, business_timezone
from app.services.trend_analytics import DealerTrend, ProductSalesTrend, build_trend_report

# WhatsApp's text message body caps around 4096 characters — comfortably
# fits this many lines with room for a header/footer, generous enough that
# "and N more" almost never triggers for a real distributor's data.
_LIST_REPLY_CAP = 60
# "Recent" views (a quick glance, not the full list) — the "all" variant of
# the same report uses _LIST_REPLY_CAP instead. Both sort by the same
# recency field; only the limit differs.
_RECENT_LIST_CAP = 15


async def business_summary_reply(db: AsyncSession, company: Company) -> str:
    s = await build_snapshot(db, company.id)
    loc = resolve_locale(company)
    overdue_line = t("reports.summary.overdue_count", loc, count=len(s.overdue_dealers))
    if s.overdue_dealers:
        overdue_line += t("reports.summary.overdue_hint", loc)
    lines = [
        t("reports.summary.header", loc),
        "",
        t("reports.summary.cash_now", loc, amount=format_inr(s.cash_available_today)),
        t("reports.summary.net_7d", loc, amount=format_signed_inr(s.net_cash_position)),
        t("reports.summary.expected_in", loc, amount=format_inr(s.expected_collections_7d_total)),
        t("reports.summary.expected_out", loc, amount=format_inr(s.expected_payments_7d_total)),
        t("reports.summary.shortage", loc)
        if s.cash_deficit
        else t("reports.summary.no_shortage", loc),
        overdue_line,
    ]
    return "\n".join(lines)


async def cash_position_reply(db: AsyncSession, company: Company) -> str:
    s = await build_snapshot(db, company.id)
    return build_cash_position_report(s)


async def priorities_reply(db: AsyncSession, company: Company) -> str:
    actions = await get_priority_actions(db, company.id)
    loc = resolve_locale(company)
    if not actions:
        return t("reports.priorities.none", loc)
    lines = [f"{i}. {a.reason}" for i, a in enumerate(actions, start=1)]
    return t("reports.priorities.header", loc) + "\n\n" + "\n\n".join(lines)


async def overdue_dealers_reply(db: AsyncSession, company: Company) -> str:
    s = await build_snapshot(db, company.id)
    return build_dealer_risk_report(s)


async def upcoming_collections_reply(db: AsyncSession, company: Company) -> str:
    s = await build_snapshot(db, company.id)
    return build_collections_report(s)


async def upcoming_payments_reply(db: AsyncSession, company: Company) -> str:
    s = await build_snapshot(db, company.id)
    return build_suppliers_report(s)


_TREND_TOP_N = 3


def _pct_change_display(current: Decimal, prior: Decimal) -> str:
    """Arrow + percentage — a symbol/number, not a translated word (same
    "universal, not translated" treatment emoji get elsewhere in this
    catalog), so it's safe to interpolate into any locale without a key.
    """
    if prior == 0:
        return "↑ —%" if current > 0 else "→ 0%"
    pct = (current - prior) / prior * 100
    arrow = "↑" if pct > 0 else ("↓" if pct < 0 else "→")
    return f"{arrow} {abs(pct):.0f}%"


def _format_signed_qty(delta: Decimal) -> str:
    text = _format_quantity(abs(delta))
    return f"+{text}" if delta >= 0 else f"-{text}"


def _top_movers(items: list, key) -> tuple[list, list]:
    """Top N risers (largest positive delta) and top N fallers (largest
    negative delta), each sorted so the biggest mover is first.
    """
    rising = sorted((i for i in items if key(i) > 0), key=key, reverse=True)[:_TREND_TOP_N]
    falling = sorted((i for i in items if key(i) < 0), key=key)[:_TREND_TOP_N]
    return rising, falling


def _dealer_trend_line(d: DealerTrend, key: str, loc) -> str:
    return t(
        key,
        loc,
        name=d.dealer_name,
        value_delta=format_signed_inr(d.value_delta),
        outstanding_delta=format_signed_inr(d.outstanding_delta),
    )


def _product_trend_line(p: ProductSalesTrend, key: str, loc) -> str:
    return t(
        key,
        loc,
        name=p.product_name,
        unit_delta=_format_signed_qty(p.units_delta),
        revenue_delta=format_signed_inr(p.revenue_current - p.revenue_prior),
    )


async def trend_report_reply(db: AsyncSession, company: Company) -> str:
    """"trend report"/"business trends" — a hybrid reply: a one-line
    headline, the cash/dealer/product detail sections, then a link to the
    full Business Trends workbook (every dealer/product, not just the top 3
    each way shown here). See app/services/trend_analytics.py for the
    underlying math and app/services/reports/trend.py for the workbook.
    """
    loc = resolve_locale(company)
    today = business_now(company.timezone).date()
    report = await build_trend_report(db, company.id, today)
    cash = report.cash

    dealers_slowing = sum(1 for d in report.dealers if d.value_delta < 0)
    products_declining = sum(1 for p in report.products if p.units_delta < 0)
    lines = [
        t(
            "reports.trend.headline",
            loc,
            collections_pct=_pct_change_display(cash.collections_current, cash.collections_prior),
            payments_pct=_pct_change_display(cash.payments_current, cash.payments_prior),
            net_delta=format_signed_inr(cash.net_cash_current - cash.net_cash_prior),
            dealers_slowing=dealers_slowing,
            products_declining=products_declining,
        ),
        "",
        t("reports.trend.header", loc),
        t(
            "reports.trend.collections_line",
            loc,
            current=format_inr(cash.collections_current),
            prior=format_inr(cash.collections_prior),
        ),
        t(
            "reports.trend.payments_line",
            loc,
            current=format_inr(cash.payments_current),
            prior=format_inr(cash.payments_prior),
        ),
        t(
            "reports.trend.net_line",
            loc,
            current=format_signed_inr(cash.net_cash_current),
            prior=format_signed_inr(cash.net_cash_prior),
        ),
        t(
            "reports.trend.sales_line",
            loc,
            current=format_inr(cash.sales_current),
            prior=format_inr(cash.sales_prior),
        ),
        "",
        t("reports.trend.dealers_header", loc),
    ]

    dealers_rising, dealers_falling = _top_movers(report.dealers, lambda d: d.value_delta)
    if not dealers_rising and not dealers_falling:
        lines.append(t("reports.trend.dealers_none", loc))
    else:
        lines += [
            _dealer_trend_line(d, "reports.trend.dealer_rising_line", loc) for d in dealers_rising
        ]
        lines += [
            _dealer_trend_line(d, "reports.trend.dealer_falling_line", loc)
            for d in dealers_falling
        ]

    lines += ["", t("reports.trend.products_header", loc)]
    products_rising, products_falling = _top_movers(report.products, lambda p: p.units_delta)
    if not products_rising and not products_falling:
        lines.append(t("reports.trend.products_none", loc))
    else:
        lines += [
            _product_trend_line(p, "reports.trend.product_rising_line", loc)
            for p in products_rising
        ]
        lines += [
            _product_trend_line(p, "reports.trend.product_falling_line", loc)
            for p in products_falling
        ]

    settings = get_settings()
    if settings.export_link_secret and settings.public_base_url:
        link = generate_export_link(company, base_url=settings.public_base_url, report="trend")
        lines += [
            "",
            t(
                "reports.trend.full_detail_link",
                loc,
                link=link,
                ttl=settings.export_link_ttl_minutes,
            ),
        ]

    return "\n".join(lines)


def _party_line(name: str, phone: str | None, outstanding: str, loc) -> str:
    return t(
        "reports.party.line",
        loc,
        name=name,
        phone=phone or t("reports.party.no_phone", loc),
        amount=format_inr(Decimal(outstanding)),
    )


async def all_dealers_reply(db: AsyncSession, company: Company) -> str:
    result = await _list_dealers(db, company)
    dealers = result["dealers"]
    loc = resolve_locale(company)
    if not dealers:
        return t("reports.dealers.none", loc)
    lines = [_party_line(d["name"], d["phone"], d["outstanding"], loc) for d in dealers]
    return t("reports.dealers.header", loc, count=len(dealers)) + "\n\n" + "\n\n".join(lines)


async def all_suppliers_reply(db: AsyncSession, company: Company) -> str:
    result = await _list_suppliers(db, company)
    suppliers = result["suppliers"]
    loc = resolve_locale(company)
    if not suppliers:
        return t("reports.suppliers_list.none", loc)
    lines = [_party_line(s["name"], s["phone"], s["outstanding"], loc) for s in suppliers]
    return (
        t("reports.suppliers_list.header", loc, count=len(suppliers)) + "\n\n" + "\n\n".join(lines)
    )


async def top_debtors_reply(db: AsyncSession, company: Company) -> str:
    result = await _list_top_debtors(db, company, limit=20)
    dealers = result["dealers_who_owe_you"]
    loc = resolve_locale(company)
    if not dealers:
        return t("reports.top_debtors.none", loc)
    lines = [
        f"{i}. {d['name']} — {format_inr(Decimal(d['outstanding']))}"
        for i, d in enumerate(dealers, start=1)
    ]
    return t("reports.top_debtors.header", loc) + "\n\n" + "\n\n".join(lines)


async def top_creditors_reply(db: AsyncSession, company: Company) -> str:
    result = await _list_top_creditors(db, company, limit=20)
    suppliers = result["suppliers_you_owe"]
    loc = resolve_locale(company)
    if not suppliers:
        return t("reports.top_creditors.none", loc)
    lines = [
        f"{i}. {s['name']} — {format_inr(Decimal(s['outstanding']))}"
        for i, s in enumerate(suppliers, start=1)
    ]
    return t("reports.top_creditors.header", loc) + "\n\n" + "\n\n".join(lines)


def _product_line(product: Product, loc) -> str:
    unit_suffix = f" {product.unit}" if product.unit else ""
    price = (
        format_inr(product.selling_price)
        if product.selling_price is not None
        else t("reports.product.price_not_set", loc)
    )
    quantity = _format_quantity(product.stock_quantity)
    return f"{product.name} — {quantity}{unit_suffix} — {price}"


async def _inventory_query_reply(
    db: AsyncSession, company: Company, *, limit: int, label_key: str
) -> str:
    loc = resolve_locale(company)
    total = await db.scalar(
        select(func.count()).select_from(Product).where(Product.company_id == company.id)
    )
    if not total:
        return t("reports.inventory.none", loc)

    stmt = (
        select(Product)
        .where(Product.company_id == company.id)
        # created_at alone can tie: Postgres's now() returns one value per
        # transaction, so products added in the same bulk-add message share
        # a timestamp. name is a stable, deterministic tiebreaker — same
        # "recency field + stable secondary key" shape as invoices below.
        .order_by(Product.created_at.desc(), Product.name)
        .limit(limit)
    )
    products = (await db.scalars(stmt)).all()
    lines = [_product_line(p, loc) for p in products]
    remaining = total - len(products)
    label = t(label_key, loc)
    header = (
        t("reports.inventory.header_partial", loc, label=label, count=len(products), total=total)
        if remaining > 0
        else t("reports.inventory.header_full", loc, label=label, count=len(products))
    )
    footer = t("reports.inventory.more", loc, remaining=remaining) if remaining > 0 else ""
    return f"{header}\n\n" + "\n\n".join(lines) + footer


async def recent_inventory_reply(db: AsyncSession, company: Company) -> str:
    return await _inventory_query_reply(
        db, company, limit=_RECENT_LIST_CAP, label_key="reports.inventory.label_recent"
    )


async def all_inventory_reply(db: AsyncSession, company: Company) -> str:
    return await _inventory_query_reply(
        db, company, limit=_LIST_REPLY_CAP, label_key="reports.inventory.label_all"
    )


async def faqs_reply(db: AsyncSession, company: Company) -> str:
    faqs = (
        await db.scalars(select(FAQ).where(FAQ.company_id == company.id).order_by(FAQ.created_at))
    ).all()
    loc = resolve_locale(company)
    if not faqs:
        return t("reports.faq.none", loc)
    lines = [t("reports.faq.qa", loc, question=f.question, answer=f.answer) for f in faqs]
    return t("reports.faq.header", loc, count=len(faqs)) + "\n\n" + "\n\n".join(lines)


async def _invoices_query_reply(
    db: AsyncSession, company: Company, *, limit: int, label_key: str
) -> str:
    loc = resolve_locale(company)
    total = await db.scalar(
        select(func.count()).select_from(Invoice).where(Invoice.company_id == company.id)
    )
    if not total:
        return t("reports.invoices.none", loc)

    stmt = (
        select(Invoice, Dealer.name, Supplier.name)
        .outerjoin(Dealer, Invoice.dealer_id == Dealer.id)
        .outerjoin(Supplier, Invoice.supplier_id == Supplier.id)
        .where(Invoice.company_id == company.id)
        .order_by(Invoice.invoice_date.desc(), Invoice.invoice_number)
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    # invoice_number / party name / amount / status value / date are all data —
    # interpolated, not translated; only "due" and "unknown party" are words.
    lines = [
        t(
            "reports.invoices.line",
            loc,
            number=invoice.invoice_number,
            party=dealer_name or supplier_name or t("reports.unknown_party", loc),
            amount=format_inr(invoice.total_amount),
            status=invoice.status.value,
            due=t("reports.due.date", loc, date=invoice.due_date.isoformat()),
        )
        for invoice, dealer_name, supplier_name in rows
    ]
    remaining = total - len(rows)
    label = t(label_key, loc)
    header = (
        t("reports.invoices.header_partial", loc, label=label, count=len(rows), total=total)
        if remaining > 0
        else t("reports.invoices.header_full", loc, label=label, count=len(rows))
    )
    footer = t("reports.invoices.more", loc, remaining=remaining) if remaining > 0 else ""
    return f"{header}\n\n" + "\n\n".join(lines) + footer


async def recent_invoices_reply(db: AsyncSession, company: Company) -> str:
    return await _invoices_query_reply(
        db, company, limit=_RECENT_LIST_CAP, label_key="reports.invoices.label_recent"
    )


async def all_invoices_reply(db: AsyncSession, company: Company) -> str:
    return await _invoices_query_reply(
        db, company, limit=_LIST_REPLY_CAP, label_key="reports.invoices.label_all"
    )


async def _payments_query_reply(
    db: AsyncSession, company: Company, *, limit: int, label_key: str
) -> str:
    loc = resolve_locale(company)
    total = await db.scalar(
        select(func.count()).select_from(Payment).where(Payment.company_id == company.id)
    )
    if not total:
        return t("reports.payments.none", loc)

    stmt = (
        select(Payment, Invoice.invoice_number, Invoice.direction)
        .join(Invoice, Payment.invoice_id == Invoice.id)
        .where(Payment.company_id == company.id)
        # payment_date is a plain date (user-supplied — "today", a CSV
        # import date), so same-day payments tie constantly; created_at
        # (server-assigned) breaks the tie deterministically.
        .order_by(Payment.payment_date.desc(), Payment.created_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    lines = [
        t(
            "reports.payments.line",
            loc,
            amount=format_inr(payment.amount),
            direction=(
                t("reports.payments.from", loc)
                if direction.value == "receivable"
                else t("reports.payments.to", loc)
            ),
            number=invoice_number,
            date=payment.payment_date.isoformat(),
        )
        for payment, invoice_number, direction in rows
    ]
    remaining = total - len(rows)
    label = t(label_key, loc)
    header = (
        t("reports.payments.header_partial", loc, label=label, count=len(rows), total=total)
        if remaining > 0
        else t("reports.payments.header_full", loc, label=label, count=len(rows))
    )
    footer = t("reports.payments.more", loc, remaining=remaining) if remaining > 0 else ""
    return f"{header}\n\n" + "\n\n".join(lines) + footer


async def recent_payments_reply(db: AsyncSession, company: Company) -> str:
    return await _payments_query_reply(
        db, company, limit=_RECENT_LIST_CAP, label_key="reports.payments.label_recent"
    )


async def all_payments_reply(db: AsyncSession, company: Company) -> str:
    return await _payments_query_reply(
        db, company, limit=_LIST_REPLY_CAP, label_key="reports.payments.label_all"
    )


async def party_balance_reply(db: AsyncSession, company: Company, name: str) -> str:
    """Backs the "balance <name>" prefix command — reuses read_tools.py's
    own fuzzy dealer/supplier name match so the deterministic and LLM-tool
    paths can never disagree on who matched.
    """
    result = await _get_party_balance(db, company, name)
    loc = resolve_locale(company)
    if "error" in result:
        return result["error"]
    outstanding = format_inr(Decimal(result["outstanding"]))
    key = (
        "reports.balance.dealer_owes"
        if result["relationship"] == "dealer_owes_you"
        else "reports.balance.you_owe"
    )
    return t(key, loc, party=result["party"], amount=outstanding)


async def stock_item_reply(db: AsyncSession, company: Company, name: str) -> str:
    """Backs the "stock <item>" prefix command — reuses read_tools.py's own
    fuzzy/singular-folding product match (the same one calculate_sales_impact
    uses) so this can never name a different product than the LLM tool would.
    """
    product = await _find_product(db, company, name)
    loc = resolve_locale(company)
    if product is None:
        return t("reports.stock.not_found", loc, name=name)
    unit_suffix = f" {product.unit}" if product.unit else ""
    price = (
        format_inr(product.selling_price)
        if product.selling_price is not None
        else t("reports.product.price_not_set", loc)
    )
    quantity = _format_quantity(product.stock_quantity)
    return t(
        "reports.stock.line",
        loc,
        name=product.name,
        stock=f"{quantity}{unit_suffix}",
        price=price,
    )


async def sales_impact_reply(db: AsyncSession, company: Company, items: list[dict]) -> str:
    """Backs the deterministic "if I sell N of X" fast-path — same
    calculate_sales_impact math the LLM tool uses, formatted as a fixed
    template instead of LLM prose. `items` is already-parsed
    [{"product_name", "quantity_sold"}, ...] from
    app/api/webhooks/whatsapp.py's conservative parser; this function does
    no further NL interpretation, only formatting.
    """
    result = await _calculate_sales_impact(db, company, items)
    loc = resolve_locale(company)
    lines = []
    for entry in result["items"]:
        if "error" in entry:
            lines.append(f"- {entry['product_name']}: {entry['error']}")
            continue
        quantity_sold = _format_quantity(Decimal(entry["quantity_sold"]))
        bits = [f"{quantity_sold} {entry['product_name']}"]
        if "revenue" in entry:
            bits.append(
                t("reports.sales.revenue", loc, amount=format_inr(Decimal(entry["revenue"])))
            )
        if "profit" in entry:
            bits.append(t("reports.sales.profit", loc, amount=format_inr(Decimal(entry["profit"]))))
        stock_remaining = _format_quantity(Decimal(entry["stock_remaining"]))
        bits.append(t("reports.sales.left", loc, qty=stock_remaining))
        lines.append("- " + ", ".join(bits))

    footer_bits = [
        t("reports.sales.total_revenue", loc, amount=format_inr(Decimal(result["total_revenue"])))
    ]
    if Decimal(result["total_profit"]) != 0 or not result["items_missing_cost_data"]:
        footer_bits.append(
            t("reports.sales.total_profit", loc, amount=format_inr(Decimal(result["total_profit"])))
        )
    if result["items_missing_cost_data"]:
        missing = ", ".join(result["items_missing_cost_data"])
        footer_bits.append(t("reports.sales.no_cost", loc, missing=missing))

    return "\n\n".join(lines) + "\n\n" + "\n".join(footer_bits)


async def _resolve_product_name(db: AsyncSession, company: Company, raw_name: str) -> str | None:
    """Trims trailing words from a parser's raw name guess (e.g. "rice how
    much" -> "rice how" -> "rice") until read_tools.py's own fuzzy
    _find_product matches, or gives up. Reusing that exact matcher means
    this can never resolve a different product than the LLM tool would.
    """
    words = raw_name.split()
    for word_count in range(len(words), 0, -1):
        candidate = " ".join(words[:word_count])
        product = await _find_product(db, company, candidate)
        if product is not None:
            return product.name
    return None


async def try_deterministic_sales_impact(
    db: AsyncSession, company: Company, text: str
) -> str | None:
    """The deterministic "if I sell N of X" fast-path. Returns None (caller
    falls back to the LLM + calculate_sales_impact + money_guard path)
    unless every extracted item resolves to a real catalogue product with a
    positive quantity — never a partial or best-guess answer, since a wrong
    but confidently-worded deterministic reply is worse than the existing
    verified LLM path.
    """
    raw_items = parse_sales_impact_query(text)
    if not raw_items:
        return None

    resolved: list[dict[str, str]] = []
    for raw in raw_items:
        try:
            # parse_amount quantizes to 2 decimal places, same as every other
            # quantity in this codebase — a bare Decimal("50") (no decimal
            # point in its string form) trips _format_quantity's rstrip("0")
            # into mangling whole numbers ("50" -> "5"); quantized input never
            # does, since it always has a real ".00" to strip down from.
            quantity = parse_amount(raw["quantity_sold"])
        except ValueError:
            return None
        if quantity <= 0:
            return None
        product_name = await _resolve_product_name(db, company, raw["product_name"])
        if product_name is None:
            return None
        resolved.append({"product_name": product_name, "quantity_sold": str(quantity)})

    return await sales_impact_reply(db, company, resolved)


# ── Delivery/read status ("delivery status") ────────────────────────────────
#
# Only the two notification types a distributor directly triggers themselves
# (an invoice PDF send, a marketing broadcast) — not every automated
# background alert (supplier reminders, dealer overdue nudges, briefings),
# which the distributor never explicitly asked to send and already reads
# inline in this same chat. NotificationLog.delivery_status is kept current
# by the whatsapp_status_received webhook (app/api/webhooks/whatsapp.py); this
# reply only ever reads it, never makes a fresh Meta call.
_DELIVERY_STATUS_TYPES = ("invoice_document", "marketing_broadcast")
# How many recent NotificationLog rows to scan before grouping — generous
# enough to cover a handful of recent invoices plus one full broadcast batch.
_DELIVERY_STATUS_SCAN_LIMIT = 60
# How many grouped lines to actually show — keeps the reply well inside
# WhatsApp's message-length comfort zone even with many small batches.
_DELIVERY_STATUS_GROUP_LIMIT = 8

_DELIVERY_STATUS_LABEL_KEYS = {
    "sent": "reports.delivery_status.status.sent",
    "delivered": "reports.delivery_status.status.delivered",
    "read": "reports.delivery_status.status.read",
    "failed": "reports.delivery_status.status.failed",
    "failed_to_send": "reports.delivery_status.status.failed_to_send",
}


@dataclass
class _DeliveryBatch:
    notification_type: str
    message_text: str
    recipient_phone: str
    latest_sent_at: datetime
    status_counts: dict[str, int] = field(default_factory=dict)


def _delivery_status_label(batch: _DeliveryBatch, dealer_names: dict[str, str], loc) -> str:
    recipients = sum(batch.status_counts.values())
    if batch.notification_type == "marketing_broadcast":
        return t("reports.delivery_status.broadcast_label", loc, count=recipients)
    # invoice_document's message_text is always f"Invoice {number} PDF"
    # (app/services/invoice_delivery.py) — our own literal, safe to trim.
    invoice_label = batch.message_text.removesuffix(" PDF")
    party = dealer_names.get(batch.recipient_phone, batch.recipient_phone)
    return t("reports.delivery_status.invoice_label", loc, invoice=invoice_label, party=party)


async def delivery_status_reply(db: AsyncSession, company: Company) -> str:
    """"delivery status" — Meta delivery/read status for recent invoice
    sends and marketing broadcasts, grouped into one line per batch. A
    broadcast writes one NotificationLog row per recipient with identical
    message_text, so grouping by (notification_type, message_text) naturally
    reports "Broadcast — 42 dealers: 38 delivered, 4 sent" instead of 42
    separate lines; an invoice send is already its own group since every
    invoice's message_text is unique.
    """
    loc = resolve_locale(company)
    stmt = (
        select(NotificationLog)
        .where(
            NotificationLog.company_id == company.id,
            NotificationLog.notification_type.in_(_DELIVERY_STATUS_TYPES),
        )
        .order_by(NotificationLog.sent_at.desc())
        .limit(_DELIVERY_STATUS_SCAN_LIMIT)
    )
    rows = (await db.scalars(stmt)).all()
    if not rows:
        return t("reports.delivery_status.none", loc)

    batches: dict[tuple[str, str], _DeliveryBatch] = {}
    order: list[tuple[str, str]] = []
    for row in rows:
        key = (row.notification_type, row.message_text)
        batch = batches.get(key)
        if batch is None:
            batch = _DeliveryBatch(
                notification_type=row.notification_type,
                message_text=row.message_text,
                recipient_phone=row.recipient_whatsapp,
                latest_sent_at=row.sent_at,
            )
            batches[key] = batch
            order.append(key)
        status = row.delivery_status or "sent"
        batch.status_counts[status] = batch.status_counts.get(status, 0) + 1
        if row.sent_at > batch.latest_sent_at:
            batch.latest_sent_at = row.sent_at

    dealer_phones = {
        b.recipient_phone for k, b in batches.items() if k[0] == "invoice_document"
    }
    dealer_names: dict[str, str] = {}
    if dealer_phones:
        dealer_rows = await db.execute(
            select(Dealer.phone, Dealer.name).where(
                Dealer.company_id == company.id, Dealer.phone.in_(dealer_phones)
            )
        )
        dealer_names = dict(dealer_rows.all())

    zone = business_timezone(company.timezone)
    lines = []
    for key in order[:_DELIVERY_STATUS_GROUP_LIMIT]:
        batch = batches[key]
        label = _delivery_status_label(batch, dealer_names, loc)
        counts = ", ".join(
            t(
                "reports.delivery_status.count_part",
                loc,
                count=count,
                status=t(_DELIVERY_STATUS_LABEL_KEYS[status], loc)
                if status in _DELIVERY_STATUS_LABEL_KEYS
                else status,
            )
            for status, count in sorted(batch.status_counts.items(), key=lambda kv: -kv[1])
        )
        when = batch.latest_sent_at.astimezone(zone).strftime("%Y-%m-%d %H:%M")
        lines.append(t("reports.delivery_status.line", loc, label=label, when=when, counts=counts))

    header = t("reports.delivery_status.header", loc)
    return header + "\n\n" + "\n".join(lines)
