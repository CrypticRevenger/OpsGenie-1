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

from app.models.company import Company
from app.models.pending_operation import PendingOperation, PendingOperationType
from app.services.invoice_delivery import send_invoice_document
from app.services.invoice_pdf import generate_invoice_pdf
from app.services.money_format import format_inr
from app.services.writes.orders import create_order
from app.services.writes.payments import record_payment
from app.services.writes.update_gst import update_gst

logger = logging.getLogger(__name__)

PENDING_OPERATION_TTL_MINUTES = 30

_YES_WORDS = {"yes", "y", "1"}
_NO_WORDS = {"no", "n", "2", "cancel"}


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
    """
    await db.execute(delete(PendingOperation).where(PendingOperation.company_id == company.id))
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
    if op.operation_type == PendingOperationType.record_payment:
        payload = op.payload
        payload_invoice_id = payload.get("invoice_id")
        try:
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
            return f"Couldn't record that payment: {exc}. Please start again."

        await db.delete(op)
        _clear_active_pending_operation(company)
        verb = "from" if payload["direction"] == "receivable" else "to"
        invoices = ", ".join(result.invoice_numbers) or "—"
        return (
            f"✅ {format_inr(result.amount_allocated)} recorded {verb} {result.party_name}.\n"
            f"Invoices updated: {invoices}\n"
            f"Remaining outstanding: {format_inr(result.remaining_outstanding)}"
        )

    if op.operation_type == PendingOperationType.create_order:
        payload = op.payload
        try:
            result = await create_order(
                db,
                company,
                dealer_name=payload["dealer_name"],
                items=payload["items"],
            )
        except (ValueError, KeyError, TypeError) as exc:
            # Same reasoning as the record_payment branch above: a re-
            # validation failure (e.g. a product deleted between preview and
            # confirm, or a price genuinely missing) degrades to a friendly
            # reply rather than aborting the whole webhook batch's commit.
            await db.delete(op)
            _clear_active_pending_operation(company)
            return f"Couldn't create that order: {exc}. Please start again."

        await db.delete(op)
        _clear_active_pending_operation(company)
        lines = "\n".join(
            f"- {line.quantity} x {line.product_name} = {format_inr(line.line_total)}"
            for line in result.lines
        )
        warning = (
            f"\n⚠️ Stock now negative for: {', '.join(result.negative_stock_warnings)}"
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
        pdf_sent = False
        try:
            pdf_bytes = generate_invoice_pdf(company, result)
            pdf_sent = await send_invoice_document(db, company, result, pdf_bytes)
        except Exception:  # noqa: BLE001 - PDF is best-effort; the order is already written
            logger.exception(
                "Invoice %s: PDF generation/delivery failed (non-blocking).",
                result.invoice_number,
            )
        pdf_note = (
            f"\nPDF sent to {result.dealer_name}."
            if pdf_sent
            else f"\n(PDF not sent to {result.dealer_name} — no phone on file or WhatsApp "
            "delivery not yet configured.)"
        )

        return (
            f"✅ Order {result.invoice_number} created for {result.dealer_name}.\n{lines}\n"
            f"Subtotal: {format_inr(result.subtotal)}\n"
            f"GST: {format_inr(result.gst_amount)}\n"
            f"Total: {format_inr(result.total_amount)}{warning}{pdf_note}"
        )

    if op.operation_type == PendingOperationType.update_gst:
        payload = op.payload
        payload_gst_rate = payload.get("gst_rate")
        try:
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
            return f"Couldn't update GST: {exc}. Please start again."

        await db.delete(op)
        _clear_active_pending_operation(company)
        rate_text = f"{result.gst_rate}%" if result.gst_rate is not None else "the company default"
        target = "all products" if result.scope == "all" else result.product_name
        return f"✅ GST for {target} set to {rate_text}."

    # Unreachable while PendingOperationType has no other members, but never
    # leave a company stuck on a confirmation type this code doesn't know yet.
    await db.delete(op)
    _clear_active_pending_operation(company)
    return "Something went wrong with that confirmation. Please start again."


async def handle_pending_operation_reply(
    db: AsyncSession, company: Company, op: PendingOperation, text: str
) -> str:
    stripped = text.strip().lower()
    if stripped in _YES_WORDS:
        return await execute_pending_operation(db, company, op)
    if stripped in _NO_WORDS:
        await db.delete(op)
        _clear_active_pending_operation(company)
        return "OK, cancelled."
    return "Reply YES to confirm or NO to cancel."
