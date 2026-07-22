"""InvoiceDueDateFollowUpService tests — Phase 9.

Real Postgres, same conventions as tests/test_snapshot.py (business-timezone
anchored TODAY) and tests/test_webhooks_whatsapp.py (unique per-test
whatsapp_number; real .env has no WhatsApp send credentials, so every send
genuinely raises WhatsAppNotConfiguredError — the fail-closed path is what's
actually exercised here, same as Phase 8's tests).

    uv run alembic upgrade head
    uv run pytest tests/test_followup_service.py -v
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from app.db.session import async_session_factory
from app.models.business_event import BusinessEvent, BusinessEventType
from app.models.company import Company, FollowUpState
from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceDirection, InvoiceSource, InvoiceStatus
from app.models.notification_log import NotificationLog
from app.models.payment import Payment
from app.models.pending_operation import PendingOperation, PendingOperationType
from app.services.followup import (
    _parse_relative_date,
    handle_follow_up_reply,
    send_due_today_follow_up,
)
from app.services.snapshot import DEFAULT_BUSINESS_TIMEZONE, business_now
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

TODAY = business_now(DEFAULT_BUSINESS_TIMEZONE).date()


@pytest.mark.parametrize("huge", ["9999999 days", "999999999999 days"])
def test_parse_relative_date_bounds_huge_day_counts(huge: str) -> None:
    # An unbounded "N days" would raise OverflowError inside
    # date + timedelta(days=N) and 500 the webhook. Beyond the ~10-year bound
    # it must return None (treated as unparseable, re-asked), never raise.
    assert _parse_relative_date(huge, TODAY) is None


def test_parse_relative_date_still_parses_reasonable_days() -> None:
    assert _parse_relative_date("5 days", TODAY) == TODAY + timedelta(days=5)


def _unique_phone() -> str:
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


async def _make_company(db: AsyncSession) -> Company:
    company = Company(
        business_name="Followup Test Co", owner_name="Owner", whatsapp_number=_unique_phone()
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company


async def _make_dealer(
    db: AsyncSession, company_id: uuid.UUID, name: str = "Ram Traders"
) -> Dealer:
    dealer = Dealer(company_id=company_id, name=name)
    db.add(dealer)
    await db.commit()
    await db.refresh(dealer)
    return dealer


async def _make_invoice(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    dealer_id: uuid.UUID,
    due_date,
    total_amount: Decimal = Decimal("49350.00"),
    status: InvoiceStatus = InvoiceStatus.Pending,
    expected_payment_date=None,
) -> Invoice:
    invoice = Invoice(
        company_id=company_id,
        invoice_number=f"INV-{uuid.uuid4().hex[:8]}",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        invoice_date=due_date - timedelta(days=30),
        due_date=due_date,
        subtotal=total_amount,
        gst_amount=Decimal("0.00"),
        total_amount=total_amount,
        status=status,
        source=InvoiceSource.csv_import,
        expected_payment_date=expected_payment_date,
    )
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)
    return invoice


# ── send_due_today_follow_up ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sends_follow_up_for_invoice_due_today(db: AsyncSession) -> None:
    company = await _make_company(db)
    dealer = await _make_dealer(db, company.id)
    invoice = await _make_invoice(db, company_id=company.id, dealer_id=dealer.id, due_date=TODAY)

    result = await send_due_today_follow_up(db, company.id)
    await db.commit()

    assert result.status == "sent"
    assert result.invoice_number == invoice.invoice_number

    await db.refresh(company)
    assert company.pending_follow_up_invoice_id == invoice.id
    assert company.pending_follow_up_state == FollowUpState.awaiting_confirmation
    assert company.pending_follow_up_created_at is not None

    log = await db.scalar(select(NotificationLog).where(NotificationLog.company_id == company.id))
    assert log is not None
    assert log.notification_type == "follow_up_sent"
    assert invoice.invoice_number in log.message_text

    event = await db.scalar(
        select(BusinessEvent).where(
            BusinessEvent.company_id == company.id,
            BusinessEvent.event_type == BusinessEventType.follow_up_sent,
        )
    )
    assert event is not None
    assert event.payload["invoice_number"] == invoice.invoice_number


@pytest.mark.asyncio
async def test_no_op_when_already_pending(db: AsyncSession) -> None:
    company = await _make_company(db)
    dealer = await _make_dealer(db, company.id)
    other_invoice = await _make_invoice(
        db, company_id=company.id, dealer_id=dealer.id, due_date=TODAY
    )
    company.pending_follow_up_invoice_id = other_invoice.id
    company.pending_follow_up_state = FollowUpState.awaiting_confirmation
    await db.commit()

    result = await send_due_today_follow_up(db, company.id)
    assert result.status == "already_pending"


@pytest.mark.asyncio
async def test_no_op_when_none_due(db: AsyncSession) -> None:
    company = await _make_company(db)
    dealer = await _make_dealer(db, company.id)
    await _make_invoice(
        db, company_id=company.id, dealer_id=dealer.id, due_date=TODAY + timedelta(days=5)
    )

    result = await send_due_today_follow_up(db, company.id)
    assert result.status == "none_due"


@pytest.mark.asyncio
async def test_matches_expected_payment_date_today(db: AsyncSession) -> None:
    company = await _make_company(db)
    dealer = await _make_dealer(db, company.id)
    invoice = await _make_invoice(
        db,
        company_id=company.id,
        dealer_id=dealer.id,
        due_date=TODAY - timedelta(days=20),
        expected_payment_date=TODAY,
    )

    result = await send_due_today_follow_up(db, company.id)
    assert result.status == "sent"
    assert result.invoice_number == invoice.invoice_number


@pytest.mark.asyncio
async def test_picks_oldest_invoice_when_multiple_due(db: AsyncSession) -> None:
    company = await _make_company(db)
    dealer = await _make_dealer(db, company.id)
    older = await _make_invoice(db, company_id=company.id, dealer_id=dealer.id, due_date=TODAY)
    older.invoice_date = TODAY - timedelta(days=60)
    newer = await _make_invoice(db, company_id=company.id, dealer_id=dealer.id, due_date=TODAY)
    newer.invoice_date = TODAY - timedelta(days=10)
    await db.commit()

    result = await send_due_today_follow_up(db, company.id)
    assert result.invoice_number == older.invoice_number


# ── handle_follow_up_reply: awaiting_confirmation ────────────────────────────


async def _start_follow_up(db: AsyncSession, company: Company, invoice: Invoice) -> None:
    company.pending_follow_up_invoice_id = invoice.id
    company.pending_follow_up_state = FollowUpState.awaiting_confirmation
    company.pending_follow_up_created_at = business_now(company.timezone)
    await db.commit()
    await db.refresh(company)


@pytest.mark.asyncio
async def test_full_payment_confirmation_closes_invoice(db: AsyncSession) -> None:
    company = await _make_company(db)
    dealer = await _make_dealer(db, company.id, name="Ram Traders")
    invoice = await _make_invoice(
        db,
        company_id=company.id,
        dealer_id=dealer.id,
        due_date=TODAY,
        total_amount=Decimal("49350.00"),
    )
    await _start_follow_up(db, company, invoice)

    reply = await handle_follow_up_reply(db, company, "1")
    await db.commit()

    assert "49,350" in reply
    assert "closed" in reply
    await db.refresh(invoice)
    assert invoice.status == InvoiceStatus.Paid
    assert company.pending_follow_up_invoice_id is None
    assert company.pending_follow_up_state is None

    payment = await db.scalar(select(Payment).where(Payment.invoice_id == invoice.id))
    assert payment is not None
    assert payment.amount == Decimal("49350.00")

    responded = await db.scalar(
        select(BusinessEvent).where(
            BusinessEvent.company_id == company.id,
            BusinessEvent.event_type == BusinessEventType.follow_up_responded,
        )
    )
    assert responded is not None
    assert responded.payload["response"] == "full"


@pytest.mark.asyncio
async def test_partial_payment_flow(db: AsyncSession) -> None:
    company = await _make_company(db)
    dealer = await _make_dealer(db, company.id)
    invoice = await _make_invoice(
        db,
        company_id=company.id,
        dealer_id=dealer.id,
        due_date=TODAY,
        total_amount=Decimal("49350.00"),
    )
    await _start_follow_up(db, company, invoice)

    ask = await handle_follow_up_reply(db, company, "2")
    await db.commit()
    assert "How much" in ask
    assert company.pending_follow_up_state == FollowUpState.awaiting_partial_amount
    assert company.pending_follow_up_invoice_id == invoice.id

    reply = await handle_follow_up_reply(db, company, "25000")
    await db.commit()

    assert "25,000" in reply
    assert "24,350" in reply
    await db.refresh(invoice)
    assert invoice.status == InvoiceStatus.Partially_Paid
    assert company.pending_follow_up_invoice_id is None
    assert company.pending_follow_up_state is None


@pytest.mark.asyncio
async def test_partial_payment_amount_at_or_above_outstanding_caps_and_closes(
    db: AsyncSession,
) -> None:
    company = await _make_company(db)
    dealer = await _make_dealer(db, company.id)
    invoice = await _make_invoice(
        db,
        company_id=company.id,
        dealer_id=dealer.id,
        due_date=TODAY,
        total_amount=Decimal("49350.00"),
    )
    await _start_follow_up(db, company, invoice)
    await handle_follow_up_reply(db, company, "2")
    await db.commit()

    reply = await handle_follow_up_reply(db, company, "50000")
    await db.commit()

    assert "closed" in reply
    await db.refresh(invoice)
    assert invoice.status == InvoiceStatus.Paid
    payment = await db.scalar(select(Payment).where(Payment.invoice_id == invoice.id))
    assert payment.amount == Decimal("49350.00")  # capped, not the literal 50000 sent


@pytest.mark.asyncio
async def test_unparseable_partial_amount_reasks_without_changing_state(
    db: AsyncSession,
) -> None:
    company = await _make_company(db)
    dealer = await _make_dealer(db, company.id)
    invoice = await _make_invoice(db, company_id=company.id, dealer_id=dealer.id, due_date=TODAY)
    await _start_follow_up(db, company, invoice)
    await handle_follow_up_reply(db, company, "2")
    await db.commit()

    reply = await handle_follow_up_reply(db, company, "not a number")
    await db.commit()

    assert "didn't understand" in reply
    assert company.pending_follow_up_state == FollowUpState.awaiting_partial_amount
    assert company.pending_follow_up_invoice_id == invoice.id
    payment_count = len(
        (await db.scalars(select(Payment).where(Payment.invoice_id == invoice.id))).all()
    )
    assert payment_count == 0


# ── handle_follow_up_reply: not-yet-received / date parsing ──────────────────


@pytest.mark.asyncio
async def test_not_yet_received_tomorrow(db: AsyncSession) -> None:
    company = await _make_company(db)
    dealer = await _make_dealer(db, company.id)
    invoice = await _make_invoice(db, company_id=company.id, dealer_id=dealer.id, due_date=TODAY)
    await _start_follow_up(db, company, invoice)

    ask = await handle_follow_up_reply(db, company, "3")
    await db.commit()
    assert "When do you expect" in ask
    assert company.pending_follow_up_state == FollowUpState.awaiting_expected_date

    reply = await handle_follow_up_reply(db, company, "tomorrow")
    await db.commit()

    assert "Noted" in reply
    await db.refresh(invoice)
    assert invoice.expected_payment_date == TODAY + timedelta(days=1)
    assert company.pending_follow_up_invoice_id is None


@pytest.mark.asyncio
async def test_not_yet_received_n_days(db: AsyncSession) -> None:
    company = await _make_company(db)
    dealer = await _make_dealer(db, company.id)
    invoice = await _make_invoice(db, company_id=company.id, dealer_id=dealer.id, due_date=TODAY)
    await _start_follow_up(db, company, invoice)
    await handle_follow_up_reply(db, company, "3")
    await db.commit()

    await handle_follow_up_reply(db, company, "3 days")
    await db.commit()

    await db.refresh(invoice)
    assert invoice.expected_payment_date == TODAY + timedelta(days=3)


@pytest.mark.asyncio
async def test_not_yet_received_next_week(db: AsyncSession) -> None:
    company = await _make_company(db)
    dealer = await _make_dealer(db, company.id)
    invoice = await _make_invoice(db, company_id=company.id, dealer_id=dealer.id, due_date=TODAY)
    await _start_follow_up(db, company, invoice)
    await handle_follow_up_reply(db, company, "3")
    await db.commit()

    await handle_follow_up_reply(db, company, "next week")
    await db.commit()

    await db.refresh(invoice)
    assert invoice.expected_payment_date == TODAY + timedelta(days=7)


@pytest.mark.asyncio
async def test_not_yet_received_weekday_name_next_occurrence(db: AsyncSession) -> None:
    """Saying tomorrow's weekday name means tomorrow (or later this week),
    never today — computed dynamically since the test's "today" is real.
    """
    company = await _make_company(db)
    dealer = await _make_dealer(db, company.id)
    invoice = await _make_invoice(db, company_id=company.id, dealer_id=dealer.id, due_date=TODAY)
    await _start_follow_up(db, company, invoice)
    await handle_follow_up_reply(db, company, "3")
    await db.commit()

    target_date = TODAY + timedelta(days=1)
    weekday_name = target_date.strftime("%A")

    await handle_follow_up_reply(db, company, weekday_name)
    await db.commit()

    await db.refresh(invoice)
    assert invoice.expected_payment_date == target_date


@pytest.mark.asyncio
async def test_not_yet_received_todays_own_weekday_means_next_week(db: AsyncSession) -> None:
    """Naming today's own weekday must mean next week, not today — "today"
    is said explicitly for the immediate case.
    """
    company = await _make_company(db)
    dealer = await _make_dealer(db, company.id)
    invoice = await _make_invoice(db, company_id=company.id, dealer_id=dealer.id, due_date=TODAY)
    await _start_follow_up(db, company, invoice)
    await handle_follow_up_reply(db, company, "3")
    await db.commit()

    todays_weekday_name = TODAY.strftime("%A")
    await handle_follow_up_reply(db, company, todays_weekday_name)
    await db.commit()

    await db.refresh(invoice)
    assert invoice.expected_payment_date == TODAY + timedelta(days=7)


@pytest.mark.asyncio
async def test_unparseable_date_reasks_without_changing_state(db: AsyncSession) -> None:
    company = await _make_company(db)
    dealer = await _make_dealer(db, company.id)
    invoice = await _make_invoice(db, company_id=company.id, dealer_id=dealer.id, due_date=TODAY)
    await _start_follow_up(db, company, invoice)
    await handle_follow_up_reply(db, company, "3")
    await db.commit()

    reply = await handle_follow_up_reply(db, company, "after Diwali")
    await db.commit()

    assert "didn't understand" in reply
    assert company.pending_follow_up_state == FollowUpState.awaiting_expected_date
    await db.refresh(invoice)
    assert invoice.expected_payment_date is None


# ── handle_follow_up_reply: unrecognized confirmation ────────────────────────


@pytest.mark.asyncio
async def test_unrecognized_confirmation_reply_reasks(db: AsyncSession) -> None:
    company = await _make_company(db)
    dealer = await _make_dealer(db, company.id)
    invoice = await _make_invoice(db, company_id=company.id, dealer_id=dealer.id, due_date=TODAY)
    await _start_follow_up(db, company, invoice)

    reply = await handle_follow_up_reply(db, company, "maybe")
    await db.commit()

    assert "Reply 1, 2, or 3" in reply
    assert company.pending_follow_up_state == FollowUpState.awaiting_confirmation
    assert company.pending_follow_up_invoice_id == invoice.id


# ── Code-review fixes: negative amounts, stale pointers, concurrent claims ──


@pytest.mark.asyncio
async def test_negative_partial_amount_rejected(db: AsyncSession) -> None:
    company = await _make_company(db)
    dealer = await _make_dealer(db, company.id)
    invoice = await _make_invoice(db, company_id=company.id, dealer_id=dealer.id, due_date=TODAY)
    await _start_follow_up(db, company, invoice)
    await handle_follow_up_reply(db, company, "2")
    await db.commit()

    reply = await handle_follow_up_reply(db, company, "-500")
    await db.commit()

    assert "didn't understand" in reply
    assert company.pending_follow_up_state == FollowUpState.awaiting_partial_amount
    payment_count = len(
        (await db.scalars(select(Payment).where(Payment.invoice_id == invoice.id))).all()
    )
    assert payment_count == 0


@pytest.mark.asyncio
async def test_zero_partial_amount_rejected(db: AsyncSession) -> None:
    company = await _make_company(db)
    dealer = await _make_dealer(db, company.id)
    invoice = await _make_invoice(db, company_id=company.id, dealer_id=dealer.id, due_date=TODAY)
    await _start_follow_up(db, company, invoice)
    await handle_follow_up_reply(db, company, "2")
    await db.commit()

    reply = await handle_follow_up_reply(db, company, "0")
    await db.commit()

    assert "didn't understand" in reply
    assert company.pending_follow_up_state == FollowUpState.awaiting_partial_amount


@pytest.mark.asyncio
async def test_stale_pending_invoice_closed_elsewhere_unblocks_new_follow_up(
    db: AsyncSession,
) -> None:
    """The invoice a follow-up is pending on gets paid off through a
    different channel (e.g. a CSV import) — send_due_today_follow_up must
    notice it's no longer open, clear the stale pointer, and pick up a new
    due-today invoice instead of staying wedged on "already_pending" forever.
    """
    company = await _make_company(db)
    dealer = await _make_dealer(db, company.id)
    stale_invoice = await _make_invoice(
        db, company_id=company.id, dealer_id=dealer.id, due_date=TODAY - timedelta(days=5)
    )
    await _start_follow_up(db, company, stale_invoice)

    # Closed through another channel entirely — not via handle_follow_up_reply.
    stale_invoice.status = InvoiceStatus.Paid
    await db.commit()

    new_invoice = await _make_invoice(
        db, company_id=company.id, dealer_id=dealer.id, due_date=TODAY
    )

    result = await send_due_today_follow_up(db, company.id)
    await db.commit()

    assert result.status == "sent"
    assert result.invoice_number == new_invoice.invoice_number
    await db.refresh(company)
    assert company.pending_follow_up_invoice_id == new_invoice.id


@pytest.mark.asyncio
async def test_stale_pending_invoice_closed_elsewhere_unblocks_reply_handling(
    db: AsyncSession,
) -> None:
    company = await _make_company(db)
    dealer = await _make_dealer(db, company.id)
    invoice = await _make_invoice(db, company_id=company.id, dealer_id=dealer.id, due_date=TODAY)
    await _start_follow_up(db, company, invoice)

    invoice.status = InvoiceStatus.Paid
    await db.commit()

    reply = await handle_follow_up_reply(db, company, "1")
    await db.commit()

    assert "no longer available" in reply
    assert company.pending_follow_up_invoice_id is None
    payment_count = len(
        (await db.scalars(select(Payment).where(Payment.invoice_id == invoice.id))).all()
    )
    assert payment_count == 0


@pytest.mark.asyncio
async def test_concurrent_send_attempts_only_one_wins(db: AsyncSession) -> None:
    """Two genuinely independent DB sessions call send_due_today_follow_up
    for the same company at the same time (asyncio.gather, not sequential
    calls) — Postgres serializes the two conditional UPDATEs on the same row,
    so exactly one claims the follow-up slot and sends; the other must see
    "already_pending", never a duplicate real send.
    """
    company = await _make_company(db)
    dealer = await _make_dealer(db, company.id)
    await _make_invoice(db, company_id=company.id, dealer_id=dealer.id, due_date=TODAY)
    company_id = company.id

    async def _attempt() -> str:
        async with async_session_factory() as session:
            result = await send_due_today_follow_up(session, company_id)
            await session.commit()
            return result.status

    results = await asyncio.gather(_attempt(), _attempt())
    assert sorted(results) == ["already_pending", "sent"]


@pytest.mark.asyncio
async def test_no_op_when_a_pending_operation_is_awaiting_confirmation(
    db: AsyncSession,
) -> None:
    """A follow-up must never be pushed on top of a live YES/NO confirm gate.

    Regression: the slot claim only checked pending_follow_up_invoice_id, so a
    follow-up could arrive while an order/payment sat at "Reply YES to
    confirm". The webhook dispatches pending operations *ahead* of follow-ups,
    so the founder's "1" (meaning "the dealer paid in full") landed in
    _YES_WORDS and executed the pending write instead — creating the order and
    silently dropping the payment they meant to record.
    """
    company = await _make_company(db)
    dealer = await _make_dealer(db, company.id)
    await _make_invoice(db, company_id=company.id, dealer_id=dealer.id, due_date=TODAY)

    op = PendingOperation(
        company_id=company.id,
        operation_type=PendingOperationType.create_order,
        payload={},
        expires_at=business_now(DEFAULT_BUSINESS_TIMEZONE) + timedelta(minutes=30),
    )
    db.add(op)
    await db.flush()
    company.active_pending_operation_id = op.id
    await db.commit()

    result = await send_due_today_follow_up(db, company.id)

    assert result.status == "conversation_busy"
    await db.refresh(company)
    # The follow-up slot stays empty, so the pending confirm still owns the
    # conversation and no follow-up message was sent.
    assert company.pending_follow_up_invoice_id is None
    assert company.active_pending_operation_id == op.id
    sent = (
        await db.execute(
            select(NotificationLog).where(
                NotificationLog.company_id == company.id,
                NotificationLog.notification_type == "follow_up_sent",
            )
        )
    ).scalars().all()
    assert sent == []


@pytest.mark.asyncio
async def test_no_op_when_a_guided_workflow_is_active(db: AsyncSession) -> None:
    company = await _make_company(db)
    dealer = await _make_dealer(db, company.id)
    await _make_invoice(db, company_id=company.id, dealer_id=dealer.id, due_date=TODAY)
    company.active_workflow = "record_payment"
    await db.commit()

    result = await send_due_today_follow_up(db, company.id)

    assert result.status == "conversation_busy"
    await db.refresh(company)
    assert company.pending_follow_up_invoice_id is None
