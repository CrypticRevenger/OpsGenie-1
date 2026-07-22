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

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import Locale, resolve_locale, t
from app.models.business_event import BusinessEvent, BusinessEventType
from app.models.company import Company
from app.models.dealer import Dealer
from app.models.supplier import Supplier
from app.services.gst import validate_gstin
from app.services.importer.normalizer import parse_amount
from app.services.money_format import format_inr
from app.services.onboarding_flow import _classify_entry_mode, _is, _parse_bulk_party_line
from app.services.phone import InvalidPhoneNumberError, normalize_party_phone

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
            try:
                scratch["phone"] = normalize_party_phone(stripped)
            except InvalidPhoneNumberError:
                return t("onboarding.party.phone_invalid", loc)
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
            try:
                scratch["phone"] = normalize_party_phone(stripped)
            except InvalidPhoneNumberError:
                return t("onboarding.party.phone_invalid", loc)
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


# ── Edit dealer / edit supplier (phone, credit limit, terms, GSTIN) ────────────
#
# Same tier as product_flow.py's update_product (field picker, write
# immediately — not a PendingOperation): these are non-transactional
# attribute fields that never touch any ledger figure. One shared state
# machine parameterized by the model class, since dealer/supplier only
# differ in which table and i18n strings apply — same shape add_dealer/
# add_supplier already use for the same reason.

_FIELD_TO_ATTR = {
    "phone": "phone",
    "credit_limit": "credit_limit",
    "payment_terms": "payment_terms_days",
    "gst_number": "gst_number",
    "marketing_opt_in": "marketing_opt_in",
    "direct_reminders_enabled": "direct_reminders_enabled",
}
_FIELD_DISPLAY = {
    "phone": "phone",
    "credit_limit": "credit limit",
    "payment_terms": "payment terms",
    "gst_number": "GSTIN",
    "marketing_opt_in": "marketing opt-in",
    "direct_reminders_enabled": "direct reminders",
}
# Boolean-valued fields share the same yes/no parsing and a per-field
# true/false i18n label pair — pulled into one lookup rather than repeating
# near-identical branches per field, same reuse rationale as elsewhere in
# this module (onboarding_flow's bulk-party-line parser, etc.).
_BOOLEAN_FIELD_LABELS = {
    "marketing_opt_in": ("party.edit.opted_in", "party.edit.opted_out"),
    "direct_reminders_enabled": ("party.edit.reminders_enabled", "party.edit.reminders_disabled"),
}
_BOOLEAN_FIELD_INVALID_KEY = {
    "marketing_opt_in": "party.edit.marketing_invalid",
    "direct_reminders_enabled": "party.edit.direct_reminders_invalid",
}


def _classify_party_field(text: str, *, party_type: str) -> str | None:
    normalized = text.strip().lower()
    if normalized in ("phone", "phone number", "mobile", "mobile number"):
        return "phone"
    if normalized in ("credit limit", "creditlimit", "credit_limit", "limit"):
        return "credit_limit"
    if normalized in ("payment terms", "payment_terms", "credit days", "terms", "credit_days"):
        return "payment_terms"
    if normalized in ("gstin", "gst", "gst number", "gst_number"):
        return "gst_number"
    # Marketing consent and direct reminders only exist on Dealer (broadcast
    # and overdue reminders are both dealer-facing) — a supplier has neither
    # column, so these keywords must never resolve for party_type ==
    # "supplier".
    if party_type == "dealer" and normalized in (
        "marketing",
        "marketing opt in",
        "marketing_opt_in",
        "opt in",
        "opt-in",
        "whatsapp marketing",
        "promotions",
    ):
        return "marketing_opt_in"
    if party_type == "dealer" and normalized in (
        "reminders",
        "reminder",
        "direct reminders",
        "direct_reminders",
        "dealer reminders",
        "overdue reminders",
    ):
        return "direct_reminders_enabled"
    return None


def _format_field_value(field: str, value: object, loc: Locale) -> str:
    if value is None:
        return t("product.not_set", loc)
    if field == "credit_limit":
        return format_inr(value)  # type: ignore[arg-type]
    if field in _BOOLEAN_FIELD_LABELS:
        true_key, false_key = _BOOLEAN_FIELD_LABELS[field]
        return t(true_key, loc) if value else t(false_key, loc)
    return str(value)


