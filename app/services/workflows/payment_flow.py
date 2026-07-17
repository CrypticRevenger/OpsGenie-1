"""Guided record-payment workflow — Phase 2A.

Party? -> (disambiguate/confirm-add if needed) -> (pick an invoice, only
asked when the party has more than one open one) -> Amount? -> Date? ->
Preview -> PendingOperation -> YES/NO (handled by app/services/writes/
pending_operation.py, not here). Same state-machine shape as
app/services/onboarding_flow.py: state lives in Company.active_workflow
(which flow) + Company.workflow_scratch (that flow's own step + collected
fields), mutated in place, never committed here.

Unknown dealer/supplier names are confirmed before creating (per this
project's Phase-2A review) rather than silently auto-created like the CSV
importer's find_or_create_party does — a typo in a chat message is much more
likely to slip through than in a reviewed CSV file. A genuinely brand-new
party has no invoice on file, so a payment against them can never actually
be recorded (allocate_payment_fifo requires an open invoice) — the flow
says so immediately after the add-confirmation rather than walking through
amount/date questions toward a guaranteed failure, and deliberately doesn't
create the dealer/supplier row itself (unlike the CSV importer, which does
keep a party record even when its payment fails) — there's no useful data to
keep yet, just a name.

A party with exactly one open invoice skips the picker entirely and targets
it directly (same UX as before this existed); "all" on the picker preserves
the original FIFO-across-every-open-invoice behavior for anyone who doesn't
care which invoice a payment lands on. Only a party with 2+ open invoices and
no explicit choice used to silently FIFO-allocate to whichever invoice
happened to sort first (oldest invoice_date, then invoice_number as a
tie-break) — which could apply a payment to the wrong invoice from the
user's point of view even though the total outstanding math was correct.

"cancel"/"stop" are recognized at every step, not just one — an active
workflow outranks the menu/follow-up/assistant in the webhook, so without a
universal exit a user could otherwise get stuck until they either finish the
flow or guess the one step that happens to accept "no".
"""

from __future__ import annotations

import re
import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.dealer import Dealer
from app.models.pending_operation import PendingOperationType
from app.models.supplier import Supplier
from app.services.importer.normalizer import parse_amount
from app.services.importer.payment_row import open_invoices_with_outstanding
from app.services.money_format import format_inr
from app.services.onboarding_flow import _is
from app.services.snapshot import business_now
from app.services.writes.pending_operation import create_pending_operation

_DAYS_AGO_PATTERN = re.compile(r"^(\d+)\s*days?\s*ago$")
# A payment recorded "N days ago" beyond this is almost certainly a typo/
# garbage input (a pasted phone number, timestamp, etc.), not a real date —
# also guards date - timedelta(days=N) against OverflowError for very large N.
_MAX_DAYS_AGO = 3650  # ~10 years


def _amount_prompt(direction: str) -> str:
    verb = "did they pay you" if direction == "receivable" else "did you pay them"
    return f"How much {verb}? (e.g. 25000)"


def _parse_past_date(text: str, today: date) -> date | None:
    """Deliberately past-oriented and a small fixed vocabulary — NOT
    app/services/followup.py's _parse_relative_date, which projects "N days"
    into the future for due dates. Reusing that here would silently
    misinterpret "3 days" as 3 days from now for a payment that already
    happened.
    """
    cleaned = text.strip().lower()
    if cleaned in ("", "today", "skip"):
        return today
    if cleaned == "yesterday":
        return today - timedelta(days=1)
    match = _DAYS_AGO_PATTERN.match(cleaned)
    if match:
        days = int(match.group(1))
        if days > _MAX_DAYS_AGO:
            return None
        return today - timedelta(days=days)
    return None


def _parse_dealer_or_supplier_choice(stripped: str) -> str | None:
    """ "1"/"2" -> receivable/payable, shared by the disambiguation step (name
    matches both a dealer and a supplier) and the new-party step (name
    matches neither) — both just need this same choice, only what happens
    next differs.
    """
    if stripped == "1":
        return "receivable"
    if stripped == "2":
        return "payable"
    return None


async def _find_dealer(db: AsyncSession, company_id: uuid.UUID, name: str) -> Dealer | None:
    return await db.scalar(
        select(Dealer).where(
            Dealer.company_id == company_id, func.lower(Dealer.name) == name.lower()
        )
    )


