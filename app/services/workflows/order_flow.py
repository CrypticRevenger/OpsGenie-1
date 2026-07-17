"""Guided create-order workflow — Phase 2B.

Dealer? -> (confirm-add if unknown) -> repeatable product loop (product name
-> price if not on file -> quantity) -> preview -> PendingOperation ->
YES/NO (handled by app/services/writes/pending_operation.py, not here). Same
state-machine shape as app/services/workflows/payment_flow.py: state lives in
Company.active_workflow ("create_order") + Company.workflow_scratch (this
flow's own step + collected fields), mutated in place, never committed here.

Orders are sales to dealers only (the receivable side) — unlike
record_payment, a brand-new dealer or product CAN proceed here, since an
order is exactly what gives a new dealer their first invoice and a new
product its catalogue entry. The dealer/product rows themselves are created
at confirm time inside app/services/writes/orders.py::create_order, not
here — this flow only collects and previews raw input.

"cancel"/"stop" are recognized at every step, matching payment_flow.py's
universal exit (an active workflow outranks the menu, so a user needs a
guaranteed way out).
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.dealer import Dealer
from app.models.pending_operation import PendingOperationType
from app.models.product import Product
from app.services.importer.normalizer import parse_amount
from app.services.money_format import format_inr
from app.services.onboarding_flow import _is
from app.services.writes.pending_operation import create_pending_operation


async def _match_dealer(db: AsyncSession, company_id, name: str) -> Dealer | None:
    return await db.scalar(
        select(Dealer).where(
            Dealer.company_id == company_id, func.lower(Dealer.name) == name.lower()
        )
    )


async def _match_product(db: AsyncSession, company_id, name: str) -> Product | None:
    return await db.scalar(
        select(Product).where(
            Product.company_id == company_id, func.lower(Product.name) == name.lower()
        )
    )


def start_order_workflow(company: Company) -> str:
    """Sets active_workflow + the first step's scratch and returns the
    opening question verbatim — called both by the webhook's keyword-match
    branch and (like payment_flow.py) any future agent starter tool.
    """
    company.active_workflow = "create_order"
    company.workflow_scratch = {"step": "awaiting_dealer"}
    return "Who is this order for? (dealer name)"


def _preview_and_finalize(scratch: dict, company_gst_rate: Decimal) -> tuple[str, dict]:
    """Builds the confirmation preview text and the PendingOperation payload
    from the collected raw items — never a precomputed total on its own, but
    a preview naturally has to show one; execute-time re-derives everything
    fresh against current prices/stock rather than trusting this text.

    The subtotal/GST/total breakdown must mirror what writes/orders.py's
    create_order actually commits (each line's own GST rate — its own
    override if set, else the company default — summed to a total), so the
    user confirms the same number they'll be invoiced for. A bare line-total
    sum with no GST would understate the real invoice total for any
    GST-configured company.
    """
    dealer_name = scratch["dealer_name"]
    items = scratch["items"]
    lines = []
    subtotal = Decimal("0.00")
    gst_amount = Decimal("0.00")
    line_rates: set[Decimal] = set()
    for item in items:
        price = Decimal(item["price"]) if item.get("price") is not None else Decimal("0.00")
        quantity = Decimal(item["quantity"])
        line_total = (price * quantity).quantize(Decimal("0.01"))
        item_gst_raw = item.get("gst_rate")
        line_gst_rate = Decimal(item_gst_raw) if item_gst_raw is not None else company_gst_rate
        line_gst_amount = (line_total * line_gst_rate / Decimal("100")).quantize(Decimal("0.01"))
        subtotal += line_total
        gst_amount += line_gst_amount
        line_rates.add(line_gst_rate)
        lines.append(
            f"- {quantity} x {item['product_name']} @ {format_inr(price)} "
            f"= {format_inr(line_total)}"
        )

    total = subtotal + gst_amount
    total_lines = [f"Subtotal: {format_inr(subtotal)}"]
    if gst_amount > 0:
        rate_label = f" ({next(iter(line_rates))}%)" if len(line_rates) == 1 else ""
        total_lines.append(f"GST{rate_label}: {format_inr(gst_amount)}")
    total_lines.append(f"Total: {format_inr(total)}")

    preview = (
        f"Confirm order for {dealer_name}:\n"
        + "\n".join(lines)
        + "\n"
        + "\n".join(total_lines)
        + "\nReply YES to create, NO to cancel."
    )
    payload = {"dealer_name": dealer_name, "items": items}
    return preview, payload


async def handle_order_workflow_message(db: AsyncSession, company: Company, text: str) -> str:
    """Advance the guided create-order flow by one message. Only mutates
    state/rows — the caller (the webhook) commits.
    """
    stripped = text.strip()

    if _is(stripped, "cancel", "stop"):
        company.active_workflow = None
        company.workflow_scratch = None
        return "OK, cancelled."

    scratch = dict(company.workflow_scratch or {})
    step = scratch.get("step")

    if step == "awaiting_dealer":
        if not stripped:
            return "Please tell me the dealer's name."
        dealer = await _match_dealer(db, company.id, stripped)
        if dealer is not None:
            scratch["dealer_name"] = dealer.name
            scratch["items"] = []
            scratch["step"] = "awaiting_product"
            company.workflow_scratch = scratch
            return f"Order for {dealer.name}. What product?"
        scratch["dealer_name"] = stripped
        scratch["step"] = "awaiting_new_dealer_confirm"
        company.workflow_scratch = scratch
        return f"I don't have '{stripped}' on file as a dealer. Add them as a new dealer? yes/no"

    if step == "awaiting_new_dealer_confirm":
        if _is(stripped, "no", "n"):
            company.active_workflow = None
            company.workflow_scratch = None
            return "OK, cancelled."
        if not _is(stripped, "yes", "y"):
            return "Please reply yes or no."
        scratch["items"] = []
        scratch["step"] = "awaiting_product"
        company.workflow_scratch = scratch
        return f"Got it, {scratch['dealer_name']} will be added as a new dealer. What product?"

    if step == "awaiting_product":
        if _is(stripped, "done"):
            if not scratch.get("items"):
                return "Add at least one product first, or 'cancel'."
            preview, payload = _preview_and_finalize(scratch, company.gst_rate)
            await create_pending_operation(db, company, PendingOperationType.create_order, payload)
            company.active_workflow = None
            company.workflow_scratch = None
            return preview
        if not stripped:
            return "Please tell me the product name, or 'done' if you're finished."
        product = await _match_product(db, company.id, stripped)
        if product is not None and product.selling_price is not None:
            scratch["current_product"] = {
                "name": product.name,
                "price": str(product.selling_price),
                "gst_rate": str(product.gst_rate) if product.gst_rate is not None else None,
            }
            scratch["step"] = "awaiting_quantity"
            company.workflow_scratch = scratch
            unit = product.unit or "units"
            return f"How many {unit} of {product.name}?"
        if product is not None:
            # On file but no price recorded yet (common for products the
            # guided onboarding conversation created with a name only).
            scratch["current_product"] = {
                "name": product.name,
                "price": None,
                "gst_rate": str(product.gst_rate) if product.gst_rate is not None else None,
            }
            scratch["step"] = "awaiting_price"
            company.workflow_scratch = scratch
            return f"What's the selling price for {product.name}?"
        scratch["current_product"] = {"name": stripped, "price": None}
        scratch["step"] = "awaiting_new_product_confirm"
        company.workflow_scratch = scratch
        return f"I don't have '{stripped}' in your catalogue. Add it? yes/no"

    if step == "awaiting_new_product_confirm":
        if _is(stripped, "no", "n"):
            scratch["current_product"] = None
            scratch["step"] = "awaiting_product"
            company.workflow_scratch = scratch
            return "OK. What product? (or 'done')"
        if not _is(stripped, "yes", "y"):
            return "Please reply yes or no."
        scratch["step"] = "awaiting_price"
        company.workflow_scratch = scratch
        name = scratch["current_product"]["name"]
        return f"What's the selling price for {name}?"

    if step == "awaiting_price":
        try:
            price = parse_amount(stripped)
        except ValueError:
            return "Please send a price, e.g. 55."
        if price <= 0:
            return "Please send a price greater than zero."
        current = dict(scratch["current_product"])
        current["price"] = str(price)
        scratch["current_product"] = current
        scratch["step"] = "awaiting_quantity"
        company.workflow_scratch = scratch
        return f"How many units of {current['name']}?"

    if step == "awaiting_quantity":
        try:
            quantity = parse_amount(stripped)
        except ValueError:
            return "Please send a quantity, e.g. 10."
        if quantity <= 0:
            return "Please send a quantity greater than zero."
        current = scratch["current_product"]
        items = list(scratch.get("items", []))
        items.append(
            {
                "product_name": current["name"],
                "quantity": str(quantity),
                "price": current.get("price"),
                "gst_rate": current.get("gst_rate"),
            }
        )
        scratch["items"] = items
        scratch["current_product"] = None
        scratch["step"] = "awaiting_product"
        company.workflow_scratch = scratch
        return f"Added {quantity} x {current['name']}. Add another product, or reply 'done'."

    # Unreachable in practice (every step above is exhaustive for this flow),
    # but never leave a company stuck on a workflow step this code can't run.
    company.active_workflow = None
    company.workflow_scratch = None
    return "Something went wrong with that. Please start again by saying 'new order'."
