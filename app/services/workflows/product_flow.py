"""Guided add-product workflow — lets an already-onboarded company add more
products later, any time, using the exact same one-by-one/bulk process as
onboarding's product step (app/services/onboarding_flow.py). Same
state-machine shape as app/services/workflows/payment_flow.py: state lives in
Company.active_workflow + Company.workflow_scratch, mutated in place, never
committed here — the webhook commits once.

Reuses onboarding_flow's mode classifier, bulk parser, and formatting helpers
rather than re-implementing them, so "add product" behaves identically to the
onboarding product step (including the bulk price-list parsing).
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.product import Product
from app.services.importer.normalizer import parse_amount
from app.services.onboarding_flow import (
    _classify_product_mode,
    _describe_product,
    _format_quantity,
    _is,
    _parse_bulk_products,
)

_MODE_PROMPT = (
    "Let's add products. Reply 'one by one' to add them individually, "
    "or 'bulk' to send them all at once with prices (e.g. Rice - 400, Dal - 450). "
    "Reply 'done' to stop anytime."
)


def start_add_product_workflow(company: Company) -> str:
    """Sets active_workflow + the first step's scratch and returns the
    opening question verbatim — called by the webhook's keyword-match branch,
    same contract as start_payment_workflow/start_order_workflow.
    """
    company.active_workflow = "add_product"
    company.workflow_scratch = {"step": "awaiting_mode"}
    return _MODE_PROMPT


async def handle_add_product_workflow_message(db: AsyncSession, company: Company, text: str) -> str:
    """Advance the guided add-product flow by one message. Only mutates
    state/rows — the caller (the webhook) commits.
    """
    stripped = text.strip()

    if _is(stripped, "cancel", "stop"):
        company.active_workflow = None
        company.workflow_scratch = None
        return "OK, cancelled."

    scratch = dict(company.workflow_scratch or {})
    step = scratch.get("step")

    if step == "awaiting_mode":
        if _is(stripped, "done", "skip"):
            company.active_workflow = None
            company.workflow_scratch = None
            return "OK, no products added."
        mode = _classify_product_mode(stripped)
        if mode == "bulk":
            scratch["step"] = "awaiting_bulk"
            company.workflow_scratch = scratch
            return (
                "Send your products now — one per line or comma-separated, with an "
                "optional price (e.g. Rice - 400, Dal - 450). Reply 'done' when finished."
            )
        if mode == "one_by_one":
            scratch["step"] = "awaiting_name"
            company.workflow_scratch = scratch
            return "Send the product's name (e.g. Rice), or 'done' to stop."
        return "Please reply 'one by one' or 'bulk' — or 'done' to stop."

    if step == "awaiting_bulk":
        if _is(stripped, "done", "skip"):
            company.active_workflow = None
            company.workflow_scratch = None
            return "All done adding products."
        parsed = _parse_bulk_products(stripped)
        if not parsed:
            return (
                "I couldn't find any products in that message. List them one per line or "
                "comma-separated, with an optional price (e.g. Rice - 400, Dal - 450)."
            )
        for name, price in parsed:
            db.add(Product(company_id=company.id, name=name, selling_price=price))
        names = ", ".join(_describe_product(name, price) for name, price in parsed)
        return (
            f"Added {len(parsed)} product(s): {names}. Send more, or reply 'done' when finished."
        )

    if step == "awaiting_name":
        if _is(stripped, "done", "skip"):
            company.active_workflow = None
            company.workflow_scratch = None
            return "All done adding products."
        scratch["name"] = stripped
        scratch["step"] = "awaiting_quantity"
        company.workflow_scratch = scratch
        return f"How much {stripped} do you have in stock right now? (e.g. 100, or 'skip')"

    if step == "awaiting_quantity":
        quantity = Decimal("0")
        if not _is(stripped, "skip"):
            try:
                quantity = parse_amount(stripped)
            except ValueError:
                return "Please send a number, e.g. 100 (or 'skip')."
        name = scratch.get("name", "Product")
        db.add(Product(company_id=company.id, name=name, stock_quantity=quantity))
        company.workflow_scratch = {"step": "awaiting_name"}
        return (
            f"Added product: {name} ({_format_quantity(quantity)} in stock). "
            "Send another, or 'done'."
        )

    # Unreachable in practice (every step above is exhaustive for this flow),
    # but never leave a company stuck in an unknown workflow step.
    company.active_workflow = None
    company.workflow_scratch = None
    return "Something went wrong with that. Please start again by saying 'add product'."
