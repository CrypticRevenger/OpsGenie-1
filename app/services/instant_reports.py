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

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.dealer import Dealer
from app.models.faq import FAQ
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.supplier import Supplier
from app.services.agent.read_tools import (
    _calculate_sales_impact,
    _find_product,
    _get_inventory,
    _get_party_balance,
    _list_dealers,
    _list_suppliers,
    _list_top_creditors,
    _list_top_debtors,
)
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
from app.services.snapshot import build_snapshot

# WhatsApp's text message body caps around 4096 characters — comfortably
# fits this many lines with room for a header/footer, generous enough that
# "and N more" almost never triggers for a real distributor's data.
_LIST_REPLY_CAP = 60


async def business_summary_reply(db: AsyncSession, company: Company) -> str:
    s = await build_snapshot(db, company.id)
    lines = [
        "📊 Business Summary",
        "",
        f"Cash available now: {format_inr(s.cash_available_today)}",
        f"Net cash position (7d): {format_signed_inr(s.net_cash_position)}",
        f"Expected in (7d): {format_inr(s.expected_collections_7d_total)}",
        f"Expected out (7d): {format_inr(s.expected_payments_7d_total)}",
        "Cash shortage expected this week." if s.cash_deficit else "No cash shortage expected.",
        f"Overdue dealers: {len(s.overdue_dealers)}"
        + (" — reply 'overdue' for details." if s.overdue_dealers else ""),
    ]
    return "\n".join(lines)


async def cash_position_reply(db: AsyncSession, company: Company) -> str:
    s = await build_snapshot(db, company.id)
    return build_cash_position_report(s)


async def priorities_reply(db: AsyncSession, company: Company) -> str:
    actions = await get_priority_actions(db, company.id)
    if not actions:
        return "🎯 Nothing urgent right now — no priority actions."
    lines = [f"{i}. {a.reason}" for i, a in enumerate(actions, start=1)]
    return "🎯 Priorities\n\n" + "\n".join(lines)


async def overdue_dealers_reply(db: AsyncSession, company: Company) -> str:
    s = await build_snapshot(db, company.id)
    return build_dealer_risk_report(s)


async def upcoming_collections_reply(db: AsyncSession, company: Company) -> str:
    s = await build_snapshot(db, company.id)
    return build_collections_report(s)


async def upcoming_payments_reply(db: AsyncSession, company: Company) -> str:
    s = await build_snapshot(db, company.id)
    return build_suppliers_report(s)


def _party_line(name: str, phone: str | None, outstanding: str) -> str:
    return f"{name} — {phone or 'no phone'} — outstanding {format_inr(Decimal(outstanding))}"


async def all_dealers_reply(db: AsyncSession, company: Company) -> str:
    result = await _list_dealers(db, company)
    dealers = result["dealers"]
    if not dealers:
        return "You don't have any dealers on file yet."
    lines = [_party_line(d["name"], d["phone"], d["outstanding"]) for d in dealers]
    return f"👥 Dealers ({len(dealers)}):\n" + "\n".join(lines)


async def all_suppliers_reply(db: AsyncSession, company: Company) -> str:
    result = await _list_suppliers(db, company)
    suppliers = result["suppliers"]
    if not suppliers:
        return "You don't have any suppliers on file yet."
    lines = [_party_line(s["name"], s["phone"], s["outstanding"]) for s in suppliers]
    return f"🚚 Suppliers ({len(suppliers)}):\n" + "\n".join(lines)


async def top_debtors_reply(db: AsyncSession, company: Company) -> str:
    result = await _list_top_debtors(db, company, limit=20)
    dealers = result["dealers_who_owe_you"]
    if not dealers:
        return "No dealer currently owes you anything."
    lines = [
        f"{i}. {d['name']} — {format_inr(Decimal(d['outstanding']))}"
        for i, d in enumerate(dealers, start=1)
    ]
    return "💰 Top Debtors\n" + "\n".join(lines)


async def top_creditors_reply(db: AsyncSession, company: Company) -> str:
    result = await _list_top_creditors(db, company, limit=20)
    suppliers = result["suppliers_you_owe"]
    if not suppliers:
        return "You don't currently owe any supplier anything."
    lines = [
        f"{i}. {s['name']} — {format_inr(Decimal(s['outstanding']))}"
        for i, s in enumerate(suppliers, start=1)
    ]
    return "💸 Top Creditors\n" + "\n".join(lines)


def _product_line(product: dict) -> str:
    unit_suffix = f" {product['unit']}" if product["unit"] else ""
    price = (
        format_inr(Decimal(product["selling_price"]))
        if product["selling_price"] is not None
        else "price not set"
    )
    quantity = _format_quantity(Decimal(product["stock_quantity"]))
    return f"{product['name']} — {quantity}{unit_suffix} — {price}"


async def inventory_reply(db: AsyncSession, company: Company) -> str:
    result = await _get_inventory(db, company)
    products = result["inventory"]
    if not products:
        return "You don't have any products in your catalogue yet."
    lines = [_product_line(p) for p in products]
    return f"📦 Inventory ({len(products)}):\n" + "\n".join(lines)


async def faqs_reply(db: AsyncSession, company: Company) -> str:
    faqs = (
        await db.scalars(select(FAQ).where(FAQ.company_id == company.id).order_by(FAQ.created_at))
    ).all()
    if not faqs:
        return "You don't have any saved policy answers yet."
    lines = [f"Q: {f.question}\nA: {f.answer}" for f in faqs]
    return f"❓ FAQs ({len(faqs)}):\n\n" + "\n\n".join(lines)


