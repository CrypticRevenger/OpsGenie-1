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

from app.models.company import Company
from app.models.pending_operation import PendingOperationType
from app.models.product import Product
from app.services.gst import parse_gst_rate
from app.services.onboarding_flow import _is
from app.services.workflows.product_flow import _describe_candidate, _find_products_by_name
from app.services.writes.pending_operation import create_pending_operation

_SCOPE_PROMPT = (
    "Update GST for all products (company default), or one specific product? "
    "Reply 'all' or the product name."
)
_CLEAR_WORDS = {"clear", "none", "remove", "unset"}


def start_update_gst_workflow(company: Company) -> str:
    """Sets active_workflow + the first step's scratch and returns the
    opening question verbatim — same contract as start_order_workflow.
    """
    company.active_workflow = "update_gst"
    company.workflow_scratch = {"step": "awaiting_scope"}
    return _SCOPE_PROMPT


def _rate_prompt(scope: str, target: str) -> str:
    if scope == "all":
        return f"What's the new default GST rate for {target}? (0-100, or 'cancel')"
    return (
        f"What's the new GST rate for {target}? (0-100, 'clear' to remove its override "
        "and use the company default, or 'cancel')"
    )


async def handle_update_gst_workflow_message(db: AsyncSession, company: Company, text: str) -> str:
    """Advance the guided update-gst flow by one message. Only mutates
    state/rows — the caller (the webhook) commits.
    """
    stripped = text.strip()

    if _is(stripped, "cancel", "stop"):
        company.active_workflow = None
        company.workflow_scratch = None
        return "OK, cancelled."

    scratch = dict(company.workflow_scratch or {})
    step = scratch.get("step")

    if step == "awaiting_scope":
        if _is(stripped, "all"):
            scratch = {"step": "awaiting_rate", "scope": "all"}
            company.workflow_scratch = scratch
            return _rate_prompt("all", "all products")
        if not stripped:
            return _SCOPE_PROMPT
        matches = await _find_products_by_name(db, company.id, stripped)
        if not matches:
            return (
                f"I couldn't find a product named '{stripped}'. Reply 'all', another "
                "product name, or 'cancel'."
            )
        if len(matches) > 1:
            scratch = {
                "step": "awaiting_disambiguation",
                "candidates": [str(p.id) for p in matches],
            }
            company.workflow_scratch = scratch
            listing = "\n".join(
                f"{i}. {_describe_candidate(p)}" for i, p in enumerate(matches, start=1)
            )
            return (
                f"Found {len(matches)} products named '{stripped}':\n{listing}\n"
                "Reply with the number to update, or 'cancel'."
            )
        product = matches[0]
        scratch = {"step": "awaiting_rate", "scope": "product", "product_name": product.name}
        company.workflow_scratch = scratch
        return _rate_prompt("product", product.name)

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
                "'update gst'."
            )
        scratch = {"step": "awaiting_rate", "scope": "product", "product_name": product.name}
        company.workflow_scratch = scratch
        return _rate_prompt("product", product.name)

    if step == "awaiting_rate":
        scope = scratch.get("scope", "all")
        product_name = scratch.get("product_name")
        target = "all products" if scope == "all" else product_name

        if scope == "product" and _is(stripped, *_CLEAR_WORDS):
            gst_rate = None
            rate_text = "no override (use the company default)"
        else:
            try:
                gst_rate = parse_gst_rate(stripped)
            except ValueError:
                return (
                    "Please send a number between 0 and 100, e.g. 18.\n\n"
                    f"{_rate_prompt(scope, target)}"
                )
            rate_text = f"{gst_rate}%"

        payload = {
            "scope": scope,
            "gst_rate": str(gst_rate) if gst_rate is not None else None,
            "product_name": product_name,
        }
        await create_pending_operation(db, company, PendingOperationType.update_gst, payload)
        company.active_workflow = None
        company.workflow_scratch = None
        return f"Set GST for {target} to {rate_text}. Reply YES to confirm, NO to cancel."

    # Unreachable in practice (every step above is exhaustive for this flow),
    # but never leave a company stuck on a workflow step this code can't run.
    company.active_workflow = None
    company.workflow_scratch = None
    return "Something went wrong with that. Please start again by saying 'update gst'."
