"""Guided "edit invoice" / "edit payment" workflows — safe cases only.

edit_invoice: invoice number -> field (amount/date/party) -> new value ->
optional reason -> PendingOperation -> YES/NO. Refuses up front (before
even asking which field) if the invoice already has any payment recorded —
no automatic reallocation is ever attempted, see
app/services/writes/edit_invoice_payment.py's module docstring.

edit_payment: party name (reuses app/services/party_lookup.py::find_party,
the same helper "balance <name>"/"ledger <name>" share) -> pick from that
party's last 5 payments -> field (amount/date only — no party/invoice
reassignment in this iteration) -> new value -> optional reason ->
PendingOperation -> YES/NO.

Same state-machine shape as app/services/workflows/gst_flow.py: state lives
in Company.active_workflow + Company.workflow_scratch, mutated in place,
never committed here. "cancel"/"stop" recognized at every step.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import resolve_locale, t
from app.models.company import Company
from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceDirection
from app.models.payment import Payment
from app.models.pending_operation import PendingOperationType
from app.models.supplier import Supplier
from app.services.importer.normalizer import parse_amount, parse_date
from app.services.money_format import format_inr
from app.services.onboarding_flow import _is
from app.services.party_lookup import find_party
from app.services.writes.pending_operation import create_pending_operation

_INVOICE_FIELD_WORDS = {"amount", "date", "party"}
_PAYMENT_FIELD_WORDS = {"amount", "date"}


def _classify_field(text: str, allowed: set[str]) -> str | None:
    normalized = text.strip().lower()
    return normalized if normalized in allowed else None


# ── Edit invoice ─────────────────────────────────────────────────────────────


def start_edit_invoice_workflow(company: Company) -> str:
    company.active_workflow = "edit_invoice"
    company.workflow_scratch = {"step": "awaiting_number"}
    return t("edit.invoice_number_ask", resolve_locale(company))


async def handle_edit_invoice_workflow_message(
    db: AsyncSession, company: Company, text: str
) -> str:
    stripped = text.strip()
    loc = resolve_locale(company)

    if _is(stripped, "cancel", "stop"):
        company.active_workflow = None
        company.workflow_scratch = None
        return t("workflow.cancelled", loc)

    scratch = dict(company.workflow_scratch or {})
    step = scratch.get("step")

    if step == "awaiting_number":
        if not stripped:
            return t("edit.invoice_number_ask", loc)
        invoice = await db.scalar(
            select(Invoice).where(
                Invoice.company_id == company.id,
                func.lower(Invoice.invoice_number) == stripped.lower(),
            )
        )
        if invoice is None:
            return t("edit.invoice_not_found", loc, number=stripped)
        has_payment = await db.scalar(select(Payment.id).where(Payment.invoice_id == invoice.id))
        if has_payment is not None:
            company.active_workflow = None
            company.workflow_scratch = None
            return t("edit.invoice_has_payment", loc, number=invoice.invoice_number)
        scratch = {
            "step": "awaiting_field",
            "invoice_id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
        }
        company.workflow_scratch = scratch
        return t("edit.field_ask_invoice", loc)

    if step == "awaiting_field":
        field = _classify_field(stripped, _INVOICE_FIELD_WORDS)
        if field is None:
            return t("edit.field_invalid_invoice", loc)
        invoice = await db.get(Invoice, uuid.UUID(scratch["invoice_id"]))
        if invoice is None:
            company.active_workflow = None
            company.workflow_scratch = None
            return t("product.gone", loc, trigger="edit invoice")
        scratch["field"] = field
        scratch["step"] = "awaiting_value"
        company.workflow_scratch = scratch
        if field == "amount":
            return t("edit.amount_ask", loc, current=format_inr(invoice.total_amount))
        if field == "date":
            return t("edit.date_ask", loc, current=invoice.invoice_date.isoformat())
        if invoice.direction == InvoiceDirection.receivable:
            current = (
                await db.get(Dealer, invoice.dealer_id) if invoice.dealer_id is not None else None
            )
            return t(
                "edit.invoice_party_ask_dealer",
                loc,
                current=current.name if current is not None else "—",
            )
        current = (
            await db.get(Supplier, invoice.supplier_id)
            if invoice.supplier_id is not None
            else None
        )
        return t(
            "edit.invoice_party_ask_supplier",
            loc,
            current=current.name if current is not None else "—",
        )

    if step == "awaiting_value":
        field = scratch["field"]
        invoice = await db.get(Invoice, uuid.UUID(scratch["invoice_id"]))
        if invoice is None:
            company.active_workflow = None
            company.workflow_scratch = None
            return t("product.gone", loc, trigger="edit invoice")

        if field == "amount":
            try:
                value = parse_amount(stripped)
            except ValueError:
                return t("edit.amount_invalid", loc)
            if value <= 0:
                return t("edit.amount_invalid", loc)
            new_value_raw = str(value)
            new_value_display = format_inr(value)
        elif field == "date":
            try:
                parsed_date = parse_date(stripped)
            except ValueError:
                return t("edit.date_invalid", loc)
            new_value_raw = parsed_date.isoformat()
            new_value_display = new_value_raw
        else:
            if invoice.direction == InvoiceDirection.receivable:
                party = await db.scalar(
                    select(Dealer).where(
                        Dealer.company_id == company.id, func.lower(Dealer.name) == stripped.lower()
                    )
                )
            else:
                party = await db.scalar(
                    select(Supplier).where(
                        Supplier.company_id == company.id,
                        func.lower(Supplier.name) == stripped.lower(),
                    )
                )
            if party is None:
                return t("edit.party_not_found", loc, name=stripped)
            new_value_raw = str(party.id)
            new_value_display = party.name

        preview = t(
            "edit.value_preview",
            loc,
            target=t("edit.target_invoice", loc, number=scratch["invoice_number"]),
            field=field,
            new=new_value_display,
        )
        scratch.update(
            {
                "step": "awaiting_reason",
                "new_value": new_value_raw,
                "preview": preview,
            }
        )
        company.workflow_scratch = scratch
        return t("edit.reason_ask", loc, preview=preview)

    if step == "awaiting_reason":
        reason = None if (not stripped or _is(stripped, "skip")) else stripped
        payload = {
            "invoice_id": scratch["invoice_id"],
            "field": scratch["field"],
            "new_value": scratch["new_value"],
            "reason": reason,
        }
        preview = scratch.get("preview", "")
        company.active_workflow = None
        company.workflow_scratch = None
        await create_pending_operation(db, company, PendingOperationType.edit_invoice, payload)
        return t("edit.confirm_prompt", loc, preview=preview)

    # Unreachable in practice (every step above is exhaustive for this flow),
    # but never leave a company stuck on a workflow step this code can't run.
    company.active_workflow = None
    company.workflow_scratch = None
    return t("workflow.error_restart", loc, trigger="edit invoice")


# ── Edit payment ─────────────────────────────────────────────────────────────


def start_edit_payment_workflow(company: Company) -> str:
    company.active_workflow = "edit_payment"
    company.workflow_scratch = {"step": "awaiting_party_name"}
    return t("edit.party_name_ask", resolve_locale(company))


async def _recent_payments_for_party(
    db: AsyncSession, company_id: uuid.UUID, direction: str, party_id: uuid.UUID
) -> list[Payment]:
    party_column = Invoice.dealer_id if direction == "receivable" else Invoice.supplier_id
    result = await db.execute(
        select(Payment)
        .join(Invoice, Invoice.id == Payment.invoice_id)
        .where(Invoice.company_id == company_id, party_column == party_id)
        .order_by(Payment.created_at.desc())
        .limit(5)
    )
    return list(result.scalars().all())


def _payment_candidate_desc(payment: Payment, invoice_number: str) -> str:
    date_text = payment.payment_date.isoformat()
    return f"{format_inr(payment.amount)} on invoice {invoice_number} ({date_text})"


async def handle_edit_payment_workflow_message(
    db: AsyncSession, company: Company, text: str
) -> str:
    stripped = text.strip()
    loc = resolve_locale(company)

    if _is(stripped, "cancel", "stop"):
        company.active_workflow = None
        company.workflow_scratch = None
        return t("workflow.cancelled", loc)

    scratch = dict(company.workflow_scratch or {})
    step = scratch.get("step")

    if step == "awaiting_party_name":
        if not stripped:
            return t("edit.party_name_ask", loc)
        found = await find_party(db, company.id, stripped)
        if found is None:
            return t("edit.party_not_found", loc, name=stripped)
        party, direction = found
        payments = await _recent_payments_for_party(db, company.id, direction, party.id)
        if not payments:
            company.active_workflow = None
            company.workflow_scratch = None
            return t("edit.no_payments_for_party", loc, name=party.name)

        invoice_numbers: dict[str, str] = {}
        for payment in payments:
            invoice = await db.get(Invoice, payment.invoice_id)
            invoice_numbers[str(payment.id)] = invoice.invoice_number if invoice else "?"

        listing = "\n".join(
            t(
                "product.candidate_line",
                loc,
                index=i,
                description=_payment_candidate_desc(p, invoice_numbers[str(p.id)]),
            )
            for i, p in enumerate(payments, start=1)
        )
        scratch = {
            "step": "awaiting_pick",
            "candidates": [str(p.id) for p in payments],
        }
        company.workflow_scratch = scratch
        return t(
            "edit.payment_pick_ask", loc, count=len(payments), name=party.name, listing=listing
        )

    if step == "awaiting_pick":
        candidates = scratch.get("candidates", [])
        try:
            index = int(stripped)
        except ValueError:
            index = -1
        if not (1 <= index <= len(candidates)):
            return t("edit.payment_pick_invalid", loc, count=len(candidates))
        payment = await db.get(Payment, uuid.UUID(candidates[index - 1]))
        if payment is None:
            company.active_workflow = None
            company.workflow_scratch = None
            return t("edit.payment_gone", loc)
        invoice = await db.get(Invoice, payment.invoice_id)
        scratch = {
            "step": "awaiting_field",
            "payment_id": str(payment.id),
            "invoice_number": invoice.invoice_number if invoice else "?",
        }
        company.workflow_scratch = scratch
        return t("edit.field_ask_payment", loc)

    if step == "awaiting_field":
        field = _classify_field(stripped, _PAYMENT_FIELD_WORDS)
        if field is None:
            return t("edit.field_invalid_payment", loc)
        payment = await db.get(Payment, uuid.UUID(scratch["payment_id"]))
        if payment is None:
            company.active_workflow = None
            company.workflow_scratch = None
            return t("edit.payment_gone", loc)
        scratch["field"] = field
        scratch["step"] = "awaiting_value"
        company.workflow_scratch = scratch
        if field == "amount":
            return t("edit.amount_ask", loc, current=format_inr(payment.amount))
        return t("edit.date_ask", loc, current=payment.payment_date.isoformat())

    if step == "awaiting_value":
        field = scratch["field"]
        if field == "amount":
            try:
                value = parse_amount(stripped)
            except ValueError:
                return t("edit.amount_invalid", loc)
            if value <= 0:
                return t("edit.amount_invalid", loc)
            new_value_raw = str(value)
            new_value_display = format_inr(value)
        else:
            try:
                parsed_date = parse_date(stripped)
            except ValueError:
                return t("edit.date_invalid", loc)
            new_value_raw = parsed_date.isoformat()
            new_value_display = new_value_raw

        preview = t(
            "edit.value_preview",
            loc,
            target=t("edit.target_payment", loc, number=scratch["invoice_number"]),
            field=field,
            new=new_value_display,
        )
        scratch.update(
            {
                "step": "awaiting_reason",
                "new_value": new_value_raw,
                "preview": preview,
            }
        )
        company.workflow_scratch = scratch
        return t("edit.reason_ask", loc, preview=preview)

    if step == "awaiting_reason":
        reason = None if (not stripped or _is(stripped, "skip")) else stripped
        payload = {
            "payment_id": scratch["payment_id"],
            "field": scratch["field"],
            "new_value": scratch["new_value"],
            "reason": reason,
        }
        preview = scratch.get("preview", "")
        company.active_workflow = None
        company.workflow_scratch = None
        await create_pending_operation(db, company, PendingOperationType.edit_payment, payload)
        return t("edit.confirm_prompt", loc, preview=preview)

    # Unreachable in practice (every step above is exhaustive for this flow),
    # but never leave a company stuck on a workflow step this code can't run.
    company.active_workflow = None
    company.workflow_scratch = None
    return t("workflow.error_restart", loc, trigger="edit payment")
