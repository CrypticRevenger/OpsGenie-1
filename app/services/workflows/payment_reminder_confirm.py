"""Guided "did you actually pay this?" follow-up to a supplier payment
reminder.

check_supplier_payment_reminders (app/services/notifications.py) fires a
WhatsApp reminder for every supplier bill due within 24h. Previously that
message was purely informational — nothing about it asked the founder to
confirm they'd actually paid, so a real payment could go unrecorded
indefinitely and cash/outstanding totals would silently drift from what
actually happened on the ground. This module turns the *first* due bill in
a batch into a tiny guided flow:

  awaiting_paid_choice -> 1 (paid): awaiting_amount_confirm -> preview ->
    PendingOperation(record_payment) [executed by
    app/services/writes/pending_operation.py, not here, same as every other
    guided write]
  awaiting_paid_choice -> 2 (not yet): awaiting_reschedule -> either a new
    due_date (moves the actual Invoice.due_date, so future reminders/
    briefings key off the new date) or 'skip' (left due — reminded again
    next cycle)

Company.active_workflow/active_pending_operation_id are single pointers, so
only one bill can be "in conversation" at a time — anything else due the
same tick rides along as workflow_scratch["queue"] (and, once the paid
branch hands off, the PendingOperation payload's "reminder_queue").
advance_reminder_queue() pops the next queued bill and starts this flow over
for it; it's called both from the "not yet paid" branch below and from
app/services/writes/pending_operation.py once a reminder-triggered
record_payment confirmation resolves, so every bill in a same-tick batch
eventually gets asked, one at a time.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import resolve_locale, t
from app.models.business_event import BusinessEvent, BusinessEventType
from app.models.company import Company
from app.models.invoice import Invoice
from app.models.pending_operation import PendingOperationType
from app.services.duplicate_check import find_similar_payment
from app.services.followup import _parse_relative_date
from app.services.importer.normalizer import parse_amount
from app.services.money_format import format_inr
from app.services.onboarding_flow import _is
from app.services.snapshot import business_now
from app.services.writes.pending_operation import create_pending_operation

_YES_WORDS = {"yes", "y", "1"}
_NO_WORDS = {"no", "n", "2"}

# A founder trying to check the help text or menu mid-reminder previously got
# swallowed by this flow's own "didn't understand, reply 1/2" restatement —
# confusing, since nothing told them *why* "help" didn't work. These words
# now get an explicit "finish this first, then continue" reply instead (see
# _current_question below), without cancelling the reminder the way
# "cancel"/"stop" do. Mirrors app/services/followup.py's identical fix.
_ORIENTATION_WORDS = {"help", "/help", "menu", "/menu", "commands", "what can you do"}


def _current_question(scratch: dict, loc) -> str:
    """Re-render whichever question this flow is currently waiting on — reused
    both by the orientation-word "please answer this first" reply and (for
    awaiting_paid_choice) the existing invalid-choice restatement, so the two
    can never drift apart.
    """
    step = scratch.get("step")
    if step == "awaiting_amount_confirm":
        return t("reminder_confirm.amount_ask", loc, amount=format_inr(Decimal(scratch["amount"])))
    if step == "awaiting_reschedule":
        return t("reminder_confirm.reschedule_ask", loc)
    # awaiting_paid_choice and any unexpected step both fall back to the
    # original paid/not-yet question — the only one guaranteed to have both
    # supplier_name and amount already in scratch.
    return t(
        "reminder_confirm.ask_paid",
        loc,
        supplier=scratch["supplier_name"],
        amount=format_inr(Decimal(scratch["amount"])),
    )


def start_reminder_confirm(company: Company, item: dict, queue: list[dict]) -> str:
    """item: {"supplier_id","supplier_name","amount","invoice_id","invoice_number"}
    (JSON-safe strings). Sets active_workflow and returns the opening
    question, same shape as payment_flow.start_payment_workflow.
    """
    loc = resolve_locale(company)
    company.active_workflow = "confirm_supplier_payment"
    company.workflow_scratch = {"step": "awaiting_paid_choice", "queue": queue, **item}
    return t(
        "reminder_confirm.ask_paid",
        loc,
        supplier=item["supplier_name"],
        amount=format_inr(Decimal(item["amount"])),
    )


def advance_reminder_queue(company: Company, queue: list[dict]) -> str:
    """Pop the next queued bill (if any) and start its confirm flow, so a
    same-tick batch of reminders gets asked about one at a time instead of
    only ever asking about the first. Returns "" when the queue is empty —
    callers append this to whatever message they were already sending.
    Synchronous/no DB access: only mutates the in-memory Company row, same
    as start_reminder_confirm.
    """
    if not queue:
        return ""
    next_item, *rest = queue
    return "\n\n" + start_reminder_confirm(company, next_item, rest)


def promote_queued_reminder(company: Company, context_id: str) -> bool:
    """Let a founder use WhatsApp's native quote-reply on any *queued* (not
    yet active) reminder message and have it jump ahead of whichever bill is
    currently being asked about — app/services/notifications.py::
    check_supplier_payment_reminders attaches each bill's own real wamid
    ("whatsapp_message_id") to its scratch entry, whether it's the active one
    or still sitting in "queue", specifically so this lookup is possible.

    Returns False (no-op, caller proceeds exactly as if this were never
    called) when: no reminder conversation is active at all; `context_id`
    matches the *already*-active item (nothing to promote — the normal path
    already handles this); or `context_id` matches nothing pending (an old,
    already-resolved, or unrelated message) — a wrong guess here must never
    corrupt a real in-progress conversation.

    On an actual match against a queued item: that item becomes the new
    active conversation (restarting fresh from its own first question,
    "awaiting_paid_choice" — any partial progress on the *previously*-active
    item, e.g. already having said "not yet" and being mid-reschedule, is
    discarded, not preserved, a deliberate simplification), and the
    previously-active item is put back at the front of the remaining queue
    so it's still asked about later, not lost.
    """
    if company.active_workflow != "confirm_supplier_payment":
        return False
    scratch = company.workflow_scratch or {}
    if scratch.get("whatsapp_message_id") == context_id:
        return False

    queue = scratch.get("queue", [])
    match_index = next(
        (i for i, item in enumerate(queue) if item.get("whatsapp_message_id") == context_id),
        None,
    )
    if match_index is None:
        return False

    matched_item = queue[match_index]
    rest = queue[:match_index] + queue[match_index + 1 :]
    previously_active = {
        key: value for key, value in scratch.items() if key not in ("step", "queue")
    }
    new_queue = [previously_active, *rest] if previously_active.get("supplier_name") else rest
    start_reminder_confirm(company, matched_item, new_queue)
    return True


async def handle_reminder_confirm_workflow_message(
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

    if stripped.lower() in _ORIENTATION_WORDS:
        # Doesn't cancel — the reminder is still waiting, just tell the
        # founder clearly what to do before their next message can go
        # through, instead of the generic "didn't understand, reply 1/2".
        return t("workflow.busy_reply_first", loc, question=_current_question(scratch, loc))

    if step == "awaiting_paid_choice":
        lowered = stripped.lower()
        if lowered in _YES_WORDS:
            scratch["step"] = "awaiting_amount_confirm"
            company.workflow_scratch = scratch
            return t(
                "reminder_confirm.amount_ask",
                loc,
                amount=format_inr(Decimal(scratch["amount"])),
            )
        if lowered in _NO_WORDS:
            scratch["step"] = "awaiting_reschedule"
            company.workflow_scratch = scratch
            return t("reminder_confirm.reschedule_ask", loc)
        return t(
            "reminder_confirm.invalid_choice",
            loc,
            supplier=scratch["supplier_name"],
            amount=format_inr(Decimal(scratch["amount"])),
        )

    if step == "awaiting_amount_confirm":
        lowered = stripped.lower()
        if lowered in ("", "ok", "yes", "y", "confirm"):
            amount = Decimal(scratch["amount"])
        else:
            try:
                amount = parse_amount(stripped)
            except ValueError:
                return t("reminder_confirm.amount_invalid", loc)
            if amount <= 0:
                return t("reminder_confirm.amount_positive", loc)

        today = business_now(company.timezone).date()
        supplier_name = scratch["supplier_name"]
        invoice_number = scratch.get("invoice_number")
        target = t("payment.target_invoice", loc, number=invoice_number) if invoice_number else ""

        # payment.preview's template has a {warning} placeholder — omitting
        # this kwarg used to make t() raise KeyError internally, caught, and
        # fall back to returning the RAW unformatted template (every
        # placeholder literal, e.g. "Confirm: {amount} {verb} {party}...")
        # straight into a live WhatsApp reply. Same duplicate-payment
        # advisory check payment_flow.py's own preview step already runs.
        warning = ""
        duplicate = await find_similar_payment(
            db,
            company_id=company.id,
            direction="payable",
            party_id=uuid.UUID(scratch["supplier_id"]),
            payment_date=today,
            amount=amount,
        )
        if duplicate is not None:
            warning = "\n" + t(
                "payment.duplicate_warning",
                loc,
                party=supplier_name,
                amount=format_inr(amount),
                date=today.isoformat(),
            )

        preview = t(
            "payment.preview",
            loc,
            amount=format_inr(amount),
            verb=t("payment.verb_to", loc),
            party=supplier_name,
            target=target,
            date=today.isoformat(),
            warning=warning,
        )
        await create_pending_operation(
            db,
            company,
            PendingOperationType.record_payment,
            {
                "direction": "payable",
                "party_name": supplier_name,
                "amount": str(amount),
                "payment_date": today.isoformat(),
                "invoice_id": scratch.get("invoice_id"),
                "reminder_queue": scratch.get("queue", []),
            },
        )
        company.active_workflow = None
        company.workflow_scratch = None
        return preview

    if step == "awaiting_reschedule":
        queue = scratch.get("queue", [])
        if _is(stripped, "skip"):
            company.active_workflow = None
            company.workflow_scratch = None
            return t("reminder_confirm.kept_due", loc) + advance_reminder_queue(company, queue)

        today = business_now(company.timezone).date()
        new_date = _parse_relative_date(stripped, today)
        if new_date is None:
            return t("reminder_confirm.reschedule_invalid", loc)

        supplier_name = scratch["supplier_name"]
        invoice_id_raw = scratch.get("invoice_id")
        invoice = await db.get(Invoice, uuid.UUID(invoice_id_raw)) if invoice_id_raw else None
        company.active_workflow = None
        company.workflow_scratch = None

        if invoice is None:
            return t("reminder_confirm.invoice_gone", loc) + advance_reminder_queue(company, queue)

        old_due = invoice.due_date.isoformat()
        invoice.due_date = new_date
        db.add(
            BusinessEvent(
                company_id=company.id,
                event_type=BusinessEventType.invoice_edited,
                entity_type="invoice",
                entity_id=invoice.id,
                payload={
                    "invoice_number": invoice.invoice_number,
                    "field": "due_date",
                    "old": old_due,
                    "new": new_date.isoformat(),
                    "reason": "rescheduled via payment reminder reply",
                },
                created_by="whatsapp",
            )
        )
        message = t(
            "reminder_confirm.rescheduled", loc, supplier=supplier_name, date=new_date.isoformat()
        )
        return message + advance_reminder_queue(company, queue)

    # Unreachable in practice (every step above is exhaustive for this flow),
    # but never leave a company stuck in an unknown workflow step.
    company.active_workflow = None
    company.workflow_scratch = None
    return t("workflow.error_restart", loc, trigger="record payment")
