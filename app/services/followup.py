"""InvoiceDueDateFollowUpService — SPEC.md V0.1 Step 13.

"On the invoice due date, ask the distributor whether payment has been
received and route their reply back through the same business logic a
manually-recorded payment uses." Only one follow-up conversation is active
per company at a time (confirmed with the user during plan review — a
second invoice due the same day simply waits its turn), so the conversation
state lives on Company (pending_follow_up_invoice_id/state/created_at), not
per-invoice.

Not in scope here (SPEC Step 15, separate): automatic daily dispatch via
APScheduler. send_due_today_follow_up is called on demand today (the new
admin endpoint); a scheduler can call the exact same function later without
any change here.

Every multi-table write in this module (Payment + Invoice + Company +
ActivityTimeline + BusinessEvent) only ever calls db.add(...)/mutates
attributes — it never commits. The caller (the webhook or the admin
endpoint) commits once, so a mid-sequence failure can never leave partial
state (a Payment recorded but the invoice still Pending, or the company's
pending-follow-up pointer left dangling).

Two hardening details caught by code review, not the original design:
1. The pending-follow-up pointer can go stale if its target invoice is
   closed through a different channel (e.g. a CSV payment import) while the
   conversation is still "pending" — _clear_if_pending_invoice_already_closed
   and handle_follow_up_reply's own status check both revalidate the invoice
   is still open before acting, so a company never gets permanently wedged
   out of new follow-ups.
2. send_due_today_follow_up claims a company's follow-up slot with a single
   conditional UPDATE (WHERE pending_follow_up_invoice_id IS NULL) rather
   than a plain read-then-write, closing the race between two overlapping
   calls for the same company that could otherwise both send a real
   duplicate WhatsApp message before either commits.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import Locale, resolve_locale, t
from app.models.activity_timeline import ActivityEntityType, ActivityEventType, ActivityTimeline
from app.models.business_event import BusinessEvent, BusinessEventType
from app.models.company import Company, FollowUpState
from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceDirection, InvoiceStatus
from app.models.notification_log import NotificationLog
from app.models.payment import Payment, PaymentSource
from app.services.importer.normalizer import parse_amount
from app.services.money_format import format_inr
from app.services.snapshot import business_now
from app.services.whatsapp_client import (
    WhatsAppNotConfiguredError,
    WhatsAppSendError,
    send_text_message,
)

logger = logging.getLogger(__name__)

_OPEN_STATUSES = (InvoiceStatus.Pending, InvoiceStatus.Partially_Paid)

FollowUpSendStatus = Literal["sent", "already_pending", "none_due"]


@dataclass(frozen=True)
class FollowUpSendResult:
    status: FollowUpSendStatus
    invoice_number: str | None = None


# ── Deterministic relative-date parsing ──────────────────────────────────────
# Deliberately a small fixed vocabulary, per the user's explicit steer during
# plan review: never attempt to interpret open-ended phrases ("after Diwali",
# "month end", "salary day", "soon", "next Monday evening") — unparseable
# input just gets asked again with the same example line.

_WEEKDAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
_DAYS_PATTERN = re.compile(r"^(\d+)\s*days?$")
# An expected payment date more than ~10 years out is almost certainly a typo
# or pasted garbage (a phone number, a reference id), not a real answer — and,
# like payment_flow._parse_past_date's own _MAX_DAYS_AGO guard, this also keeps
# `today + timedelta(days=N)` from raising OverflowError on a huge N and 500ing
# the webhook.
_MAX_DAYS_AHEAD = 3650


def _parse_relative_date(text: str, today: date) -> date | None:
    cleaned = text.strip().lower()
    if cleaned == "today":
        return today
    if cleaned == "tomorrow":
        return today + timedelta(days=1)
    if cleaned == "next week":
        return today + timedelta(days=7)
    if cleaned in _WEEKDAYS:
        target_weekday = _WEEKDAYS.index(cleaned)
        delta = (target_weekday - today.weekday()) % 7
        # Naming today's own weekday means next week's occurrence, not "today"
        # — "today"/"tomorrow" already cover the immediate cases explicitly.
        delta = delta or 7
        return today + timedelta(days=delta)
    match = _DAYS_PATTERN.match(cleaned)
    if match:
        days = int(match.group(1))
        if days > _MAX_DAYS_AHEAD:
            return None
        return today + timedelta(days=days)
    return None


async def _invoice_paid_amount(db: AsyncSession, invoice_id: uuid.UUID) -> Decimal:
    paid = await db.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.invoice_id == invoice_id)
    )
    return Decimal(paid)


def _follow_up_message(
    invoice: Invoice, dealer_name: str, outstanding: Decimal, loc: Locale
) -> str:
    return t(
        "followup.message",
        loc,
        number=invoice.invoice_number,
        dealer=dealer_name,
        amount=format_inr(outstanding),
    )


async def _clear_if_pending_invoice_already_closed(db: AsyncSession, company: Company) -> None:
    """A follow-up's target invoice can be closed through a different channel
    entirely (e.g. an ordinary CSV payment import pays it off) while the
    conversation is still marked pending — without this check, the company
    would be wedged out of new follow-ups forever, and an eventual "1" reply
    would record a spurious ₹0 payment against an already-closed invoice.
    """
    if company.pending_follow_up_invoice_id is None:
        return
    invoice = await db.get(Invoice, company.pending_follow_up_invoice_id)
    if invoice is None or invoice.status not in _OPEN_STATUSES:
        _clear_pending_follow_up(company)
        await db.flush()


async def send_due_today_follow_up(db: AsyncSession, company_id: uuid.UUID) -> FollowUpSendResult:
    company = await db.get(Company, company_id)
    if company is None:
        raise ValueError(f"Company {company_id} not found")

    await _clear_if_pending_invoice_already_closed(db, company)
    if company.pending_follow_up_invoice_id is not None:
        return FollowUpSendResult(status="already_pending")

    today = business_now(company.timezone).date()
    stmt = (
        select(Invoice)
        .where(
            Invoice.company_id == company_id,
            Invoice.direction == InvoiceDirection.receivable,
            Invoice.status.in_(_OPEN_STATUSES),
            (Invoice.due_date == today) | (Invoice.expected_payment_date == today),
        )
        .order_by(Invoice.invoice_date)
        .limit(1)
    )
    invoice = (await db.execute(stmt)).scalars().first()
    if invoice is None:
        return FollowUpSendResult(status="none_due")

    # Atomically claim this company's follow-up slot: only proceed if
    # pending_follow_up_invoice_id is still NULL at the exact moment of this
    # UPDATE. Closes the race between two overlapping calls for the same
    # company (a retried admin trigger, or a future scheduler tick
    # overlapping a manual one) — a plain read-then-write here could let both
    # send a real duplicate WhatsApp message before either commits.
    claimed = await db.execute(
        update(Company)
        .where(Company.id == company_id, Company.pending_follow_up_invoice_id.is_(None))
        .values(
            pending_follow_up_invoice_id=invoice.id,
            pending_follow_up_state=FollowUpState.awaiting_confirmation,
            pending_follow_up_created_at=business_now(company.timezone),
        )
    )
    if claimed.rowcount == 0:
        return FollowUpSendResult(status="already_pending")
    # Keep the in-memory object in sync with the Core-level UPDATE above
    # (bypassing the ORM doesn't update company's already-loaded attributes).
    company.pending_follow_up_invoice_id = invoice.id
    company.pending_follow_up_state = FollowUpState.awaiting_confirmation
    company.pending_follow_up_created_at = business_now(company.timezone)

    dealer_name = (
        await db.scalar(select(Dealer.name).where(Dealer.id == invoice.dealer_id)) or "the dealer"
    )
    outstanding = invoice.total_amount - await _invoice_paid_amount(db, invoice.id)
    message = _follow_up_message(invoice, dealer_name, outstanding, resolve_locale(company))

    send_result = None
    try:
        send_result = await send_text_message(company.whatsapp_number, message)
    except (WhatsAppNotConfiguredError, WhatsAppSendError) as exc:
        logger.warning("Follow-up send to %s not sent: %s", company.whatsapp_number, exc)

    db.add(
        NotificationLog(
            company_id=company_id,
            notification_type="follow_up_sent",
            recipient_whatsapp=company.whatsapp_number,
            message_text=message,
            whatsapp_message_id=send_result.message_id if send_result else None,
            delivery_status="sent" if send_result else "failed_to_send",
        )
    )
    db.add(
        BusinessEvent(
            company_id=company_id,
            event_type=BusinessEventType.follow_up_sent,
            entity_type="invoice",
            entity_id=invoice.id,
            payload={
                "invoice_number": invoice.invoice_number,
                "dealer_name": dealer_name,
                "outstanding": str(outstanding),
            },
            created_by="followup_service",
        )
    )
    db.add(
        ActivityTimeline(
            company_id=company_id,
            entity_type=ActivityEntityType.dealer,
            entity_id=invoice.dealer_id,
            event_type=ActivityEventType.follow_up_sent,
            amount=outstanding,
            notes=f"Follow-up sent for {invoice.invoice_number}",
        )
    )

    return FollowUpSendResult(status="sent", invoice_number=invoice.invoice_number)


def _clear_pending_follow_up(company: Company) -> None:
    company.pending_follow_up_invoice_id = None
    company.pending_follow_up_state = None
    company.pending_follow_up_created_at = None


async def _record_payment_and_close(
    db: AsyncSession,
    *,
    company: Company,
    invoice: Invoice,
    dealer_name: str,
    amount: Decimal,
    outstanding_before: Decimal,
) -> str:
    today = business_now(company.timezone).date()
    payment = Payment(
        company_id=company.id,
        invoice_id=invoice.id,
        amount=amount,
        payment_date=today,
        source=PaymentSource.whatsapp,
    )
    db.add(payment)
    remaining = outstanding_before - amount
    invoice.status = InvoiceStatus.Paid if remaining <= 0 else InvoiceStatus.Partially_Paid

    db.add(
        BusinessEvent(
            company_id=company.id,
            event_type=BusinessEventType.payment_received,
            entity_type="invoice",
            entity_id=invoice.id,
            payload={
                "invoice_number": invoice.invoice_number,
                "dealer_name": dealer_name,
                "amount": str(amount),
                "source": "whatsapp_follow_up",
            },
            created_by="followup_service",
        )
    )
    db.add(
        BusinessEvent(
            company_id=company.id,
            event_type=BusinessEventType.follow_up_responded,
            entity_type="invoice",
            entity_id=invoice.id,
            payload={"response": "full" if remaining <= 0 else "partial", "amount": str(amount)},
            created_by="followup_service",
        )
    )
    db.add(
        ActivityTimeline(
            company_id=company.id,
            entity_type=ActivityEntityType.dealer,
            entity_id=invoice.dealer_id,
            event_type=ActivityEventType.payment_received,
            amount=amount,
            notes=f"Payment recorded via follow-up for {invoice.invoice_number}",
        )
    )

    _clear_pending_follow_up(company)

    loc = resolve_locale(company)
    if remaining <= 0:
        return t(
            "followup.recorded_full",
            loc,
            amount=format_inr(amount),
            dealer=dealer_name,
            number=invoice.invoice_number,
        )
    return t(
        "followup.recorded_partial",
        loc,
        amount=format_inr(amount),
        number=invoice.invoice_number,
        remaining=format_inr(remaining),
    )


async def handle_follow_up_reply(db: AsyncSession, company: Company, text: str) -> str:
    """Called by the webhook whenever company.pending_follow_up_invoice_id is
    set — before menu_router.match, so a bare "1"/"2"/"3" is interpreted as
    this conversation's answer, never a numbered-menu command.
    """
    loc = resolve_locale(company)
    invoice = await db.get(Invoice, company.pending_follow_up_invoice_id)
    if invoice is None or invoice.status not in _OPEN_STATUSES:
        # Deleted, or already closed through a different channel (e.g. a
        # CSV payment import) while this conversation was in flight — clear
        # the pointer rather than recording a spurious payment against an
        # invoice that's no longer open.
        _clear_pending_follow_up(company)
        return t("followup.invoice_gone", loc, menu_prompt=t("menu.prompt", loc))

    dealer_name = (
        await db.scalar(select(Dealer.name).where(Dealer.id == invoice.dealer_id)) or "the dealer"
    )
    stripped = text.strip()

    if company.pending_follow_up_state == FollowUpState.awaiting_confirmation:
        if stripped == "1":
            outstanding = invoice.total_amount - await _invoice_paid_amount(db, invoice.id)
            return await _record_payment_and_close(
                db,
                company=company,
                invoice=invoice,
                dealer_name=dealer_name,
                amount=outstanding,
                outstanding_before=outstanding,
            )
        if stripped == "2":
            company.pending_follow_up_state = FollowUpState.awaiting_partial_amount
            return t("followup.ask_partial", loc)
        if stripped == "3":
            company.pending_follow_up_state = FollowUpState.awaiting_expected_date
            return t("followup.ask_expected_date", loc, dealer=dealer_name)
        return t("followup.confirm_invalid", loc)

    if company.pending_follow_up_state == FollowUpState.awaiting_partial_amount:
        try:
            amount = parse_amount(stripped)
        except ValueError:
            return t("followup.amount_invalid", loc)
        if amount <= 0:
            return t("followup.amount_invalid", loc)
        outstanding = invoice.total_amount - await _invoice_paid_amount(db, invoice.id)
        capped_amount = min(amount, outstanding)
        return await _record_payment_and_close(
            db,
            company=company,
            invoice=invoice,
            dealer_name=dealer_name,
            amount=capped_amount,
            outstanding_before=outstanding,
        )

    if company.pending_follow_up_state == FollowUpState.awaiting_expected_date:
        today = business_now(company.timezone).date()
        parsed = _parse_relative_date(stripped, today)
        if parsed is None:
            return t("followup.date_invalid", loc)
        invoice.expected_payment_date = parsed
        db.add(
            BusinessEvent(
                company_id=company.id,
                event_type=BusinessEventType.follow_up_responded,
                entity_type="invoice",
                entity_id=invoice.id,
                payload={"response": "not_yet", "expected_payment_date": parsed.isoformat()},
                created_by="followup_service",
            )
        )
        db.add(
            ActivityTimeline(
                company_id=company.id,
                entity_type=ActivityEntityType.dealer,
                entity_id=invoice.dealer_id,
                event_type=ActivityEventType.follow_up_responded,
                amount=None,
                notes=f"{invoice.invoice_number} follow-up rescheduled for {parsed.isoformat()}",
            )
        )
        _clear_pending_follow_up(company)
        return t(
            "followup.rescheduled",
            loc,
            number=invoice.invoice_number,
            when=stripped,
            dealer=dealer_name,
        )

    # Unreachable in practice (the three FollowUpState members are exhaustive),
    # but never leave the company stuck if state is somehow unset/unexpected.
    _clear_pending_follow_up(company)
    return t("followup.error", loc, menu_prompt=t("menu.prompt", loc))
