"""Guided record-payment workflow — Phase 2A.

Party? -> (disambiguate/confirm-add if needed) -> Amount? -> Date? -> Preview
-> PendingOperation -> YES/NO (handled by app/services/writes/
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


async def _match_direction(db: AsyncSession, company_id: uuid.UUID, name: str) -> tuple[bool, bool]:
    """Case-insensitive existence check (not create) against both Dealer and
    Supplier. Returns (found_in_dealer, found_in_supplier) — the caller
    derives direction itself (receivable iff dealer-only, payable iff
    supplier-only) since that's fully determined by these two booleans.
    """
    found_dealer = (
        await db.scalar(
            select(Dealer.id).where(
                Dealer.company_id == company_id, func.lower(Dealer.name) == name.lower()
            )
        )
    ) is not None
    found_supplier = (
        await db.scalar(
            select(Supplier.id).where(
                Supplier.company_id == company_id, func.lower(Supplier.name) == name.lower()
            )
        )
    ) is not None
    return found_dealer, found_supplier


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
        found_dealer, found_supplier = await _match_direction(db, company.id, stripped)
        scratch["party_name"] = stripped
        if found_dealer and not found_supplier:
            scratch["direction"] = "receivable"
            scratch["step"] = "awaiting_amount"
            company.workflow_scratch = scratch
            return _amount_prompt("receivable")
        if found_supplier and not found_dealer:
            scratch["direction"] = "payable"
            scratch["step"] = "awaiting_amount"
            company.workflow_scratch = scratch
            return _amount_prompt("payable")
        if found_dealer and found_supplier:
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
        scratch["step"] = "awaiting_amount"
        company.workflow_scratch = scratch
        return _amount_prompt(direction)

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
        kind = "dealer" if scratch["pending_direction"] == "receivable" else "supplier"
        company.active_workflow = None
        company.workflow_scratch = None
        return (
            f"Got it. I can only record a payment against an existing invoice, though, "
            f"and {party_name} doesn't have one yet as a {kind}. "
            "Create an invoice for them first, then say 'record payment' again."
        )

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
        verb = "from" if direction == "receivable" else "to"
        preview = (
            f"Confirm: {format_inr(amount)} {verb} {party_name} on {payment_date.isoformat()}.\n"
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
