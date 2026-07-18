"""Guided add-product / delete-product workflows — let an already-onboarded
company manage its catalogue any time, using the exact same one-by-one/bulk
process as onboarding's product step (app/services/onboarding_flow.py). Same
state-machine shape as app/services/workflows/payment_flow.py: state lives in
Company.active_workflow + Company.workflow_scratch, mutated in place, never
committed here — the webhook commits once.

Reuses onboarding_flow's mode classifier, bulk parser, and formatting helpers
rather than re-implementing them, so "add product" behaves identically to the
onboarding product step (including the bulk price-list parsing).

Deletion always confirms with YES/NO before committing — same
never-silently-destructive spirit as the admin dashboard's delete buttons
(each behind a JS confirm()) and the PendingOperation gate on money writes.
Products can share a name (no unique constraint), so a name match that finds
more than one candidate is disambiguated by number before the confirm step,
rather than guessing or deleting every match.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import resolve_locale, t
from app.models.company import Company
from app.models.product import Product
from app.services.gst import parse_gst_rate
from app.services.importer.normalizer import parse_amount
from app.services.money_format import format_inr
from app.services.onboarding_flow import (
    _classify_product_mode,
    _describe_product,
    _format_quantity,
    _is,
    _parse_bulk_line,
)

_MODE_PROMPT = (
    "Let's add products. Reply 'one by one' to add them individually, "
    "or 'bulk' to send them all at once with full details "
    "(e.g. Rice, 300, 400, kg, 100, 5). Reply 'done' to stop anytime."
)


def start_add_product_workflow(company: Company) -> str:
    """Sets active_workflow + the first step's scratch and returns the
    opening question verbatim — called by the webhook's keyword-match branch,
    same contract as start_payment_workflow/start_order_workflow.
    """
    company.active_workflow = "add_product"
    company.workflow_scratch = {"step": "awaiting_mode"}
    return _MODE_PROMPT


def _finalize_add_product(
    db: AsyncSession,
    company: Company,
    scratch: dict,
    purchase_price: Decimal | None,
    gst_rate: Decimal | None,
) -> str:
    """Creates the Product row from the one-by-one loop's accumulated
    scratch fields — reached either directly after purchase price
    (gst_varies_by_product False) or after the extra GST question (True).
    """
    name = scratch.get("name", "Product")
    quantity = Decimal(scratch.get("quantity", "0"))
    unit = scratch.get("unit")
    price_raw = scratch.get("price")
    price = Decimal(price_raw) if price_raw is not None else None
    db.add(
        Product(
            company_id=company.id,
            name=name,
            stock_quantity=quantity,
            unit=unit,
            selling_price=price,
            purchase_price=purchase_price,
            gst_rate=gst_rate,
        )
    )
    company.workflow_scratch = {"step": "awaiting_name"}
    unit_suffix = f" {unit}" if unit else ""
    return (
        f"Added product: {name} ({_format_quantity(quantity)}{unit_suffix} in stock). "
        "Send another, or 'done'."
    )


async def handle_add_product_workflow_message(db: AsyncSession, company: Company, text: str) -> str:
    """Advance the guided add-product flow by one message. Only mutates
    state/rows — the caller (the webhook) commits.
    """
    stripped = text.strip()
    loc = resolve_locale(company)

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
            return t("onboarding.product.bulk_format", loc)
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
        lines = [line for line in stripped.splitlines() if line.strip()]
        if not lines:
            return t("onboarding.product.bulk_format", loc)
        parsed_items = []
        for line in lines:
            try:
                parsed_items.append(_parse_bulk_line(line))
            except ValueError as exc:
                return (
                    t("onboarding.product.bulk_error", loc, error=exc)
                    + "\n\n"
                    + t("onboarding.product.bulk_format", loc)
                )
        for item in parsed_items:
            db.add(
                Product(
                    company_id=company.id,
                    name=item["name"],
                    stock_quantity=item["stock"],
                    unit=item["unit"],
                    selling_price=item["selling_price"],
                    purchase_price=item["purchase_price"],
                    gst_rate=item["gst_rate"],
                )
            )
        names = ", ".join(
            _describe_product(item["name"], item["selling_price"], item["unit"])
            for item in parsed_items
        )
        return (
            f"Added {len(parsed_items)} product(s): {names}. "
            "Send more, or reply 'done' when finished."
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
        scratch["quantity"] = str(quantity)
        scratch["step"] = "awaiting_unit"
        company.workflow_scratch = scratch
        return t("onboarding.product.unit", loc)

    if step == "awaiting_unit":
        unit = None if _is(stripped, "skip") else stripped
        scratch["unit"] = unit
        scratch["step"] = "awaiting_price"
        company.workflow_scratch = scratch
        name = scratch.get("name", "this product")
        return f"What's the selling price for {name}? (e.g. 400, or 'skip')"

    if step == "awaiting_price":
        price = None
        if not _is(stripped, "skip"):
            try:
                price = parse_amount(stripped)
            except ValueError:
                return "Please send a number, e.g. 400 (or 'skip')."
        scratch["price"] = str(price) if price is not None else None
        scratch["step"] = "awaiting_purchase_price"
        company.workflow_scratch = scratch
        name = scratch.get("name", "this product")
        return f"What's the purchase price (cost price) for {name}? (e.g. 300, or 'skip')"

    if step == "awaiting_purchase_price":
        purchase_price = None
        if not _is(stripped, "skip", "done"):
            try:
                purchase_price = parse_amount(stripped)
            except ValueError:
                return "Please send a number, e.g. 300 (or 'skip')."
        if company.gst_varies_by_product:
            scratch["purchase_price"] = str(purchase_price) if purchase_price is not None else None
            scratch["step"] = "awaiting_gst_rate"
            company.workflow_scratch = scratch
            name = scratch.get("name", "this product")
            return f"What's the GST% for {name}? (e.g. 5, 12, 18, or 'skip' to decide later)"
        return _finalize_add_product(db, company, scratch, purchase_price, None)

    if step == "awaiting_gst_rate":
        gst_rate = None
        if not _is(stripped, "skip", "not sure", "done"):
            try:
                gst_rate = parse_gst_rate(stripped)
            except ValueError:
                return (
                    "Please send a number between 0 and 100, e.g. 18 "
                    "(or 'skip' to decide later)."
                )
        purchase_price_raw = scratch.get("purchase_price")
        purchase_price = Decimal(purchase_price_raw) if purchase_price_raw is not None else None
        return _finalize_add_product(db, company, scratch, purchase_price, gst_rate)

    # Unreachable in practice (every step above is exhaustive for this flow),
    # but never leave a company stuck in an unknown workflow step.
    company.active_workflow = None
    company.workflow_scratch = None
    return "Something went wrong with that. Please start again by saying 'add product'."


# ── Delete product ───────────────────────────────────────────────────────────

_DELETE_NAME_PROMPT = "Which product do you want to delete? Send its name, or 'cancel'."


def _describe_candidate(product: Product) -> str:
    unit_suffix = f" {product.unit}" if product.unit else ""
    stock = f"{_format_quantity(product.stock_quantity)}{unit_suffix}"
    bits = [f"{stock} in stock"]
    if product.selling_price is not None:
        bits.append(format_inr(product.selling_price))
    return f"{product.name} ({', '.join(bits)})"


async def _find_products_by_name(
    db: AsyncSession, company_id: uuid.UUID, name: str
) -> list[Product]:
    result = await db.scalars(
        select(Product).where(
            Product.company_id == company_id, func.lower(Product.name) == name.lower()
        )
    )
    return list(result.all())


def start_delete_product_workflow(company: Company) -> str:
    """Sets active_workflow + the first step's scratch and returns the
    opening question verbatim — same contract as start_add_product_workflow.
    """
    company.active_workflow = "delete_product"
    company.workflow_scratch = {"step": "awaiting_name"}
    return _DELETE_NAME_PROMPT


async def handle_delete_product_workflow_message(
    db: AsyncSession, company: Company, text: str
) -> str:
    """Advance the guided delete-product flow by one message. Only mutates
    state/rows — the caller (the webhook) commits.
    """
    stripped = text.strip()

    if _is(stripped, "cancel", "stop"):
        company.active_workflow = None
        company.workflow_scratch = None
        return "OK, cancelled."

    scratch = dict(company.workflow_scratch or {})
    step = scratch.get("step")

    if step == "awaiting_name":
        if not stripped:
            return _DELETE_NAME_PROMPT
        matches = await _find_products_by_name(db, company.id, stripped)
        if not matches:
            return (
                f"I couldn't find a product named '{stripped}'. Check the spelling and "
                "try again, or reply 'cancel'."
            )
        if len(matches) > 1:
            scratch["candidates"] = [str(p.id) for p in matches]
            scratch["step"] = "awaiting_disambiguation"
            company.workflow_scratch = scratch
            listing = "\n".join(
                f"{i}. {_describe_candidate(p)}" for i, p in enumerate(matches, start=1)
            )
            return (
                f"Found {len(matches)} products named '{stripped}':\n{listing}\n"
                "Reply with the number to delete, or 'cancel'."
            )
        product = matches[0]
        scratch["product_id"] = str(product.id)
        scratch["product_name"] = product.name
        scratch["step"] = "awaiting_confirm"
        company.workflow_scratch = scratch
        return (
            f"Delete {_describe_candidate(product)}? This can't be undone. "
            "Reply YES to delete, NO to cancel."
        )

    if step == "awaiting_disambiguation":
        candidates = scratch.get("candidates", [])
        try:
            index = int(stripped)
        except ValueError:
            index = -1
        if not (1 <= index <= len(candidates)):
            return f"Please reply with a number from 1 to {len(candidates)}, or 'cancel'."
        product = await db.get(Product, uuid.UUID(candidates[index - 1]))
        if product is None:
            # Deleted/moved between listing and choosing (shouldn't happen) —
            # never leave the company stuck on a stale candidate list.
            company.active_workflow = None
            company.workflow_scratch = None
            return (
                "That product is no longer available. Please start again by saying "
                "'delete product'."
            )
        scratch["product_id"] = str(product.id)
        scratch["product_name"] = product.name
        scratch["step"] = "awaiting_confirm"
        company.workflow_scratch = scratch
        return (
            f"Delete {_describe_candidate(product)}? This can't be undone. "
            "Reply YES to delete, NO to cancel."
        )

    if step == "awaiting_confirm":
        if _is(stripped, "no", "n"):
            company.active_workflow = None
            company.workflow_scratch = None
            return "OK, not deleted."
        if not _is(stripped, "yes", "y"):
            return "Please reply YES to delete, or NO to cancel."
        product = await db.get(Product, uuid.UUID(scratch["product_id"]))
        name = scratch.get("product_name", "that product")
        company.active_workflow = None
        company.workflow_scratch = None
        if product is None:
            return f"{name} was already removed."
        await db.delete(product)
        return f"Deleted {name}."

    # Unreachable in practice (every step above is exhaustive for this flow),
    # but never leave a company stuck in an unknown workflow step.
    company.active_workflow = None
    company.workflow_scratch = None
    return "Something went wrong with that. Please start again by saying 'delete product'."


# ── Update product (selling price, purchase price, or stock) ────────────────
#
# One workflow, one "field" (price|purchase_price|stock) picked either up
# front (generic "update product" trigger) or implied by the specific
# trigger the user said ("update price" / "update purchase price" /
# "update stock") — same shape as onboarding routing a bare "1" differently
# depending on which question is currently active.

_FIELD_PROMPT = (
    "What do you want to update — price, purchase price, or stock? "
    "Reply 'price', 'purchase price', or 'stock'."
)
_FIELD_LABELS = {"price": "price", "purchase_price": "purchase price", "stock": "stock"}


def _name_prompt(field: str) -> str:
    label = _FIELD_LABELS.get(field, field)
    return f"Which product's {label} do you want to update? Send its name, or 'cancel'."


def _classify_update_field(text: str) -> str | None:
    normalized = text.strip().lower()
    if normalized in ("price", "selling price", "prices"):
        return "price"
    if normalized in ("purchase price", "purchase", "cost price", "cost", "buying price"):
        return "purchase_price"
    if normalized in ("stock", "stock quantity", "quantity", "qty"):
        return "stock"
    return None


def start_update_product_workflow(company: Company) -> str:
    """Generic entry point ("update product") — asks which field first."""
    company.active_workflow = "update_product"
    company.workflow_scratch = {"step": "awaiting_field"}
    return _FIELD_PROMPT


def start_update_price_workflow(company: Company) -> str:
    """Direct entry point ("update price") — field is already known."""
    company.active_workflow = "update_product"
    company.workflow_scratch = {"step": "awaiting_name", "field": "price"}
    return _name_prompt("price")


def start_update_purchase_price_workflow(company: Company) -> str:
    """Direct entry point ("update purchase price") — field is already known."""
    company.active_workflow = "update_product"
    company.workflow_scratch = {"step": "awaiting_name", "field": "purchase_price"}
    return _name_prompt("purchase_price")


def start_update_stock_workflow(company: Company) -> str:
    """Direct entry point ("update stock") — field is already known."""
    company.active_workflow = "update_product"
    company.workflow_scratch = {"step": "awaiting_name", "field": "stock"}
    return _name_prompt("stock")


def _current_value_prompt(product: Product, field: str) -> str:
    if field == "price":
        current = (
            format_inr(product.selling_price) if product.selling_price is not None else "not set"
        )
        return (
            f"{product.name}'s current price is {current}. "
            "What should the new price be? (e.g. 450)"
        )
    if field == "purchase_price":
        current = (
            format_inr(product.purchase_price) if product.purchase_price is not None else "not set"
        )
        return (
            f"{product.name}'s current purchase price is {current}. "
            "What should the new purchase price be? (e.g. 300)"
        )
    unit_suffix = f" {product.unit}" if product.unit else ""
    current = f"{_format_quantity(product.stock_quantity)}{unit_suffix}"
    return f"{product.name}'s current stock is {current}. What should the new stock be? (e.g. 100)"


async def handle_update_product_workflow_message(
    db: AsyncSession, company: Company, text: str
) -> str:
    """Advance the guided update-product flow by one message. Only mutates
    state/rows — the caller (the webhook) commits.
    """
    stripped = text.strip()

    if _is(stripped, "cancel", "stop"):
        company.active_workflow = None
        company.workflow_scratch = None
        return "OK, cancelled."

    scratch = dict(company.workflow_scratch or {})
    step = scratch.get("step")
    field = scratch.get("field", "price")

    if step == "awaiting_field":
        chosen = _classify_update_field(stripped)
        if chosen is None:
            return _FIELD_PROMPT
        scratch["field"] = chosen
        scratch["step"] = "awaiting_name"
        company.workflow_scratch = scratch
        return _name_prompt(chosen)

    if step == "awaiting_name":
        if not stripped:
            return _name_prompt(field)
        matches = await _find_products_by_name(db, company.id, stripped)
        if not matches:
            return (
                f"I couldn't find a product named '{stripped}'. Check the spelling and "
                "try again, or reply 'cancel'."
            )
        if len(matches) > 1:
            scratch["candidates"] = [str(p.id) for p in matches]
            scratch["step"] = "awaiting_disambiguation"
            company.workflow_scratch = scratch
            listing = "\n".join(
                f"{i}. {_describe_candidate(p)}" for i, p in enumerate(matches, start=1)
            )
            return (
                f"Found {len(matches)} products named '{stripped}':\n{listing}\n"
                "Reply with the number to update, or 'cancel'."
            )
        product = matches[0]
        scratch["product_id"] = str(product.id)
        scratch["step"] = "awaiting_value"
        company.workflow_scratch = scratch
        return _current_value_prompt(product, field)

    if step == "awaiting_disambiguation":
        candidates = scratch.get("candidates", [])
        try:
            index = int(stripped)
        except ValueError:
            index = -1
        if not (1 <= index <= len(candidates)):
            return f"Please reply with a number from 1 to {len(candidates)}, or 'cancel'."
        product = await db.get(Product, uuid.UUID(candidates[index - 1]))
        if product is None:
            # Deleted/moved between listing and choosing (shouldn't happen) —
            # never leave the company stuck on a stale candidate list.
            company.active_workflow = None
            company.workflow_scratch = None
            return (
                "That product is no longer available. Please start again by saying "
                "'update product'."
            )
        scratch["product_id"] = str(product.id)
        scratch["step"] = "awaiting_value"
        company.workflow_scratch = scratch
        return _current_value_prompt(product, field)

    if step == "awaiting_value":
        try:
            value = parse_amount(stripped)
        except ValueError:
            return "Please send a number, e.g. 450."
        if value < 0:
            return "Please send a number of zero or more."
        product = await db.get(Product, uuid.UUID(scratch["product_id"]))
        company.active_workflow = None
        company.workflow_scratch = None
        if product is None:
            return "That product is no longer available."
        if field == "price":
            had_price = product.selling_price is not None
            old = format_inr(product.selling_price) if had_price else "not set"
            product.selling_price = value
            return f"Updated {product.name}'s price to {format_inr(value)} (was {old})."
        if field == "purchase_price":
            had_price = product.purchase_price is not None
            old = format_inr(product.purchase_price) if had_price else "not set"
            product.purchase_price = value
            return f"Updated {product.name}'s purchase price to {format_inr(value)} (was {old})."
        unit_suffix = f" {product.unit}" if product.unit else ""
        old = f"{_format_quantity(product.stock_quantity)}{unit_suffix}"
        product.stock_quantity = value
        new = f"{_format_quantity(value)}{unit_suffix}"
        return f"Updated {product.name}'s stock to {new} (was {old})."

    # Unreachable in practice (every step above is exhaustive for this flow),
    # but never leave a company stuck in an unknown workflow step.
    company.active_workflow = None
    company.workflow_scratch = None
    return "Something went wrong with that. Please start again by saying 'update product'."
