"""Guided "update gst" workflow — Phase 2C.

Scope? (all products / one product) -> [disambiguate if the product name
matches more than one row] -> rate -> preview -> PendingOperation -> YES/NO
(handled by app/services/writes/pending_operation.py, not here). Same
state-machine shape as app/services/workflows/order_flow.py: state lives in
Company.active_workflow ("update_gst") + Company.workflow_scratch, mutated in
place, never committed here.

Reuses product_flow.py's name-matching/disambiguation helpers rather than
re-implementing them, since product names aren't unique in this catalogue.

"cancel"/"stop" are recognized at every step, matching every other guided
workflow's universal exit.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import Locale, resolve_locale, t
from app.models.company import Company
from app.models.pending_operation import PendingOperationType
from app.models.product import Product
from app.services.gst import parse_gst_rate
from app.services.onboarding_flow import _is
from app.services.workflows.product_flow import _describe_candidate, _find_products_by_name
from app.services.writes.pending_operation import create_pending_operation

_CLEAR_WORDS = {"clear", "none", "remove", "unset"}


def start_update_gst_workflow(company: Company) -> str:
    """Sets active_workflow + the first step's scratch and returns the
    opening question verbatim — same contract as start_order_workflow.
    """
    company.active_workflow = "update_gst"
    company.workflow_scratch = {"step": "awaiting_scope"}
    return t("gst.scope_prompt", resolve_locale(company))


def _rate_prompt(scope: str, target: str, loc: Locale) -> str:
    key = "gst.rate_ask_all" if scope == "all" else "gst.rate_ask_product"
    return t(key, loc, target=target)


async def handle_update_gst_workflow_message(db: AsyncSession, company: Company, text: str) -> str:
    """Advance the guided update-gst flow by one message. Only mutates
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

    if step == "awaiting_scope":
        if _is(stripped, "all"):
            scratch = {"step": "awaiting_rate", "scope": "all"}
            company.workflow_scratch = scratch
            return _rate_prompt("all", t("gst.all_products", loc), loc)
        if not stripped:
            return t("gst.scope_prompt", loc)
        matches = await _find_products_by_name(db, company.id, stripped)
        if not matches:
            return t("gst.not_found", loc, name=stripped)
        if len(matches) > 1:
            scratch = {
                "step": "awaiting_disambiguation",
                "candidates": [str(p.id) for p in matches],
            }
            company.workflow_scratch = scratch
            listing = "\n".join(
                t("product.candidate_line", loc, index=i, description=_describe_candidate(p, loc))
                for i, p in enumerate(matches, start=1)
            )
            return t(
                "product.disambiguation",
                loc,
                count=len(matches),
                name=stripped,
                listing=listing,
                action=t("product.action_update", loc),
            )
        product = matches[0]
        scratch = {"step": "awaiting_rate", "scope": "product", "product_name": product.name}
        company.workflow_scratch = scratch
        return _rate_prompt("product", product.name, loc)

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
            return t("product.gone", loc, trigger="update gst")
        scratch = {"step": "awaiting_rate", "scope": "product", "product_name": product.name}
        company.workflow_scratch = scratch
        return _rate_prompt("product", product.name, loc)

    if step == "awaiting_rate":
        scope = scratch.get("scope", "all")
        product_name = scratch.get("product_name")
        target = t("gst.all_products", loc) if scope == "all" else product_name

        if scope == "product" and _is(stripped, *_CLEAR_WORDS):
            gst_rate = None
            rate_text = t("gst.no_override", loc)
        else:
            try:
                gst_rate = parse_gst_rate(stripped)
            except ValueError:
                return t("gst.rate_invalid", loc) + "\n\n" + _rate_prompt(scope, target, loc)
            rate_text = t("gst.rate_pct", loc, rate=gst_rate)

        payload = {
            "scope": scope,
            "gst_rate": str(gst_rate) if gst_rate is not None else None,
            "product_name": product_name,
        }
        await create_pending_operation(db, company, PendingOperationType.update_gst, payload)
        company.active_workflow = None
        company.workflow_scratch = None
        return t("gst.preview", loc, target=target, rate_text=rate_text)

    # Unreachable in practice (every step above is exhaustive for this flow),
    # but never leave a company stuck on a workflow step this code can't run.
    company.active_workflow = None
    company.workflow_scratch = None
    return t("workflow.error_restart", loc, trigger="update gst")
