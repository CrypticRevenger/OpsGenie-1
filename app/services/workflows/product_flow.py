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

from app.i18n import Locale, resolve_locale, t
from app.models.company import Company
from app.models.product import Product
from app.services.gst import parse_gst_rate
from app.services.importer.normalizer import parse_amount
from app.services.money_format import format_inr
from app.services.onboarding_flow import (
    _classify_entry_mode,
    _describe_product,
    _format_quantity,
    _is,
    _parse_bulk_line,
)


def start_add_product_workflow(company: Company) -> str:
    """Sets active_workflow + the first step's scratch and returns the
    opening question verbatim — called by the webhook's keyword-match branch,
    same contract as start_payment_workflow/start_order_workflow.
    """
    company.active_workflow = "add_product"
    company.workflow_scratch = {"step": "awaiting_mode"}
    return t("product.mode_prompt", resolve_locale(company))


def _finalize_add_product(
    db: AsyncSession,
    company: Company,
    scratch: dict,
    purchase_price: Decimal | None,
    gst_rate: Decimal | None,
    loc: Locale,
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
    stock = f"{_format_quantity(quantity)}{unit_suffix}"
    return t("onboarding.product.added", loc, name=name, stock=stock)


async def handle_add_product_workflow_message(db: AsyncSession, company: Company, text: str) -> str:
    """Advance the guided add-product flow by one message. Only mutates
    state/rows — the caller (the webhook) commits.
    """
    stripped = text.strip()
    loc = resolve_locale(company)

    if _is(stripped, "cancel", "stop"):
        company.active_workflow = None
        company.workflow_scratch = None
        return t("workflow.cancelled", loc)

    scratch = dict(company.workflow_scratch or {})
    step = scratch.get("step")

    if step == "awaiting_mode":
        if _is(stripped, "done", "skip"):
            company.active_workflow = None
            company.workflow_scratch = None
            return t("product.no_products_added", loc)
        mode = _classify_entry_mode(stripped)
        if mode == "bulk":
            scratch["step"] = "awaiting_bulk"
            company.workflow_scratch = scratch
            return t("onboarding.product.bulk_format", loc)
        if mode == "one_by_one":
            scratch["step"] = "awaiting_name"
            company.workflow_scratch = scratch
            return t("product.name_or_done", loc)
        return t("product.mode_invalid", loc)

    if step == "awaiting_bulk":
        if _is(stripped, "done", "skip"):
            company.active_workflow = None
            company.workflow_scratch = None
            return t("product.all_done", loc)
        lines = [line for line in stripped.splitlines() if line.strip()]
        if not lines:
            return t("onboarding.product.bulk_format", loc)
        parsed_items = []
        for line in lines:
            try:
                parsed_items.append(_parse_bulk_line(line))
            except ValueError as exc:
                return (
                    t("onboarding.bulk_error", loc, error=exc)
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
        return t("onboarding.product.bulk_added", loc, count=len(parsed_items), names=names)

    if step == "awaiting_name":
        if _is(stripped, "done", "skip"):
            company.active_workflow = None
            company.workflow_scratch = None
            return t("product.all_done", loc)
        scratch["name"] = stripped
        scratch["step"] = "awaiting_quantity"
        company.workflow_scratch = scratch
        return t("onboarding.product.quantity_ask", loc, name=stripped)

    if step == "awaiting_quantity":
        quantity = Decimal("0")
        if not _is(stripped, "skip"):
            try:
                quantity = parse_amount(stripped)
            except ValueError:
                return t("onboarding.product.quantity_invalid", loc)
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
        return t("onboarding.product.price_ask", loc, name=name)

    if step == "awaiting_price":
        price = None
        if not _is(stripped, "skip"):
            try:
                price = parse_amount(stripped)
            except ValueError:
                return t("onboarding.product.price_invalid", loc)
        scratch["price"] = str(price) if price is not None else None
        scratch["step"] = "awaiting_purchase_price"
        company.workflow_scratch = scratch
        name = scratch.get("name", "this product")
        return t("onboarding.product.purchase_ask", loc, name=name)

    if step == "awaiting_purchase_price":
        purchase_price = None
        if not _is(stripped, "skip", "done"):
            try:
                purchase_price = parse_amount(stripped)
            except ValueError:
                return t("onboarding.product.purchase_invalid", loc)
        if company.gst_varies_by_product:
            scratch["purchase_price"] = str(purchase_price) if purchase_price is not None else None
            scratch["step"] = "awaiting_gst_rate"
            company.workflow_scratch = scratch
            name = scratch.get("name", "this product")
            return t("onboarding.product.gst_ask", loc, name=name)
        return _finalize_add_product(db, company, scratch, purchase_price, None, loc)

    if step == "awaiting_gst_rate":
        gst_rate = None
        if not _is(stripped, "skip", "not sure", "done"):
            try:
                gst_rate = parse_gst_rate(stripped)
            except ValueError:
                return t("onboarding.product.gst_invalid", loc)
        purchase_price_raw = scratch.get("purchase_price")
        purchase_price = Decimal(purchase_price_raw) if purchase_price_raw is not None else None
        return _finalize_add_product(db, company, scratch, purchase_price, gst_rate, loc)

    # Unreachable in practice (every step above is exhaustive for this flow),
    # but never leave a company stuck in an unknown workflow step.
    company.active_workflow = None
    company.workflow_scratch = None
    return t("workflow.error_restart", loc, trigger="add product")


# ── Delete product ───────────────────────────────────────────────────────────


def _describe_candidate(product: Product, loc: Locale) -> str:
    unit_suffix = f" {product.unit}" if product.unit else ""
    stock = f"{_format_quantity(product.stock_quantity)}{unit_suffix}"
    bits = [t("product.candidate_stock", loc, stock=stock)]
    if product.selling_price is not None:
        bits.append(format_inr(product.selling_price))
    return t("product.candidate_desc", loc, name=product.name, details=", ".join(bits))


def _candidate_listing(matches: list[Product], loc: Locale) -> str:
    return "\n".join(
        t("product.candidate_line", loc, index=i, description=_describe_candidate(p, loc))
        for i, p in enumerate(matches, start=1)
    )


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
    return t("product.delete_name_prompt", resolve_locale(company))


async def handle_delete_product_workflow_message(
    db: AsyncSession, company: Company, text: str
) -> str:
    """Advance the guided delete-product flow by one message. Only mutates
    state/rows — the caller (the webhook) commits.
    """
    stripped = text.strip()
    loc = resolve_locale(company)

    if _is(stripped, "cancel", "stop"):
        company.active_workflow = None
        company.workflow_scratch = None
        return t("workflow.cancelled", loc)

    scratch = dict(company.workflow_scratch or {})
    step = scratch.get("step")

    if step == "awaiting_name":
        if not stripped:
            return t("product.delete_name_prompt", loc)
        matches = await _find_products_by_name(db, company.id, stripped)
        if not matches:
            return t("product.not_found_retry", loc, name=stripped)
        if len(matches) > 1:
            scratch["candidates"] = [str(p.id) for p in matches]
            scratch["step"] = "awaiting_disambiguation"
            company.workflow_scratch = scratch
            return t(
                "product.disambiguation",
                loc,
                count=len(matches),
                name=stripped,
                listing=_candidate_listing(matches, loc),
                action=t("product.action_delete", loc),
            )
        product = matches[0]
        scratch["product_id"] = str(product.id)
        scratch["product_name"] = product.name
        scratch["step"] = "awaiting_confirm"
        company.workflow_scratch = scratch
        return t("product.delete_confirm", loc, description=_describe_candidate(product, loc))

    if step == "awaiting_disambiguation":
        candidates = scratch.get("candidates", [])
        try:
            index = int(stripped)
        except ValueError:
            index = -1
        if not (1 <= index <= len(candidates)):
            return t("product.disambiguation_invalid", loc, count=len(candidates))
        product = await db.get(Product, uuid.UUID(candidates[index - 1]))
        if product is None:
            # Deleted/moved between listing and choosing (shouldn't happen) —
            # never leave the company stuck on a stale candidate list.
            company.active_workflow = None
            company.workflow_scratch = None
            return t("product.gone", loc, trigger="delete product")
        scratch["product_id"] = str(product.id)
        scratch["product_name"] = product.name
        scratch["step"] = "awaiting_confirm"
        company.workflow_scratch = scratch
        return t("product.delete_confirm", loc, description=_describe_candidate(product, loc))

    if step == "awaiting_confirm":
        if _is(stripped, "no", "n"):
            company.active_workflow = None
            company.workflow_scratch = None
            return t("product.delete_no", loc)
        if not _is(stripped, "yes", "y"):
            return t("product.delete_confirm_invalid", loc)
        product = await db.get(Product, uuid.UUID(scratch["product_id"]))
        name = scratch.get("product_name", "that product")
        company.active_workflow = None
        company.workflow_scratch = None
        if product is None:
            return t("product.delete_already_gone", loc, name=name)
        await db.delete(product)
        return t("product.deleted", loc, name=name)

    # Unreachable in practice (every step above is exhaustive for this flow),
    # but never leave a company stuck in an unknown workflow step.
    company.active_workflow = None
    company.workflow_scratch = None
    return t("workflow.error_restart", loc, trigger="delete product")


# ── Update product (selling price, purchase price, or stock) ────────────────
#
# One workflow, one "field" (price|purchase_price|stock) picked either up
# front (generic "update product" trigger) or implied by the specific
# trigger the user said ("update price" / "update purchase price" /
# "update stock") — same shape as onboarding routing a bare "1" differently
# depending on which question is currently active.

_FIELD_LABEL_KEYS = {
    "price": "product.label_price",
    "purchase_price": "product.label_purchase",
    "stock": "product.label_stock",
}


def _field_label(field: str, loc: Locale) -> str:
    return t(_FIELD_LABEL_KEYS.get(field, "product.label_price"), loc)


def _name_prompt(field: str, loc: Locale) -> str:
    return t("product.update_name_prompt", loc, label=_field_label(field, loc))


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
    return t("product.field_prompt", resolve_locale(company))


def start_update_price_workflow(company: Company) -> str:
    """Direct entry point ("update price") — field is already known."""
    company.active_workflow = "update_product"
    company.workflow_scratch = {"step": "awaiting_name", "field": "price"}
    return _name_prompt("price", resolve_locale(company))


def start_update_purchase_price_workflow(company: Company) -> str:
    """Direct entry point ("update purchase price") — field is already known."""
    company.active_workflow = "update_product"
    company.workflow_scratch = {"step": "awaiting_name", "field": "purchase_price"}
    return _name_prompt("purchase_price", resolve_locale(company))


def start_update_stock_workflow(company: Company) -> str:
    """Direct entry point ("update stock") — field is already known."""
    company.active_workflow = "update_product"
    company.workflow_scratch = {"step": "awaiting_name", "field": "stock"}
    return _name_prompt("stock", resolve_locale(company))


def _current_value_prompt(product: Product, field: str, loc: Locale) -> str:
    not_set = t("product.not_set", loc)
    if field == "price":
        current = (
            format_inr(product.selling_price) if product.selling_price is not None else not_set
        )
        return t("product.current_price", loc, name=product.name, current=current)
    if field == "purchase_price":
        current = (
            format_inr(product.purchase_price) if product.purchase_price is not None else not_set
        )
        return t("product.current_purchase", loc, name=product.name, current=current)
    unit_suffix = f" {product.unit}" if product.unit else ""
    current = f"{_format_quantity(product.stock_quantity)}{unit_suffix}"
    return t("product.current_stock", loc, name=product.name, current=current)


async def handle_update_product_workflow_message(
    db: AsyncSession, company: Company, text: str
) -> str:
    """Advance the guided update-product flow by one message. Only mutates
    state/rows — the caller (the webhook) commits.
    """
    stripped = text.strip()
    loc = resolve_locale(company)

    if _is(stripped, "cancel", "stop"):
        company.active_workflow = None
        company.workflow_scratch = None
        return t("workflow.cancelled", loc)

    scratch = dict(company.workflow_scratch or {})
    step = scratch.get("step")
    field = scratch.get("field", "price")

    if step == "awaiting_field":
        chosen = _classify_update_field(stripped)
        if chosen is None:
            return t("product.field_prompt", loc)
        scratch["field"] = chosen
        scratch["step"] = "awaiting_name"
        company.workflow_scratch = scratch
        return _name_prompt(chosen, loc)

    if step == "awaiting_name":
        if not stripped:
            return _name_prompt(field, loc)
        matches = await _find_products_by_name(db, company.id, stripped)
        if not matches:
            return t("product.not_found_retry", loc, name=stripped)
        if len(matches) > 1:
            scratch["candidates"] = [str(p.id) for p in matches]
            scratch["step"] = "awaiting_disambiguation"
            company.workflow_scratch = scratch
            return t(
                "product.disambiguation",
                loc,
                count=len(matches),
                name=stripped,
                listing=_candidate_listing(matches, loc),
                action=t("product.action_update", loc),
            )
        product = matches[0]
        scratch["product_id"] = str(product.id)
        scratch["step"] = "awaiting_value"
        company.workflow_scratch = scratch
        return _current_value_prompt(product, field, loc)

    if step == "awaiting_disambiguation":
        candidates = scratch.get("candidates", [])
        try:
            index = int(stripped)
        except ValueError:
            index = -1
        if not (1 <= index <= len(candidates)):
            return t("product.disambiguation_invalid", loc, count=len(candidates))
        product = await db.get(Product, uuid.UUID(candidates[index - 1]))
        if product is None:
            # Deleted/moved between listing and choosing (shouldn't happen) —
            # never leave the company stuck on a stale candidate list.
            company.active_workflow = None
            company.workflow_scratch = None
            return t("product.gone", loc, trigger="update product")
        scratch["product_id"] = str(product.id)
        scratch["step"] = "awaiting_value"
        company.workflow_scratch = scratch
        return _current_value_prompt(product, field, loc)

    if step == "awaiting_value":
        try:
            value = parse_amount(stripped)
        except ValueError:
            return t("product.value_invalid", loc)
        if value < 0:
            return t("product.value_nonneg", loc)
        product = await db.get(Product, uuid.UUID(scratch["product_id"]))
        company.active_workflow = None
        company.workflow_scratch = None
        if product is None:
            return t("product.gone_value", loc)
        not_set = t("product.not_set", loc)
        if field == "price":
            old = (
                format_inr(product.selling_price) if product.selling_price is not None else not_set
            )
            product.selling_price = value
            return t(
                "product.updated_price", loc, name=product.name, new=format_inr(value), old=old
            )
        if field == "purchase_price":
            old = (
                format_inr(product.purchase_price)
                if product.purchase_price is not None
                else not_set
            )
            product.purchase_price = value
            return t(
                "product.updated_purchase", loc, name=product.name, new=format_inr(value), old=old
            )
        unit_suffix = f" {product.unit}" if product.unit else ""
        old = f"{_format_quantity(product.stock_quantity)}{unit_suffix}"
        product.stock_quantity = value
        new = f"{_format_quantity(value)}{unit_suffix}"
        return t("product.updated_stock", loc, name=product.name, new=new, old=old)

    # Unreachable in practice (every step above is exhaustive for this flow),
    # but never leave a company stuck in an unknown workflow step.
    company.active_workflow = None
    company.workflow_scratch = None
    return t("workflow.error_restart", loc, trigger="update product")