async def _find_supplier(db: AsyncSession, company_id: uuid.UUID, name: str) -> Supplier | None:
    return await db.scalar(
        select(Supplier).where(
            Supplier.company_id == company_id, func.lower(Supplier.name) == name.lower()
        )
    )


def _no_open_invoice_message(party_name: str, direction: str) -> str:
    kind = "dealer" if direction == "receivable" else "supplier"
    return (
        f"I can only record a payment against an existing invoice, though, and "
        f"{party_name} doesn't have an open one as a {kind}. Create an invoice for "
        "them first, then say 'record payment' again."
    )


async def _proceed_after_direction(
    db: AsyncSession, company: Company, scratch: dict, party_id: uuid.UUID
) -> str:
    """Once direction + party are both known: look up that party's open
    invoices and either skip straight to the amount question (0 or 1 open
    invoice — the common case, unchanged from before this existed) or ask
    which invoice the payment is for (2+ — previously silently FIFO-
    allocated to whichever invoice sorted first, which could apply a payment
    to the wrong one when a party has more than one open invoice).
    """
    direction = scratch["direction"]
    party_name = scratch["party_name"]
    invoices_with_outstanding = await open_invoices_with_outstanding(
        db, company_id=company.id, direction=direction, party_id=party_id
    )
    if not invoices_with_outstanding:
        company.active_workflow = None
        company.workflow_scratch = None
        return _no_open_invoice_message(party_name, direction)

    if len(invoices_with_outstanding) == 1:
        invoice, _outstanding = invoices_with_outstanding[0]
        scratch["invoice_id"] = str(invoice.id)
        scratch["invoice_number"] = invoice.invoice_number
        scratch["step"] = "awaiting_amount"
        company.workflow_scratch = scratch
        return _amount_prompt(direction)

    scratch["invoice_choices"] = [
        [str(invoice.id), invoice.invoice_number]
        for invoice, _outstanding in invoices_with_outstanding
    ]
    scratch["step"] = "awaiting_invoice_selection"
    company.workflow_scratch = scratch
    listing = "\n".join(
        f"{i}. {invoice.invoice_number} — {format_inr(invoice.total_amount)} total, "
        f"{format_inr(outstanding)} outstanding, due {invoice.due_date.isoformat()}"
        for i, (invoice, outstanding) in enumerate(invoices_with_outstanding, start=1)
    )
    return (
        f"{party_name} has {len(invoices_with_outstanding)} open invoices:\n{listing}\n"
        "Reply with a number, or 'all' to apply across all of them (oldest first)."
    )


def start_payment_workflow(company: Company) -> str:
    """Sets active_workflow + the first step's scratch and returns the
    opening question verbatim — called both by the webhook's keyword-match
    branch and (in a later phase) an agent starter tool, so the exact
    wording is guaranteed either way.
    """
    company.active_workflow = "record_payment"
    company.workflow_scratch = {"step": "awaiting_party"}
    return "Who paid you, or who did you pay? (party name)"