async def invoices_reply(db: AsyncSession, company: Company) -> str:
    total = await db.scalar(
        select(func.count()).select_from(Invoice).where(Invoice.company_id == company.id)
    )
    if not total:
        return "You don't have any invoices yet."

    stmt = (
        select(Invoice, Dealer.name, Supplier.name)
        .outerjoin(Dealer, Invoice.dealer_id == Dealer.id)
        .outerjoin(Supplier, Invoice.supplier_id == Supplier.id)
        .where(Invoice.company_id == company.id)
        .order_by(Invoice.invoice_date.desc(), Invoice.invoice_number)
        .limit(_LIST_REPLY_CAP)
    )
    rows = (await db.execute(stmt)).all()
    lines = [
        f"{invoice.invoice_number} — {dealer_name or supplier_name or 'unknown party'} — "
        f"{format_inr(invoice.total_amount)} — {invoice.status.value} — "
        f"due {invoice.due_date.isoformat()}"
        for invoice, dealer_name, supplier_name in rows
    ]
    remaining = total - len(rows)
    header = (
        f"📄 Invoices ({len(rows)} of {total}):" if remaining > 0 else f"📄 Invoices ({len(rows)}):"
    )
    footer = (
        f"\n…and {remaining} more — use 'export data' for the full list." if remaining > 0 else ""
    )
    return f"{header}\n" + "\n".join(lines) + footer


async def payments_reply(db: AsyncSession, company: Company) -> str:
    total = await db.scalar(
        select(func.count()).select_from(Payment).where(Payment.company_id == company.id)
    )
    if not total:
        return "You don't have any payments recorded yet."

    stmt = (
        select(Payment, Invoice.invoice_number, Invoice.direction)
        .join(Invoice, Payment.invoice_id == Invoice.id)
        .where(Payment.company_id == company.id)
        .order_by(Payment.payment_date.desc())
        .limit(_LIST_REPLY_CAP)
    )
    rows = (await db.execute(stmt)).all()
    lines = [
        f"{format_inr(payment.amount)} — {'from' if direction.value == 'receivable' else 'to'} "
        f"invoice {invoice_number} — {payment.payment_date.isoformat()}"
        for payment, invoice_number, direction in rows
    ]
    remaining = total - len(rows)
    header = (
        f"💵 Payments ({len(rows)} of {total}):" if remaining > 0 else f"💵 Payments ({len(rows)}):"
    )
    footer = (
        f"\n…and {remaining} more — use 'export data' for the full list." if remaining > 0 else ""
    )
    return f"{header}\n" + "\n".join(lines) + footer


async def party_balance_reply(db: AsyncSession, company: Company, name: str) -> str:
    """Backs the "balance <name>" prefix command — reuses read_tools.py's
    own fuzzy dealer/supplier name match so the deterministic and LLM-tool
    paths can never disagree on who matched.
    """
    result = await _get_party_balance(db, company, name)
    if "error" in result:
        return result["error"]
    outstanding = format_inr(Decimal(result["outstanding"]))
    verb = "owes you" if result["relationship"] == "dealer_owes_you" else "you owe"
    return f"{result['party']} {verb} {outstanding}."


async def stock_item_reply(db: AsyncSession, company: Company, name: str) -> str:
    """Backs the "stock <item>" prefix command — reuses read_tools.py's own
    fuzzy/singular-folding product match (the same one calculate_sales_impact
    uses) so this can never name a different product than the LLM tool would.
    """
    product = await _find_product(db, company, name)
    if product is None:
        return f"I couldn't find a product matching '{name}'."
    unit_suffix = f" {product.unit}" if product.unit else ""
    price = (
        format_inr(product.selling_price) if product.selling_price is not None else "price not set"
    )
    quantity = _format_quantity(product.stock_quantity)
    return f"{product.name} — {quantity}{unit_suffix} in stock — {price}"


async def sales_impact_reply(db: AsyncSession, company: Company, items: list[dict]) -> str:
    """Backs the deterministic "if I sell N of X" fast-path — same
    calculate_sales_impact math the LLM tool uses, formatted as a fixed
    template instead of LLM prose. `items` is already-parsed
    [{"product_name", "quantity_sold"}, ...] from
    app/api/webhooks/whatsapp.py's conservative parser; this function does
    no further NL interpretation, only formatting.
    """
    result = await _calculate_sales_impact(db, company, items)
    lines = []
    for entry in result["items"]:
        if "error" in entry:
            lines.append(f"- {entry['product_name']}: {entry['error']}")
            continue
        quantity_sold = _format_quantity(Decimal(entry["quantity_sold"]))
        bits = [f"{quantity_sold} {entry['product_name']}"]
        if "revenue" in entry:
            bits.append(f"revenue {format_inr(Decimal(entry['revenue']))}")
        if "profit" in entry:
            bits.append(f"profit {format_inr(Decimal(entry['profit']))}")
        stock_remaining = _format_quantity(Decimal(entry["stock_remaining"]))
        bits.append(f"{stock_remaining} left in stock")
        lines.append("- " + ", ".join(bits))

    footer_bits = [f"Total revenue: {format_inr(Decimal(result['total_revenue']))}"]
    if Decimal(result["total_profit"]) != 0 or not result["items_missing_cost_data"]:
        footer_bits.append(f"Total profit: {format_inr(Decimal(result['total_profit']))}")
    if result["items_missing_cost_data"]:
        missing = ", ".join(result["items_missing_cost_data"])
        footer_bits.append(f"(no purchase price on file for {missing} — excluded from profit)")

    return "\n".join(lines) + "\n\n" + "\n".join(footer_bits)


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
