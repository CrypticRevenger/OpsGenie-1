"""Guided "stock take" workflow — bulk stock recount/adjustment.

Extends the existing single-product update_stock flow
(app/services/workflows/product_flow.py) into a repeatable loop: product
name -> [disambiguate if needed] -> value -> loop, until 'done' -> optional
reason for the whole batch -> full summary -> inline YES/NO (not a
PendingOperation — same write-immediately-behind-a-confirm tier as
delete_product, since this is inventory counts, not a ledger figure).

Value parsing: a leading '+' or '-' means a delta against current stock
(e.g. '+15' found, '-3' damaged); a plain number means an absolute recount
(e.g. '40'), matching update_stock's existing overwrite semantics exactly.
Negative resulting stock is a flag, not a block — same convention
order_flow.py's negative_stock_warnings already uses.
"""

from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation

from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import resolve_locale, t
from app.models.company import Company
from app.models.product import Product
from app.services.importer.normalizer import parse_amount
from app.services.onboarding_flow import _format_quantity, _is
from app.services.workflows.product_flow import _candidate_listing, _find_products_by_name
from app.services.writes.stock_take import apply_stock_take


def start_stock_take_workflow(company: Company) -> str:
    company.active_workflow = "stock_take"
    company.workflow_scratch = {"step": "awaiting_line", "adjustments": []}
    return t("stock_take.start_prompt", resolve_locale(company))


def _parse_line_value(text: str) -> tuple[str, Decimal] | None:
    """Returns (mode, value) or None if unparseable. A leading '+'/'-'
    means a signed delta (kept as a plain Decimal, sign intact); anything
    else is an absolute recount via parse_amount."""
    stripped = text.strip()
    if stripped[:1] in ("+", "-"):
        try:
            return "delta", Decimal(stripped)
        except InvalidOperation:
            return None
    try:
        return "absolute", parse_amount(stripped)
    except ValueError:
        return None


def _line_summary(item: dict) -> str:
    return f"{item['product_name']}: {item['old_display']} → {item['new_display']}"


async def handle_stock_take_workflow_message(db: AsyncSession, company: Company, text: str) -> str:
    stripped = text.strip()
    loc = resolve_locale(company)

    if _is(stripped, "cancel", "stop"):
        company.active_workflow = None
        company.workflow_scratch = None
        return t("workflow.cancelled", loc)

    scratch = dict(company.workflow_scratch or {})
    step = scratch.get("step")

    if step == "awaiting_line":
        if _is(stripped, "done"):
            if not scratch.get("adjustments"):
                company.active_workflow = None
                company.workflow_scratch = None
                return t("stock_take.nothing_to_apply", loc)
            scratch["step"] = "awaiting_reason"
            company.workflow_scratch = scratch
            return t("stock_take.reason_ask", loc)
        if not stripped:
            return t("stock_take.line_prompt", loc)
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
        scratch["pending_product_id"] = str(product.id)
        scratch["pending_product_name"] = product.name
        scratch["step"] = "awaiting_value"
        company.workflow_scratch = scratch
        return t("stock_take.value_ask", loc, name=product.name)

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
            company.active_workflow = None
            company.workflow_scratch = None
            return t("product.gone", loc, trigger="stock take")
        scratch["pending_product_id"] = str(product.id)
        scratch["pending_product_name"] = product.name
        scratch["step"] = "awaiting_value"
        company.workflow_scratch = scratch
        return t("stock_take.value_ask", loc, name=product.name)

    if step == "awaiting_value":
        product = await db.get(Product, uuid.UUID(scratch["pending_product_id"]))
        if product is None:
            company.active_workflow = None
            company.workflow_scratch = None
            return t("product.gone_value", loc)
        parsed = _parse_line_value(stripped)
        if parsed is None:
            return t("stock_take.value_invalid", loc)
        mode, value = parsed
        old_quantity = product.stock_quantity
        new_quantity = old_quantity + value if mode == "delta" else value
        unit_suffix = f" {product.unit}" if product.unit else ""
        old_display = f"{_format_quantity(old_quantity)}{unit_suffix}"
        new_display = f"{_format_quantity(new_quantity)}{unit_suffix}"

        adjustments = list(scratch.get("adjustments", []))
        adjustments.append(
            {
                "product_id": scratch["pending_product_id"],
                "product_name": product.name,
                "mode": mode,
                "value": str(value),
                "old_display": old_display,
                "new_display": new_display,
            }
        )
        scratch = {"step": "awaiting_line", "adjustments": adjustments}
        company.workflow_scratch = scratch
        return t(
            "stock_take.line_added",
            loc,
            name=product.name,
            old=old_display,
            new=new_display,
        )

    if step == "awaiting_reason":
        reason = None if (not stripped or _is(stripped, "skip")) else stripped
        adjustments = scratch.get("adjustments", [])
        summary = "\n".join(_line_summary(item) for item in adjustments)
        scratch = {"step": "awaiting_confirm", "adjustments": adjustments, "reason": reason}
        company.workflow_scratch = scratch
        return t("stock_take.confirm_prompt", loc, summary=summary)

    if step == "awaiting_confirm":
        if _is(stripped, "no", "n"):
            company.active_workflow = None
            company.workflow_scratch = None
            return t("workflow.cancelled", loc)
        if not _is(stripped, "yes", "y"):
            return t("pending.reply_yes_no", loc)

        adjustments = scratch.get("adjustments", [])
        reason = scratch.get("reason")
        company.active_workflow = None
        company.workflow_scratch = None
        try:
            # SAVEPOINT so a mid-batch failure really does discard the whole
            # batch. apply_stock_take mutates each product and adds its audit
            # event as it loops, then raises if a later product turns out to be
            # gone — and the webhook commits unconditionally at the end of the
            # request, so without this the already-processed products stayed
            # committed while the reply below said the stock take failed.
            # That contradicted apply_stock_take's own docstring ("rather than
            # committing a partial batch silently").
            async with db.begin_nested():
                results = await apply_stock_take(
                    db, company, adjustments=adjustments, reason=reason
                )
        except ValueError as exc:
            return t("stock_take.failed", loc, error=exc)

        warnings = [r.product_name for r in results if r.new_quantity < 0]
        warning_text = (
            t("pending.order_stock_warning", loc, products=", ".join(warnings)) if warnings else ""
        )
        lines = "\n".join(
            t(
                "stock_take.result_line",
                loc,
                name=r.product_name,
                new=_format_quantity(r.new_quantity),
            )
            for r in results
        )
        return t("stock_take.success", loc, count=len(results), lines=lines, warning=warning_text)

    # Unreachable in practice (every step above is exhaustive for this flow),
    # but never leave a company stuck on a workflow step this code can't run.
    company.active_workflow = None
    company.workflow_scratch = None
    return t("workflow.error_restart", loc, trigger="stock take")