async def handle_payment_workflow_message(db: AsyncSession, company: Company, text: str) -> str:
    """Advance the guided record-payment flow by one message. Only mutates
    state/rows — the caller (the webhook) commits.
    """
    stripped = text.strip()

    if _is(stripped, "cancel", "stop"):
        company.active_workflow = None
        company.workflow_scratch = None
        return "OK, cancelled."

    scratch = dict(company.workflow_scratch or {})
    step = scratch.get("step")

    if step == "awaiting_party":
        if not stripped:
            return "Please tell me the party's name."
        dealer = await _find_dealer(db, company.id, stripped)
        supplier = await _find_supplier(db, company.id, stripped)
        scratch["party_name"] = stripped
        if dealer is not None and supplier is None:
            scratch["direction"] = "receivable"
            return await _proceed_after_direction(db, company, scratch, dealer.id)
        if supplier is not None and dealer is None:
            scratch["direction"] = "payable"
            return await _proceed_after_direction(db, company, scratch, supplier.id)
        if dealer is not None and supplier is not None:
            scratch["dealer_id"] = str(dealer.id)
            scratch["supplier_id"] = str(supplier.id)
            scratch["step"] = "awaiting_disambiguation"
            company.workflow_scratch = scratch
            return (
                f"'{stripped}' matches both a dealer and a supplier on file. "
                "Reply 1 if they're the dealer (they paid you), "
                "or 2 if they're the supplier (you paid them)."
            )
        scratch["step"] = "awaiting_new_party_type"
        company.workflow_scratch = scratch
        return (
            f"I don't have '{stripped}' on file. Are they a dealer (customer) "
            "or a supplier (you buy from)? Reply 1 Dealer or 2 Supplier."
        )

    if step == "awaiting_disambiguation":
        direction = _parse_dealer_or_supplier_choice(stripped)
        if direction is None:
            return "Please reply 1 for dealer or 2 for supplier."
        scratch["direction"] = direction
        party_id_raw = scratch["dealer_id"] if direction == "receivable" else scratch["supplier_id"]
        return await _proceed_after_direction(db, company, scratch, uuid.UUID(party_id_raw))

    if step == "awaiting_invoice_selection":
        if _is(stripped, "all"):
            scratch["invoice_id"] = None
            scratch["invoice_number"] = None
            scratch["step"] = "awaiting_amount"
            company.workflow_scratch = scratch
            return _amount_prompt(scratch["direction"])
        choices = scratch.get("invoice_choices", [])
        try:
            index = int(stripped)
        except ValueError:
            index = -1
        if not (1 <= index <= len(choices)):
            return f"Please reply with a number from 1 to {len(choices)}, or 'all'."
        invoice_id, invoice_number = choices[index - 1]
        scratch["invoice_id"] = invoice_id
        scratch["invoice_number"] = invoice_number
        scratch["step"] = "awaiting_amount"
        company.workflow_scratch = scratch
        return _amount_prompt(scratch["direction"])

    if step == "awaiting_new_party_type":
        direction = _parse_dealer_or_supplier_choice(stripped)
        if direction is None:
            return "Please reply 1 Dealer or 2 Supplier."
        scratch["pending_direction"] = direction
        scratch["step"] = "awaiting_new_party_confirm"
        company.workflow_scratch = scratch
        kind = "dealer" if direction == "receivable" else "supplier"
        return f"Add '{scratch['party_name']}' as a new {kind}? yes/no"

    if step == "awaiting_new_party_confirm":
        if _is(stripped, "no", "n"):
            company.active_workflow = None
            company.workflow_scratch = None
            return "OK, cancelled."
        if not _is(stripped, "yes", "y"):
            return "Please reply yes or no."
        # A brand-new party has no invoice on file — recording a payment
        # against them can never succeed (allocate_payment_fifo requires an
        # open invoice), so say so now instead of asking amount/date toward
        # a guaranteed failure. Deliberately doesn't create the dealer/
        # supplier row itself; there's nothing useful to save yet, just a
        # name — create_invoice (Phase 2B) is where a real new-party record
        # will first earn its keep.
        party_name = scratch["party_name"]
        direction = scratch["pending_direction"]
        company.active_workflow = None
        company.workflow_scratch = None
        return f"Got it. {_no_open_invoice_message(party_name, direction)}"

    if step == "awaiting_amount":
        try:
            amount = parse_amount(stripped)
        except ValueError:
            return "Please send an amount, e.g. 25000."
        if amount <= 0:
            return "Please send an amount greater than zero."
        scratch["amount"] = str(amount)
        scratch["step"] = "awaiting_date"
        company.workflow_scratch = scratch
        return "When was this paid? Reply 'today', 'yesterday', '3 days ago', or skip for today."

    if step == "awaiting_date":
        today = business_now(company.timezone).date()
        payment_date = _parse_past_date(stripped, today)
        if payment_date is None:
            return "Sorry, I didn't get that date. Try 'today', 'yesterday', '3 days ago'."

        direction = scratch["direction"]
        party_name = scratch["party_name"]
        amount = Decimal(scratch["amount"])
        invoice_number = scratch.get("invoice_number")
        verb = "from" if direction == "receivable" else "to"
        target = f" against invoice {invoice_number}" if invoice_number else ""
        preview = (
            f"Confirm: {format_inr(amount)} {verb} {party_name}{target} "
            f"on {payment_date.isoformat()}.\n"
            "Reply YES to record, NO to cancel."
        )
        await create_pending_operation(
            db,
            company,
            PendingOperationType.record_payment,
            {
                "direction": direction,
                "party_name": party_name,
                "amount": str(amount),
                "payment_date": payment_date.isoformat(),
                "invoice_id": scratch.get("invoice_id"),
            },
        )
        company.active_workflow = None
        company.workflow_scratch = None
        return preview

    # Unreachable in practice (every step above is exhaustive for this flow),
    # but never leave a company stuck in an unknown workflow step.
    company.active_workflow = None
    company.workflow_scratch = None
    return "Something went wrong with that. Please start again by saying 'record payment'."