async def _find_parties_by_name(
    db: AsyncSession, company_id: uuid.UUID, model: type[Dealer] | type[Supplier], name: str
) -> list[Dealer] | list[Supplier]:
    result = await db.scalars(
        select(model).where(model.company_id == company_id, func.lower(model.name) == name.lower())
    )
    return list(result.all())


def _describe_party_candidate(party: Dealer | Supplier) -> str:
    return f"{party.name} ({party.phone or 'no phone on file'})"


def _current_value_prompt(party: Dealer | Supplier, field: str, loc: Locale) -> str:
    current = _format_field_value(field, getattr(party, _FIELD_TO_ATTR[field]), loc)
    key = {
        "phone": "party.edit.phone_ask",
        "credit_limit": "party.edit.credit_limit_ask",
        "payment_terms": "party.edit.payment_terms_ask",
        "gst_number": "party.edit.gstin_ask",
        "marketing_opt_in": "party.edit.marketing_ask",
        "direct_reminders_enabled": "party.edit.direct_reminders_ask",
    }[field]
    return t(key, loc, name=party.name, current=current)


def start_edit_dealer_workflow(company: Company) -> str:
    company.active_workflow = "edit_dealer"
    company.workflow_scratch = {"step": "awaiting_field"}
    # Dealer-only field_prompt mentions marketing opt-in — the supplier
    # variant doesn't, since Supplier has no marketing_opt_in column.
    return t("party.edit.field_prompt_dealer", resolve_locale(company))


def start_edit_supplier_workflow(company: Company) -> str:
    company.active_workflow = "edit_supplier"
    company.workflow_scratch = {"step": "awaiting_field"}
    return t("party.edit.field_prompt_supplier", resolve_locale(company))


