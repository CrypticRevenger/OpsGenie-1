"""Guided add-dealer / add-supplier workflows — let an already-onboarded
company add a dealer or supplier any time, using the exact same
one-by-one/bulk process as onboarding's dealer/supplier steps
(app/services/onboarding_flow.py). Same state-machine shape as
app/services/workflows/product_flow.py's add-product workflow: state lives in
Company.active_workflow + Company.workflow_scratch, mutated in place, never
committed here — the webhook commits once.

Reuses onboarding_flow's mode classifier and bulk-party-line parser, and the
onboarding dealer/supplier i18n strings for the shared name/phone/credit/bulk
questions, so this behaves identically to onboarding's dealer/supplier step.
Only the entry prompt and the "nothing added"/"all done" wording are
workflow-specific — onboarding's own versions of those talk about skipping a
whole onboarding step, which doesn't fit a standalone command reached any
time after setup is already complete.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import resolve_locale, t
from app.models.company import Company
from app.models.dealer import Dealer
from app.models.supplier import Supplier
from app.services.onboarding_flow import _classify_entry_mode, _is, _parse_bulk_party_line

# ── Add dealer ────────────────────────────────────────────────────────────────


def start_add_dealer_workflow(company: Company) -> str:
    """Sets active_workflow + the first step's scratch and returns the
    opening question verbatim — same contract as start_add_product_workflow.
    """
    company.active_workflow = "add_dealer"
    company.workflow_scratch = {"step": "awaiting_mode"}
    return t("party.dealer.mode_prompt", resolve_locale(company))


async def handle_add_dealer_workflow_message(db: AsyncSession, company: Company, text: str) -> str:
    """Advance the guided add-dealer flow by one message. Only mutates
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
            return t("party.dealer.no_added", loc)
        mode = _classify_entry_mode(stripped)
        if mode == "bulk":
            scratch["step"] = "awaiting_bulk"
            company.workflow_scratch = scratch
            return t("onboarding.dealer.bulk_format", loc)
        if mode == "one_by_one":
            scratch["step"] = "awaiting_name"
            company.workflow_scratch = scratch
            return t("party.dealer.name_or_done", loc)
        return t("party.dealer.mode_invalid", loc)

    if step == "awaiting_bulk":
        if _is(stripped, "done", "skip"):
            company.active_workflow = None
            company.workflow_scratch = None
            return t("party.dealer.all_done", loc)
        lines = [line for line in stripped.splitlines() if line.strip()]
        if not lines:
            return t("onboarding.dealer.bulk_format", loc)
        parsed_items = []
        for line in lines:
            try:
                parsed_items.append(_parse_bulk_party_line(line))
            except ValueError as exc:
                return (
                    t("onboarding.bulk_error", loc, error=exc)
                    + "\n\n"
                    + t("onboarding.dealer.bulk_format", loc)
                )
        for item in parsed_items:
            db.add(
                Dealer(
                    company_id=company.id,
                    name=item["name"],
                    phone=item["phone"],
                    payment_terms_days=item["credit_days"],
                )
            )
        names = ", ".join(item["name"] for item in parsed_items)
        return t("onboarding.dealer.bulk_added", loc, count=len(parsed_items), names=names)

    if step == "awaiting_name":
        if _is(stripped, "done", "skip"):
            company.active_workflow = None
            company.workflow_scratch = None
            return t("party.dealer.all_done", loc)
        scratch["name"] = stripped
        scratch["step"] = "awaiting_phone"
        company.workflow_scratch = scratch
        return t("onboarding.party.phone_ask", loc, name=stripped)

    if step == "awaiting_phone":
        if not _is(stripped, "skip"):
            scratch["phone"] = stripped
        scratch["step"] = "awaiting_credit"
        company.workflow_scratch = scratch
        name = scratch.get("name", "them")
        return t("onboarding.dealer.credit_ask", loc, name=name)

    if step == "awaiting_credit":
        credit = None
        if not _is(stripped, "skip"):
            try:
                credit = int(stripped)
            except ValueError:
                return t("onboarding.party.credit_invalid", loc)
        name = scratch.get("name", "Dealer")
        db.add(
            Dealer(
                company_id=company.id,
                name=name,
                phone=scratch.get("phone"),
                payment_terms_days=credit,
            )
        )
        company.workflow_scratch = {"step": "awaiting_name"}
        return t("onboarding.dealer.added", loc, name=name)

    # Unreachable in practice (every step above is exhaustive for this flow),
    # but never leave a company stuck in an unknown workflow step.
    company.active_workflow = None
    company.workflow_scratch = None
    return t("workflow.error_restart", loc, trigger="add dealer")


