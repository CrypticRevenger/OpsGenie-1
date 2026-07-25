"""Generic write-confirmation gate — Phase 2A.

One PendingOperation row = one validated write awaiting the user's explicit
"YES". payload stores RAW user inputs only, never a pre-computed total, so
execute_pending_operation always re-derives the actual write fresh against
current DB state (an outstanding balance can move between preview and
confirm) rather than trusting what the preview showed. This module is the
reusable confirm mechanism every future write type (create_invoice in 2B,
and beyond) dispatches through — only execute_pending_operation's dispatch
needs a new branch per operation_type.

Company.active_pending_operation_id mirrors the existing
pending_follow_up_invoice_id pattern: an in-memory pointer so the webhook can
check "does this company have a pending confirmation" with a plain attribute
read, instead of an extra query on every inbound message for every company.
Every path that deletes a PendingOperation row also clears this pointer in
the same breath — the DB's ondelete=SET NULL is a backstop, not the primary
mechanism, since the in-memory Company object wouldn't otherwise reflect it
within the same request.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import resolve_locale, t
from app.models.company import Company
from app.models.pending_operation import PendingOperation, PendingOperationType
from app.services.importer.normalizer import parse_positive_amount
from app.services.invoice_delivery import send_invoice_document
from app.services.invoice_pdf import generate_invoice_pdf
from app.services.money_format import format_inr
from app.services.writes.broadcast import bulk_opt_in_all_dealers, send_broadcast
from app.services.writes.edit_invoice_payment import edit_invoice, edit_payment
from app.services.writes.orders import create_order
from app.services.writes.payments import record_payment
from app.services.writes.update_gst import update_gst
from app.services.writes.void import void_order, void_payment

logger = logging.getLogger(__name__)

PENDING_OPERATION_TTL_MINUTES = 30

_YES_WORDS = {"yes", "y", "1"}
_NO_WORDS = {"no", "n", "2", "cancel"}
# Narrower escape set for the awaiting_advance_amount sub-state only: "1"/"2"
# are also valid advance amounts there (a ₹1 or ₹2 advance is unlikely but
# not impossible), so they must fall through to amount-parsing instead of
# being swallowed as _YES_WORDS/_NO_WORDS shorthand — which would silently
# execute or cancel the whole order instead of erroring on/accepting the
# typed amount. Only the actual words still escape the amount parser.
_ADVANCE_AMOUNT_ESCAPE_YES = {"yes", "y"}
_ADVANCE_AMOUNT_ESCAPE_NO = {"no", "n", "cancel"}


def _clear_active_pending_operation(company: Company) -> None:
    company.active_pending_operation_id = None


async def create_pending_operation(
    db: AsyncSession,
    company: Company,
    operation_type: PendingOperationType,
    payload: dict,
) -> PendingOperation:
    """Create a new pending confirmation, replacing any stale one for this
    company — only one is ever meaningful at a time (the guided flow that
    creates this always clears active_workflow in the same step).

    Threads company.active_workflow_start_trigger (set by the webhook
    routing ladder when the now-ending guided flow started — see
    app/api/webhooks/whatsapp.py) into the payload as "start_trigger", since
    every call site here runs *before* the calling workflow clears
    active_workflow/active_workflow_start_trigger to None. This lets the
    webhook's generic "want to do that again?" continue-or-end offer
    (Company.pending_continue_prompt) work for every PendingOperation-gated
    flow (record_payment, create_order, update_gst, ...) without any of
    those workflow files needing to know about it themselves.
    """
    await db.execute(delete(PendingOperation).where(PendingOperation.company_id == company.id))
    if "start_trigger" not in payload:
        payload = {**payload, "start_trigger": company.active_workflow_start_trigger}
    company.active_workflow_start_trigger = None
    op = PendingOperation(
        company_id=company.id,
        operation_type=operation_type,
        payload=payload,
        expires_at=datetime.now(UTC) + timedelta(minutes=PENDING_OPERATION_TTL_MINUTES),
    )
    db.add(op)
    await db.flush()
    company.active_pending_operation_id = op.id
    return op


async def get_pending_operation(db: AsyncSession, op_id: uuid.UUID) -> PendingOperation | None:
    """Fetch a specific pending operation by id — the webhook already knows
    which one it wants via company.active_pending_operation_id, so this is a
    plain primary-key lookup, not a company-scoped query.
    """
    return await db.get(PendingOperation, op_id)


async def execute_pending_operation(
    db: AsyncSession, company: Company, op: PendingOperation
) -> str:
    """Dispatch by operation_type, then always remove the row — a definitive
    outcome (success or a re-validation failure) never leaves a stale
    confirmation a later "YES" could accidentally re-trigger.
    """
    loc = resolve_locale(company)
    if op.operation_type == PendingOperationType.record_payment:
        payload = op.payload
        payload_invoice_id = payload.get("invoice_id")
        # Only set when this confirmation originated from a supplier payment
        # reminder (app/services/workflows/payment_reminder_confirm.py) with
        # other same-tick bills queued behind it — see that module's
        # docstring. Not a normal record_payment field.
        reminder_queue = payload.get("reminder_queue")
        try:
            async with db.begin_nested():
                result = await record_payment(
                    db,
                    company,
                    direction=payload["direction"],
                    party_name=payload["party_name"],
                    amount=Decimal(payload["amount"]),
                    payment_date=date.fromisoformat(payload["payment_date"]),
                    invoice_id=uuid.UUID(payload_invoice_id) if payload_invoice_id else None,
                )
        except (ValueError, KeyError, TypeError) as exc:
            # ValueError covers the real re-validation failures
            # (allocate_payment_fifo's no-open-invoice / exceeds-outstanding).
            # KeyError/TypeError guard against a malformed payload — not
            # reachable today (the one creation site always populates all
            # four keys correctly), but this dispatch is designed to be
            # reused by future operation types, and a raw exception here
            # would abort the whole webhook batch's commit rather than
            # degrade to a friendly reply.
            await db.delete(op)
            _clear_active_pending_operation(company)
            message = t("pending.payment_failed", loc, error=exc)
            if reminder_queue:
                from app.services.workflows.payment_reminder_confirm import (
                    advance_reminder_queue,
                )

                message += advance_reminder_queue(company, reminder_queue)
            return message

        await db.delete(op)
        _clear_active_pending_operation(company)
        verb = (
            t("payment.verb_from", loc)
            if payload["direction"] == "receivable"
            else t("payment.verb_to", loc)
        )
        invoices = ", ".join(result.invoice_numbers) or "—"
        message = t(
            "pending.payment_success",
            loc,
            amount=format_inr(result.amount_allocated),
            verb=verb,
            party=result.party_name,
            invoices=invoices,
            outstanding=format_inr(result.remaining_outstanding),
        )
        if reminder_queue:
            from app.services.workflows.payment_reminder_confirm import advance_reminder_queue

            message += advance_reminder_queue(company, reminder_queue)
        return message

    if op.operation_type == PendingOperationType.create_order:
        payload = op.payload
        try:
            async with db.begin_nested():
                result = await create_order(
                    db,
                    company,
                    dealer_name=payload["dealer_name"],
                    items=payload["items"],
                    advance_paid=(
                        Decimal(payload["advance_paid"]) if payload.get("advance_paid") else None
                    ),
                    dealer_phone=payload.get("dealer_phone"),
                )
        except (ValueError, KeyError, TypeError) as exc:
            # Same reasoning as the record_payment branch above: a re-
            # validation failure (e.g. a product deleted between preview and
            # confirm, or a price genuinely missing) degrades to a friendly
            # reply rather than aborting the whole webhook batch's commit.
            #
            # The begin_nested() SAVEPOINT above is what makes that degradation
            # honest. create_order decrements stock and adds the Invoice +
            # InvoiceItems *before* it can raise on the advance's FIFO
            # allocation, and the webhook commits unconditionally at the end of
            # the request — so without the savepoint those partial mutations
            # were committed while this reply told the distributor the order
            # failed. Same pattern the CSV importers already use per row.
            await db.delete(op)
            _clear_active_pending_operation(company)
            return t("pending.order_failed", loc, error=exc)

        await db.delete(op)
        _clear_active_pending_operation(company)
        lines = "\n".join(
            t(
                "pending.order_line",
                loc,
                quantity=line.quantity,
                product=line.product_name,
                total=format_inr(line.line_total),
            )
            for line in result.lines
        )
        warning = (
            t(
                "pending.order_stock_warning",
                loc,
                products=", ".join(result.negative_stock_warnings),
            )
            if result.negative_stock_warnings
            else ""
        )

        # PDF generation/delivery is a bonus, never a blocker — the invoice
        # itself is already written above regardless of what happens here. Any
        # failure (e.g. an fpdf2 rendering error on a name the core font can't
        # encode) must degrade to "not sent", never propagate out: this runs
        # before the webhook's single db.commit(), so an escaped exception
        # would roll back the just-created order and land the request on Meta's
        # aggressive retry loop, wedging the distributor's confirmation forever.
        pdf_sent_to_dealer = False
        pdf_sent_to_founder = False
        try:
            pdf_bytes = generate_invoice_pdf(company, result)
            delivery = await send_invoice_document(db, company, result, pdf_bytes)
            pdf_sent_to_dealer = delivery.sent_to_dealer
            pdf_sent_to_founder = delivery.sent_to_founder
        except Exception:  # noqa: BLE001 - PDF is best-effort; the order is already written
            logger.exception(
                "Invoice %s: PDF generation/delivery failed (non-blocking).",
                result.invoice_number,
            )
        # send_invoice_document always attempts the founder copy, so the two
        # flags are no longer mutually exclusive (see invoice_delivery.py) —
        # "both" is now the common case for a dealer with a phone on file.
        if pdf_sent_to_dealer and pdf_sent_to_founder:
            pdf_note = t("pending.order_pdf_sent_both", loc, dealer=result.dealer_name)
        elif pdf_sent_to_dealer:
            pdf_note = t("pending.order_pdf_sent", loc, dealer=result.dealer_name)
        elif pdf_sent_to_founder:
            pdf_note = t("pending.order_pdf_sent_to_founder", loc, dealer=result.dealer_name)
        else:
            pdf_note = t("pending.order_pdf_not_sent", loc, dealer=result.dealer_name)

        return t(
            "pending.order_success",
            loc,
            number=result.invoice_number,
            dealer=result.dealer_name,
            lines=lines,
            subtotal=format_inr(result.subtotal),
            gst=format_inr(result.gst_amount),
            total=format_inr(result.total_amount),
            payment_made=format_inr(result.advance_paid),
            balance_due=format_inr(result.balance_due),
            warning=warning,
            pdf_note=pdf_note,
        )

    if op.operation_type == PendingOperationType.update_gst:
        payload = op.payload
        payload_gst_rate = payload.get("gst_rate")
        try:
            async with db.begin_nested():
                result = await update_gst(
                    db,
                    company,
                    scope=payload["scope"],
                    gst_rate=Decimal(payload_gst_rate) if payload_gst_rate is not None else None,
                    product_name=payload.get("product_name"),
                )
        except (ValueError, KeyError, TypeError) as exc:
            # Same reasoning as the record_payment/create_order branches
            # above: a re-validation failure (e.g. the product was deleted
            # between preview and confirm) degrades to a friendly reply
            # rather than aborting the whole webhook batch's commit.
            await db.delete(op)
            _clear_active_pending_operation(company)
            return t("pending.gst_failed", loc, error=exc)

        await db.delete(op)
        _clear_active_pending_operation(company)
        rate_text = (
            t("gst.rate_pct", loc, rate=result.gst_rate)
            if result.gst_rate is not None
            else t("pending.gst_rate_default", loc)
        )
        target = t("gst.all_products", loc) if result.scope == "all" else result.product_name
        return t("pending.gst_success", loc, target=target, rate=rate_text)

    if op.operation_type == PendingOperationType.void_payment:
        payload = op.payload
        try:
            async with db.begin_nested():
                result = await void_payment(
                    db,
                    company,
                    payment_id=uuid.UUID(payload["payment_id"]),
                    reason=payload.get("reason"),
                )
        except (ValueError, KeyError, TypeError) as exc:
            await db.delete(op)
            _clear_active_pending_operation(company)
            return t("pending.void_payment_failed", loc, error=exc)

        await db.delete(op)
        _clear_active_pending_operation(company)
        return t(
            "pending.void_payment_success",
            loc,
            amount=format_inr(result.amount),
            invoice_number=result.invoice_number,
            party=result.party_name,
        )

    if op.operation_type == PendingOperationType.void_order:
        payload = op.payload
        try:
            async with db.begin_nested():
                result = await void_order(
                    db,
                    company,
                    invoice_id=uuid.UUID(payload["invoice_id"]),
                    reason=payload.get("reason"),
                )
        except (ValueError, KeyError, TypeError) as exc:
            await db.delete(op)
            _clear_active_pending_operation(company)
            return t("pending.void_order_failed", loc, error=exc)

        await db.delete(op)
        _clear_active_pending_operation(company)
        return t(
            "pending.void_order_success",
            loc,
            invoice_number=result.invoice_number,
            dealer=result.dealer_name,
            total=format_inr(result.total_amount),
        )

    if op.operation_type == PendingOperationType.edit_invoice:
        payload = op.payload
        try:
            async with db.begin_nested():
                result = await edit_invoice(
                    db,
                    company,
                    invoice_id=uuid.UUID(payload["invoice_id"]),
                    field=payload["field"],
                    new_value=payload["new_value"],
                    reason=payload.get("reason"),
                )
        except (ValueError, KeyError, TypeError) as exc:
            await db.delete(op)
            _clear_active_pending_operation(company)
            return t("pending.edit_invoice_failed", loc, error=exc)

        await db.delete(op)
        _clear_active_pending_operation(company)
        return t(
            "pending.edit_invoice_success",
            loc,
            number=result.invoice_number,
            field=result.field,
            old=result.old_value,
            new=result.new_value,
        )

    if op.operation_type == PendingOperationType.edit_payment:
        payload = op.payload
        try:
            async with db.begin_nested():
                result = await edit_payment(
                    db,
                    company,
                    payment_id=uuid.UUID(payload["payment_id"]),
                    field=payload["field"],
                    new_value=payload["new_value"],
                    reason=payload.get("reason"),
                )
        except (ValueError, KeyError, TypeError) as exc:
            await db.delete(op)
            _clear_active_pending_operation(company)
            return t("pending.edit_payment_failed", loc, error=exc)

        await db.delete(op)
        _clear_active_pending_operation(company)
        return t(
            "pending.edit_payment_success",
            loc,
            number=result.invoice_number,
            field=result.field,
            old=result.old_value,
            new=result.new_value,
        )

    if op.operation_type == PendingOperationType.broadcast_dealers:
        payload = op.payload
        try:
            # Deliberately NOT wrapped in db.begin_nested() like every other
            # write branch here: send_broadcast commits per recipient by
            # design, and a savepoint around a function that commits would
            # defeat both. Its idempotency comes from batch_id instead — op.id
            # is stable across the Meta redelivery that a failed final commit
            # triggers, so a resumed broadcast skips dealers already messaged.
            result = await send_broadcast(
                db,
                company,
                segment=payload["segment"],
                dealer_ids=[uuid.UUID(d) for d in payload.get("dealer_ids", [])],
                message=payload["message"],
                batch_id=op.id,
            )
        except (ValueError, KeyError, TypeError) as exc:
            await db.delete(op)
            _clear_active_pending_operation(company)
            return t("pending.broadcast_failed", loc, error=exc)

        await db.delete(op)
        _clear_active_pending_operation(company)
        return t(
            "pending.broadcast_success",
            loc,
            sent=result.sent_count,
            failed=result.failed_count,
            total=result.attempted_count,
        )

    if op.operation_type == PendingOperationType.bulk_opt_in_dealers:
        try:
            async with db.begin_nested():
                count = await bulk_opt_in_all_dealers(db, company)
        except (ValueError, KeyError, TypeError) as exc:
            await db.delete(op)
            _clear_active_pending_operation(company)
            return t("pending.opt_in_all_failed", loc, error=exc)

        await db.delete(op)
        _clear_active_pending_operation(company)
        return t("pending.opt_in_all_success", loc, count=count)

    # Unreachable while every PendingOperationType member has a branch above,
    # but never leave a company stuck on a confirmation type this code
    # doesn't know yet — a future member added to the enum without a branch
    # here degrades to this instead of raising.
    await db.delete(op)
    _clear_active_pending_operation(company)
    return t("pending.unknown", loc)


async def handle_pending_operation_reply(
    db: AsyncSession, company: Company, op: PendingOperation, text: str
) -> str:
    stripped = text.strip().lower()
    loc = resolve_locale(company)

    if op.operation_type == PendingOperationType.create_order:
        # Local import: order_flow.py imports create_pending_operation from
        # this module, so importing it back at module level here would be a
        # circular import — same reason payment_reminder_confirm is imported
        # locally below, not at the top of this file.
        from app.services.workflows.order_flow import compute_order_math, render_order_preview

        if (
            op.payload.get("awaiting_advance_amount")
            and stripped not in _ADVANCE_AMOUNT_ESCAPE_YES
            and stripped not in _ADVANCE_AMOUNT_ESCAPE_NO
        ):
            try:
                advance = parse_positive_amount(text.strip())
            except ValueError:
                return t("order.advance_amount_invalid", loc)
            _subtotal, _gst_amount, total = compute_order_math(
                op.payload["items"], company.gst_rate
            )
            if advance > total:
                return t("order.advance_exceeds_total", loc, total=format_inr(total))
            op.payload = {
                **op.payload,
                "advance_paid": str(advance),
                "awaiting_advance_amount": False,
            }
            return render_order_preview(
                dealer_name=op.payload["dealer_name"],
                items=op.payload["items"],
                company_gst_rate=company.gst_rate,
                advance_paid=advance,
                duplicate_invoice_number=op.payload["duplicate_invoice_number"],
                credit_limit_breach=op.payload["credit_limit_breach"],
                loc=loc,
            )
        if stripped in ("advance", "add advance", "advance paid"):
            op.payload = {**op.payload, "awaiting_advance_amount": True}
            return t("order.advance_amount_ask", loc)

    if stripped in _YES_WORDS:
        return await execute_pending_operation(db, company, op)
    if stripped in _NO_WORDS:
        # A declined record_payment gets a chance to just fix the amount/date
        # instead of restarting the whole guided flow from the party name —
        # unless this confirmation came from a supplier-payment reminder
        # (payment_reminder_confirm.py's reminder_queue), where "no" correctly
        # means "not yet paid" and already has its own reschedule branch;
        # conflating the two would break that flow's semantics.
        if op.operation_type == PendingOperationType.record_payment and not op.payload.get(
            "reminder_queue"
        ):
            # Local import: payment_flow.py imports create_pending_operation
            # from this module, so importing it back at module level here
            # would be a circular import — same reason order_flow.py/
            # payment_reminder_confirm are imported locally elsewhere in
            # this file.
            from app.services.workflows.payment_flow import _amount_prompt

            payload = op.payload
            await db.delete(op)
            _clear_active_pending_operation(company)
            company.active_workflow = "record_payment"
            company.active_workflow_start_trigger = payload.get("start_trigger")
            company.workflow_scratch = {
                "step": "awaiting_amount",
                "direction": payload["direction"],
                "party_name": payload["party_name"],
                "invoice_id": payload.get("invoice_id"),
                "invoice_number": payload.get("invoice_number"),
            }
            question = _amount_prompt(payload["direction"], loc)
            return t("pending.payment_declined_amend", loc, question=question)

        # Reminder-triggered record_payment confirmations carry same-tick
        # bills queued behind them — see payment_reminder_confirm.py. A "no"
        # here still resolves this one (declined), so the next queued bill
        # should get its turn, same as the success/failure paths above.
        reminder_queue = (
            op.payload.get("reminder_queue")
            if op.operation_type == PendingOperationType.record_payment
            else None
        )
        await db.delete(op)
        _clear_active_pending_operation(company)
        message = t("workflow.cancelled", loc)
        if reminder_queue:
            from app.services.workflows.payment_reminder_confirm import advance_reminder_queue

            message += advance_reminder_queue(company, reminder_queue)
        return message
    if op.operation_type == PendingOperationType.create_order:
        # Reuse the preview's own footer wording (mentions YES/NO/ADVANCE)
        # rather than the generic yes/no-only fallback every other
        # operation type uses below.
        return t("order.preview_footer", loc)
    return t("pending.reply_yes_no", loc)