async def _handle_edit_party_workflow_message(
    db: AsyncSession,
    company: Company,
    text: str,
    model: type[Dealer] | type[Supplier],
    party_type: str,
) -> str:
    stripped = text.strip()
    loc = resolve_locale(company)

    if _is(stripped, "cancel", "stop"):
        company.active_workflow = None
        company.workflow_scratch = None
        return t("workflow.cancelled", loc)

    scratch = dict(company.workflow_scratch or {})
    step = scratch.get("step")

    if step == "awaiting_field":
        field = _classify_party_field(stripped, party_type=party_type)
        if field is None:
            key = (
                "party.edit.field_invalid_dealer"
                if party_type == "dealer"
                else "party.edit.field_invalid_supplier"
            )
            return t(key, loc)
        scratch = {"step": "awaiting_name", "field": field}
        company.workflow_scratch = scratch
        key = (
            "party.edit.name_ask_dealer"
            if party_type == "dealer"
            else "party.edit.name_ask_supplier"
        )
        return t(key, loc)

    if step == "awaiting_name":
        if not stripped:
            key = (
                "party.edit.name_ask_dealer"
                if party_type == "dealer"
                else "party.edit.name_ask_supplier"
            )
            return t(key, loc)
        matches = await _find_parties_by_name(db, company.id, model, stripped)
        if not matches:
            return t("party.edit.not_found", loc, name=stripped)
        if len(matches) > 1:
            scratch["candidates"] = [str(p.id) for p in matches]
            scratch["step"] = "awaiting_disambiguation"
            company.workflow_scratch = scratch
            listing = "\n".join(
                t(
                    "product.candidate_line",
                    loc,
                    index=i,
                    description=_describe_party_candidate(p),
                )
                for i, p in enumerate(matches, start=1)
            )
            return t(
                "party.edit.disambiguation", loc, count=len(matches), name=stripped, listing=listing
            )
        party = matches[0]
        scratch["party_id"] = str(party.id)
        scratch["party_name"] = party.name
        scratch["step"] = "awaiting_value"
        company.workflow_scratch = scratch
        return _current_value_prompt(party, scratch["field"], loc)

    if step == "awaiting_disambiguation":
        candidates = scratch.get("candidates", [])
        try:
            index = int(stripped)
        except ValueError:
            index = -1
        if not (1 <= index <= len(candidates)):
            return t("party.edit.disambiguation_invalid", loc, count=len(candidates))
        party = await db.get(model, uuid.UUID(candidates[index - 1]))
        if party is None:
            company.active_workflow = None
            company.workflow_scratch = None
            return t("party.edit.gone", loc, trigger=f"edit {party_type}")
        scratch["party_id"] = str(party.id)
        scratch["party_name"] = party.name
        scratch["step"] = "awaiting_value"
        company.workflow_scratch = scratch
        return _current_value_prompt(party, scratch["field"], loc)

    if step == "awaiting_value":
        field = scratch["field"]
        party = await db.get(model, uuid.UUID(scratch["party_id"]))
        if party is None:
            company.active_workflow = None
            company.workflow_scratch = None
            return t("party.edit.gone_value", loc)

        if field == "phone":
            try:
                new_value_raw = normalize_party_phone(stripped)
            except InvalidPhoneNumberError:
                return t("party.edit.phone_invalid", loc)
            new_value_display = new_value_raw
        elif field == "credit_limit":
            try:
                value = parse_amount(stripped)
            except ValueError:
                return t("product.value_invalid", loc)
            if value < 0:
                return t("product.value_nonneg", loc)
            new_value_raw = str(value)
            new_value_display = format_inr(value)
        elif field == "payment_terms":
            try:
                days = int(stripped)
            except ValueError:
                return t("party.edit.days_invalid", loc)
            if days < 0:
                return t("product.value_nonneg", loc)
            new_value_raw = str(days)
            new_value_display = str(days)
        elif field in _BOOLEAN_FIELD_LABELS:
            if _is(stripped, "yes", "y", "opt in", "on", "enable"):
                flag = True
            elif _is(stripped, "no", "n", "opt out", "off", "disable"):
                flag = False
            else:
                return t(_BOOLEAN_FIELD_INVALID_KEY[field], loc)
            new_value_raw = "true" if flag else "false"
            true_key, false_key = _BOOLEAN_FIELD_LABELS[field]
            new_value_display = t(true_key, loc) if flag else t(false_key, loc)
        else:
            candidate_gstin = stripped.strip().upper()
            if not validate_gstin(candidate_gstin):
                return t("party.edit.gstin_invalid", loc)
            new_value_raw = candidate_gstin
            new_value_display = candidate_gstin

        preview = t(
            "party.edit.value_preview",
            loc,
            name=scratch["party_name"],
            field=_FIELD_DISPLAY[field],
            new=new_value_display,
        )
        scratch.update(
            {"step": "awaiting_reason", "new_value": new_value_raw, "preview": preview}
        )
        company.workflow_scratch = scratch
        return t("edit.reason_ask", loc, preview=preview)

    if step == "awaiting_reason":
        reason = None if (not stripped or _is(stripped, "skip")) else stripped
        field = scratch["field"]
        party = await db.get(model, uuid.UUID(scratch["party_id"]))
        company.active_workflow = None
        company.workflow_scratch = None
        if party is None:
            return t("party.edit.gone_value", loc)

        attr = _FIELD_TO_ATTR[field]
        old_display = _format_field_value(field, getattr(party, attr), loc)
        new_value_raw = scratch["new_value"]
        if field == "credit_limit":
            setattr(party, attr, Decimal(new_value_raw))
        elif field == "payment_terms":
            setattr(party, attr, int(new_value_raw))
        elif field in _BOOLEAN_FIELD_LABELS:
            setattr(party, attr, new_value_raw == "true")
        else:
            setattr(party, attr, new_value_raw)
        new_display = _format_field_value(field, getattr(party, attr), loc)

        db.add(
            BusinessEvent(
                company_id=company.id,
                event_type=BusinessEventType.party_edited,
                entity_type=party_type,
                entity_id=party.id,
                payload={
                    "party_name": party.name,
                    "field": field,
                    "old": old_display,
                    "new": new_display,
                    "reason": reason,
                },
                created_by="whatsapp",
            )
        )
        return t(
            "party.edit.success",
            loc,
            name=party.name,
            field=_FIELD_DISPLAY[field],
            new=new_display,
            old=old_display,
        )

    # Unreachable in practice (every step above is exhaustive for this flow),
    # but never leave a company stuck on a workflow step this code can't run.
    company.active_workflow = None
    company.workflow_scratch = None
    return t("workflow.error_restart", loc, trigger=f"edit {party_type}")


async def handle_edit_dealer_workflow_message(db: AsyncSession, company: Company, text: str) -> str:
    return await _handle_edit_party_workflow_message(db, company, text, Dealer, "dealer")


async def handle_edit_supplier_workflow_message(
    db: AsyncSession, company: Company, text: str
) -> str:
    return await _handle_edit_party_workflow_message(db, company, text, Supplier, "supplier")