# ── Add supplier (same shape as dealer) ────────────────────────────────────────


def start_add_supplier_workflow(company: Company) -> str:
    """Sets active_workflow + the first step's scratch and returns the
    opening question verbatim — same contract as start_add_dealer_workflow.
    """
    company.active_workflow = "add_supplier"
    company.workflow_scratch = {"step": "awaiting_mode"}
    return t("party.supplier.mode_prompt", resolve_locale(company))


async def handle_add_supplier_workflow_message(
    db: AsyncSession, company: Company, text: str
) -> str:
    """Advance the guided add-supplier flow by one message. Only mutates
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
            return t("party.supplier.no_added", loc)
        mode = _classify_entry_mode(stripped)
        if mode == "bulk":
            scratch["step"] = "awaiting_bulk"
            company.workflow_scratch = scratch
            return t("onboarding.supplier.bulk_format", loc)
        if mode == "one_by_one":
            scratch["step"] = "awaiting_name"
            company.workflow_scratch = scratch
            return t("party.supplier.name_or_done", loc)
        return t("party.supplier.mode_invalid", loc)

    if step == "awaiting_bulk":
        if _is(stripped, "done", "skip"):
            company.active_workflow = None
            company.workflow_scratch = None
            return t("party.supplier.all_done", loc)
        lines = [line for line in stripped.splitlines() if line.strip()]
        if not lines:
            return t("onboarding.supplier.bulk_format", loc)
        parsed_items = []
        for line in lines:
            try:
                parsed_items.append(_parse_bulk_party_line(line))
            except ValueError as exc:
                return (
                    t("onboarding.bulk_error", loc, error=exc)
                    + "\n\n"
                    + t("onboarding.supplier.bulk_format", loc)
                )
        for item in parsed_items:
            db.add(
                Supplier(
                    company_id=company.id,
                    name=item["name"],
                    phone=item["phone"],
                    payment_terms_days=item["credit_days"],
                )
            )
        names = ", ".join(item["name"] for item in parsed_items)
        return t("onboarding.supplier.bulk_added", loc, count=len(parsed_items), names=names)

    if step == "awaiting_name":
        if _is(stripped, "done", "skip"):
            company.active_workflow = None
            company.workflow_scratch = None
            return t("party.supplier.all_done", loc)
        scratch["name"] = stripped
        scratch["step"] = "awaiting_phone"
        company.workflow_scratch = scratch
        return t("onboarding.party.phone_ask", loc, name=stripped)

    if step == "awaiting_phone":
        if not _is(stripped, "skip"):
            scratch["phone"] = stripped
        scratch["step"] = "awaiting_credit"
        company.workflow_scratch = scratch
        name = scratch.get("name", "they")
        return t("onboarding.supplier.credit_ask", loc, name=name)

    if step == "awaiting_credit":
        credit = None
        if not _is(stripped, "skip"):
            try:
                credit = int(stripped)
            except ValueError:
                return t("onboarding.party.credit_invalid", loc)
        name = scratch.get("name", "Supplier")
        db.add(
            Supplier(
                company_id=company.id,
                name=name,
                phone=scratch.get("phone"),
                payment_terms_days=credit,
            )
        )
        company.workflow_scratch = {"step": "awaiting_name"}
        return t("onboarding.supplier.added", loc, name=name)

    # Unreachable in practice (every step above is exhaustive for this flow),
    # but never leave a company stuck in an unknown workflow step.
    company.active_workflow = None
    company.workflow_scratch = None
    return t("workflow.error_restart", loc, trigger="add supplier")
