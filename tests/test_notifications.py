"""NotificationEngine tests — Phase 10.

Real Postgres for the company/log rows (ActivityTimeline/BusinessEvent
entity_id have no FK, so supplier/dealer ids can be synthetic), but the
Snapshot each rule reads is hand-built rather than derived from build_snapshot
— that keeps each rule's trigger/dedup logic isolated and fast. send is always
monkeypatched: real Meta credentials now live in .env, so an unpatched send
would hit the real API.

    uv run alembic upgrade head
    uv run pytest tests/test_notifications.py -v
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from app.core.config import get_settings
from app.db.session import async_session_factory
from app.models.activity_timeline import ActivityEntityType, ActivityEventType, ActivityTimeline
from app.models.business_event import BusinessEvent, BusinessEventType
from app.models.company import Company, OnboardingState
from app.models.dealer import Dealer
from app.models.import_log import ImportLog
from app.models.invoice import Invoice, InvoiceDirection, InvoiceSource, InvoiceStatus
from app.models.invoice_item import InvoiceItem
from app.models.notification_log import NotificationLog
from app.models.product import Product
from app.services.notifications import (
    _MAX_SUPPLIER_REMINDERS_PER_TICK,
    check_cash_shortage_forecast,
    check_dealer_overdue_alerts,
    check_predue_invoice_nudges,
    check_stock_out_forecasts,
    check_supplier_payment_reminders,
    notify_briefing_failed,
    notify_briefing_generation_failed,
    run_notification_checks,
    send_founder_alert,
    send_stale_data_digest,
)
from app.services.snapshot import (
    DEFAULT_BUSINESS_TIMEZONE,
    CashDeficitForecast,
    DealerCollection,
    OverdueDealer,
    Snapshot,
    SupplierPayment,
    business_now,
)
from app.services.whatsapp_client import WhatsAppSendError, WhatsAppSendResult
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

NOW = business_now(DEFAULT_BUSINESS_TIMEZONE)
TODAY = NOW.date()


def _unique_phone() -> str:
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


async def _make_company(db: AsyncSession, *, name: str = "Notify Test Co") -> Company:
    company = Company(
        business_name=name, owner_name="Owner", whatsapp_number=_unique_phone()
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company


def _snapshot(company_id: uuid.UUID, **overrides) -> Snapshot:
    defaults = dict(
        company_id=company_id,
        generated_at=NOW,
        cash_available_today=Decimal("184000.00"),
        expected_collections_7d=[],
        expected_collections_7d_total=Decimal("0.00"),
        expected_payments_7d=[],
        expected_payments_7d_total=Decimal("0.00"),
        net_cash_position=Decimal("184000.00"),
        cash_deficit=False,
        overdue_dealers=[],
        data_freshness_hours=1.0,
        data_completeness_score=None,
        confidence_score=100.0,
    )
    defaults.update(overrides)
    return Snapshot(**defaults)


def _supplier_payment(**overrides) -> SupplierPayment:
    defaults = dict(
        supplier_id=uuid.uuid4(),
        supplier_name="Amul",
        amount=Decimal("82000.00"),
        due_date=TODAY + timedelta(days=1),
        urgent=True,
        invoice_id=uuid.uuid4(),
        invoice_number="INV-0001",
    )
    defaults.update(overrides)
    return SupplierPayment(**defaults)


def _overdue_dealer(**overrides) -> OverdueDealer:
    defaults = dict(
        dealer_id=uuid.uuid4(),
        dealer_name="XYZ Traders",
        outstanding=Decimal("42000.00"),
        days_overdue=20,
        late_payment_count_6mo=3,
        risk_level="High",
        credit_limit=None,
    )
    defaults.update(overrides)
    return OverdueDealer(**defaults)


def _dealer_collection(**overrides) -> DealerCollection:
    defaults = dict(
        dealer_id=uuid.uuid4(),
        dealer_name="ABC Medical",
        amount=Decimal("48000.00"),
        due_date=TODAY + timedelta(days=2),
    )
    defaults.update(overrides)
    return DealerCollection(**defaults)


async def _make_dealer(
    db: AsyncSession, company_id: uuid.UUID, name: str = "Velocity Dealer"
) -> uuid.UUID:
    dealer = Dealer(company_id=company_id, name=name)
    db.add(dealer)
    await db.commit()
    await db.refresh(dealer)
    return dealer.id


async def _make_product(
    db: AsyncSession, company_id: uuid.UUID, name: str, stock_quantity: Decimal
) -> uuid.UUID:
    product = Product(company_id=company_id, name=name, stock_quantity=stock_quantity)
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product.id


async def _make_sale(
    db: AsyncSession,
    company_id: uuid.UUID,
    dealer_id: uuid.UUID,
    product_id: uuid.UUID,
    quantity: Decimal,
    invoice_date,
) -> None:
    """A receivable invoice + line item — the real rows check_stock_out_forecasts'
    underlying build_stock_out_forecasts query reads directly (unlike the other
    rules, it doesn't read off the hand-built Snapshot).
    """
    invoice = Invoice(
        company_id=company_id,
        invoice_number=f"INV-{uuid.uuid4().hex[:10]}",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        invoice_date=invoice_date,
        due_date=invoice_date + timedelta(days=7),
        subtotal=Decimal("100.00"),
        gst_amount=Decimal("0.00"),
        total_amount=Decimal("100.00"),
        status=InvoiceStatus.Paid,
        source=InvoiceSource.csv_import,
    )
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)
    db.add(
        InvoiceItem(
            invoice_id=invoice.id,
            product_id=product_id,
            description="line",
            quantity=quantity,
            unit_price=Decimal("10.00"),
            line_total=Decimal("100.00"),
        )
    )
    await db.commit()


@pytest.fixture
def recorded_sends(monkeypatch):
    sends: list[tuple[str, str]] = []

    async def _fake_send(to: str, body: str) -> WhatsAppSendResult:
        sends.append((to, body))
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.services.notifications.send_text_message", _fake_send)
    return sends


def _set_founder_number(monkeypatch, number: str | None):
    class _Settings:
        founder_whatsapp_number = number
        briefing_hour = 8  # the stale-data digest reads this for its business-hours gate

    monkeypatch.setattr("app.services.notifications.get_settings", lambda: _Settings())


def _pinned_now(hour: int = 10):
    """A business-local time at/after the briefing hour so the digest's
    business-hours gate doesn't skip the company under test."""
    return NOW.replace(hour=hour, minute=0, second=0, microsecond=0)


async def _add_import(db: AsyncSession, company_id: uuid.UUID, *, hours_ago: float) -> None:
    db.add(
        ImportLog(
            company_id=company_id,
            filename="tally.xlsx",
            source_format="excel",
            imported_at=_pinned_now() - timedelta(hours=hours_ago),
            rows_processed=1,
            rows_succeeded=1,
            rows_failed=0,
        )
    )
    await db.commit()


# ── Rule 1: supplier payment reminder ────────────────────────────────────────


@pytest.mark.asyncio
async def test_supplier_reminder_fires_for_due_tomorrow(db: AsyncSession, recorded_sends) -> None:
    company = await _make_company(db)
    snap = _snapshot(
        company.id, expected_payments_7d=[_supplier_payment(due_date=TODAY + timedelta(days=1))]
    )
    sent = await check_supplier_payment_reminders(db, company, snap, NOW)
    await db.commit()

    assert sent == 1
    assert len(recorded_sends) == 1
    assert "Payment Reminder" in recorded_sends[0][1]
    log = await db.scalar(
        select(NotificationLog).where(
            NotificationLog.company_id == company.id,
            NotificationLog.notification_type == "supplier_payment_reminder",
        )
    )
    assert log is not None


@pytest.mark.asyncio
async def test_supplier_reminder_wording_for_an_overdue_bill(
    db: AsyncSession, recorded_sends
) -> None:
    # Regression: expected_payments_7d can now include an already-overdue
    # payable (snapshot.py::_expected_payments_7d dropped its due_date >=
    # today floor) — the reminder's "due {when}" slot only ever handled
    # today/tomorrow, so an overdue bill would have wrongly said "due
    # tomorrow" instead of describing it as overdue.
    company = await _make_company(db)
    snap = _snapshot(
        company.id, expected_payments_7d=[_supplier_payment(due_date=TODAY - timedelta(days=3))]
    )
    sent = await check_supplier_payment_reminders(db, company, snap, NOW)
    await db.commit()

    assert sent == 1
    assert "3 day(s) ago" in recorded_sends[0][1]
    assert "due tomorrow" not in recorded_sends[0][1].lower()


@pytest.mark.asyncio
async def test_supplier_reminder_skips_when_due_beyond_24h(
    db: AsyncSession, recorded_sends
) -> None:
    company = await _make_company(db)
    snap = _snapshot(
        company.id, expected_payments_7d=[_supplier_payment(due_date=TODAY + timedelta(days=3))]
    )
    sent = await check_supplier_payment_reminders(db, company, snap, NOW)
    await db.commit()
    assert sent == 0
    assert recorded_sends == []


@pytest.mark.asyncio
async def test_supplier_reminder_sends_one_message_per_supplier_not_per_bill(
    db: AsyncSession, recorded_sends
) -> None:
    """Regression (found against live prod data): the per-supplier 24h dedup
    was evaluated for every bill *before* any of the tick's reminders were
    sent, so a supplier with N open bills passed the check N times and got N
    separate WhatsApp messages in one burst. The live pilot had 87 open
    payables across 11 suppliers — 47 of them for one supplier — and was
    receiving 88 messages a day, ~32 of which Meta throttled.
    """
    company = await _make_company(db)
    supplier_id = uuid.uuid4()
    bills = [
        _supplier_payment(
            supplier_id=supplier_id,
            supplier_name="Shakti Traders",
            amount=Decimal("1000.00"),
            due_date=TODAY - timedelta(days=days_overdue),
            invoice_number=f"INV-{index}",
        )
        # Ordered most-urgent-first, the way snapshot.py::_expected_payments_7d
        # emits them (ORDER BY due_date).
        for index, days_overdue in enumerate((30, 20, 10))
    ]
    snap = _snapshot(company.id, expected_payments_7d=bills)

    sent = await check_supplier_payment_reminders(db, company, snap, NOW)
    await db.commit()

    assert sent == 1
    assert len(recorded_sends) == 1
    body = recorded_sends[0][1]
    # The lead bill is the most urgent one, and the two it collapsed are
    # still accounted for rather than silently dropped.
    assert "30 day(s) ago" in body
    assert "2 more bill(s)" in body
    assert "2,000" in body


@pytest.mark.asyncio
async def test_supplier_reminder_caps_the_number_of_messages_per_tick(
    db: AsyncSession, recorded_sends
) -> None:
    """Even with every bill belonging to a distinct supplier, one tick must
    not blast an unbounded number of WhatsApp messages — Meta throttles the
    burst, and a throttled reminder deliberately skips its dedup marker, so
    an uncapped burst re-fails identically on every subsequent tick.
    """
    company = await _make_company(db)
    bills = [
        _supplier_payment(supplier_name=f"Supplier {index}", due_date=TODAY)
        for index in range(_MAX_SUPPLIER_REMINDERS_PER_TICK + 5)
    ]
    snap = _snapshot(company.id, expected_payments_7d=bills)

    sent = await check_supplier_payment_reminders(db, company, snap, NOW)
    await db.commit()

    assert sent == _MAX_SUPPLIER_REMINDERS_PER_TICK
    assert len(recorded_sends) == _MAX_SUPPLIER_REMINDERS_PER_TICK


@pytest.mark.asyncio
async def test_supplier_reminder_dedups_within_24h(db: AsyncSession, recorded_sends) -> None:
    company = await _make_company(db)
    payment = _supplier_payment(due_date=TODAY + timedelta(days=1))
    snap = _snapshot(company.id, expected_payments_7d=[payment])

    first = await check_supplier_payment_reminders(db, company, snap, NOW)
    await db.commit()
    second = await check_supplier_payment_reminders(db, company, snap, NOW)
    await db.commit()

    assert first == 1
    assert second == 0  # deduped by the reminder_sent ActivityTimeline entry
    assert len(recorded_sends) == 1


@pytest.mark.asyncio
async def test_supplier_reminder_attaches_wamid_to_active_and_queued_items(
    db: AsyncSession, recorded_sends
) -> None:
    """Both the active reminder and any still-queued ones must carry their
    own real WhatsApp message id in workflow_scratch — this is what lets a
    later native quote-reply be matched back to the specific bill it was
    about (see payment_reminder_confirm.py::promote_queued_reminder), rather
    than only the founder's *first* reminder ever being addressable.
    """
    company = await _make_company(db)
    first_bill = _supplier_payment(
        supplier_name="Royal Meat Suppliers", due_date=TODAY + timedelta(days=1)
    )
    second_bill = _supplier_payment(
        supplier_name="Premium Poultry", due_date=TODAY + timedelta(days=1)
    )
    snap = _snapshot(company.id, expected_payments_7d=[first_bill, second_bill])

    sent = await check_supplier_payment_reminders(db, company, snap, NOW)
    await db.commit()

    assert sent == 2
    assert len(recorded_sends) == 2
    await db.refresh(company)
    scratch = company.workflow_scratch
    assert scratch["supplier_name"] == "Royal Meat Suppliers"
    active_wamid = scratch["whatsapp_message_id"]
    assert active_wamid

    queue = scratch["queue"]
    assert len(queue) == 1
    assert queue[0]["supplier_name"] == "Premium Poultry"
    queued_wamid = queue[0]["whatsapp_message_id"]
    assert queued_wamid
    assert queued_wamid != active_wamid


@pytest.mark.asyncio
async def test_supplier_reminder_retries_after_a_failed_send(
    db: AsyncSession, monkeypatch
) -> None:
    # Regression: a failed send must NOT write the reminder_sent dedup
    # marker — otherwise a bill due today that fails to send at 8am is
    # silently suppressed from retry for the full 24h quiet window, and
    # nothing else ever consumes NotificationLog.delivery_status ==
    # "failed_to_send" to retry sooner.
    company = await _make_company(db)
    payment = _supplier_payment(due_date=TODAY + timedelta(days=1))
    snap = _snapshot(company.id, expected_payments_7d=[payment])

    async def _failing_send(to: str, body: str) -> WhatsAppSendResult:
        raise WhatsAppSendError("Meta down")

    monkeypatch.setattr("app.services.notifications.send_text_message", _failing_send)
    first = await check_supplier_payment_reminders(db, company, snap, NOW)
    await db.commit()
    assert first == 0

    log = await db.scalar(
        select(NotificationLog).where(
            NotificationLog.company_id == company.id,
            NotificationLog.notification_type == "supplier_payment_reminder",
        )
    )
    assert log is not None
    assert log.delivery_status == "failed_to_send"

    async def _working_send(to: str, body: str) -> WhatsAppSendResult:
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.services.notifications.send_text_message", _working_send)
    second = await check_supplier_payment_reminders(db, company, snap, NOW)
    await db.commit()
    assert second == 1  # retried on the next tick, not suppressed


@pytest.mark.asyncio
async def test_supplier_reminder_stays_informational_during_a_live_follow_up(
    db: AsyncSession, recorded_sends
) -> None:
    """A live receivable follow-up must block the interactive payable confirm.

    Regression: can_start_confirm checked active_workflow and
    active_pending_operation_id but not pending_follow_up_invoice_id. A
    follow-up asks "Has INV-100 been paid? 1 = paid in full" about a
    *receivable*; starting this confirm on top makes active_workflow outrank
    it in the webhook, so the founder's unchanged "1" answers a question about
    a *payable* instead — a directional money mix-up.

    The reminder itself still goes out; it just stays one-way this cycle.
    """
    company = await _make_company(db)
    dealer = Dealer(company_id=company.id, name="Follow-up Dealer")
    db.add(dealer)
    await db.flush()
    invoice = Invoice(
        company_id=company.id,
        invoice_number="INV-FU-BUSY",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer.id,
        invoice_date=TODAY,
        due_date=TODAY,
        subtotal=Decimal("1000.00"),
        gst_amount=Decimal("0.00"),
        total_amount=Decimal("1000.00"),
        status=InvoiceStatus.Pending,
        source=InvoiceSource.whatsapp,
    )
    db.add(invoice)
    await db.flush()
    company.pending_follow_up_invoice_id = invoice.id
    await db.commit()

    snap = _snapshot(
        company.id, expected_payments_7d=[_supplier_payment(due_date=TODAY + timedelta(days=1))]
    )
    sent = await check_supplier_payment_reminders(db, company, snap, NOW)
    await db.commit()

    assert sent == 1
    await db.refresh(company)
    assert company.active_workflow is None
    assert company.active_pending_operation_id is None
    assert company.pending_follow_up_invoice_id == invoice.id


@pytest.mark.asyncio
async def test_supplier_reminder_stays_informational_during_incomplete_onboarding(
    db: AsyncSession, recorded_sends
) -> None:
    """A company mid-onboarding must not have this rule start an interactive
    confirm workflow on it.

    Regression: can_start_confirm checked active_workflow/
    active_pending_operation_id/pending_follow_up_invoice_id but not
    onboarding_state. The website import step can seed payable invoices
    before the WhatsApp onboarding chat finishes, and onboarding_state
    outranks active_workflow in the webhook's dispatch chain — so starting
    this confirm mid-onboarding would wedge it until onboarding completes,
    then hijack the founder's first post-onboarding reply.

    The reminder itself still goes out; it just stays one-way this cycle.
    """
    company = await _make_company(db)
    company.onboarding_state = OnboardingState.awaiting_business_type
    await db.commit()

    snap = _snapshot(
        company.id, expected_payments_7d=[_supplier_payment(due_date=TODAY + timedelta(days=1))]
    )
    sent = await check_supplier_payment_reminders(db, company, snap, NOW)
    await db.commit()

    assert sent == 1
    await db.refresh(company)
    assert company.active_workflow is None
    assert company.active_pending_operation_id is None


# ── Rule 2: dealer overdue alert ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dealer_alert_fires_for_high_risk(db: AsyncSession, recorded_sends) -> None:
    company = await _make_company(db)
    snap = _snapshot(company.id, overdue_dealers=[_overdue_dealer(risk_level="High")])
    sent = await check_dealer_overdue_alerts(db, company, snap, NOW)
    await db.commit()

    assert sent == 1
    assert "Collection Alert" in recorded_sends[0][1]
    tl = await db.scalar(
        select(ActivityTimeline).where(
            ActivityTimeline.company_id == company.id,
            ActivityTimeline.event_type == ActivityEventType.overdue_flagged,
        )
    )
    assert tl is not None


@pytest.mark.asyncio
async def test_dealer_alert_skips_medium_and_low_risk(db: AsyncSession, recorded_sends) -> None:
    company = await _make_company(db)
    snap = _snapshot(
        company.id,
        overdue_dealers=[
            _overdue_dealer(risk_level="Medium"),
            _overdue_dealer(risk_level="Low"),
        ],
    )
    sent = await check_dealer_overdue_alerts(db, company, snap, NOW)
    await db.commit()
    assert sent == 0
    assert recorded_sends == []


@pytest.mark.asyncio
async def test_dealer_alert_dedups_when_recent_followup_exists(
    db: AsyncSession, recorded_sends
) -> None:
    company = await _make_company(db)
    dealer = _overdue_dealer(risk_level="High")
    # A Phase 9 follow-up sent yesterday counts as recent contact.
    db.add(
        ActivityTimeline(
            company_id=company.id,
            entity_type=ActivityEntityType.dealer,
            entity_id=dealer.dealer_id,
            event_type=ActivityEventType.follow_up_sent,
            amount=dealer.outstanding,
            notes="prior follow-up",
        )
    )
    await db.commit()

    snap = _snapshot(company.id, overdue_dealers=[dealer])
    sent = await check_dealer_overdue_alerts(db, company, snap, NOW)
    await db.commit()
    assert sent == 0
    assert recorded_sends == []


@pytest.mark.asyncio
async def test_dealer_alert_also_reminds_dealer_directly_when_enabled(
    db: AsyncSession, recorded_sends
) -> None:
    company = await _make_company(db)
    dealer = _overdue_dealer(
        risk_level="High", dealer_phone=_unique_phone(), direct_reminders_enabled=True
    )
    # Inside the dealer's own 24h session window -> free-form send_text_message,
    # same as the founder alert (no template needed).
    db.add(
        BusinessEvent(
            company_id=company.id,
            event_type=BusinessEventType.whatsapp_message_received,
            entity_type="company",
            entity_id=company.id,
            payload={"from": dealer.dealer_phone},
            created_by="test",
        )
    )
    await db.commit()

    snap = _snapshot(company.id, overdue_dealers=[dealer])
    sent = await check_dealer_overdue_alerts(db, company, snap, NOW)
    await db.commit()

    assert sent == 1
    assert len(recorded_sends) == 2  # founder alert + dealer-direct reminder
    dealer_message = next(body for to, body in recorded_sends if to == dealer.dealer_phone)
    assert dealer.dealer_name in dealer_message
    assert company.business_name in dealer_message

    log = await db.scalar(
        select(NotificationLog).where(
            NotificationLog.company_id == company.id,
            NotificationLog.notification_type == "dealer_direct_reminder",
        )
    )
    assert log is not None
    assert log.recipient_whatsapp == dealer.dealer_phone
    assert log.delivery_status == "sent"

    event = await db.scalar(
        select(BusinessEvent).where(
            BusinessEvent.company_id == company.id,
            BusinessEvent.event_type == BusinessEventType.reminder_sent,
            BusinessEvent.entity_type == "dealer",
        )
    )
    assert event.payload["dealer_direct_reminder_sent"] is True


@pytest.mark.asyncio
async def test_dealer_alert_skips_direct_reminder_when_not_enabled(
    db: AsyncSession, recorded_sends
) -> None:
    company = await _make_company(db)
    dealer = _overdue_dealer(risk_level="High", dealer_phone=_unique_phone())  # opted-out default
    snap = _snapshot(company.id, overdue_dealers=[dealer])
    sent = await check_dealer_overdue_alerts(db, company, snap, NOW)
    await db.commit()

    assert sent == 1
    assert len(recorded_sends) == 1  # founder alert only
    assert recorded_sends[0][0] == company.whatsapp_number
    log = await db.scalar(
        select(NotificationLog).where(
            NotificationLog.company_id == company.id,
            NotificationLog.notification_type == "dealer_direct_reminder",
        )
    )
    assert log is None


@pytest.mark.asyncio
async def test_dealer_alert_skips_direct_reminder_without_phone_on_file(
    db: AsyncSession, recorded_sends
) -> None:
    company = await _make_company(db)
    dealer = _overdue_dealer(risk_level="High", dealer_phone=None, direct_reminders_enabled=True)
    snap = _snapshot(company.id, overdue_dealers=[dealer])
    sent = await check_dealer_overdue_alerts(db, company, snap, NOW)
    await db.commit()

    assert sent == 1
    assert len(recorded_sends) == 1  # founder alert only — no phone to reach the dealer on


@pytest.mark.asyncio
async def test_dealer_direct_reminder_uses_template_outside_session_window(
    db: AsyncSession, recorded_sends, monkeypatch
) -> None:
    """No whatsapp_message_received event for this dealer's phone -> outside
    the 24h free-form window, so this must go out as the configured template
    instead of send_text_message (mirrors broadcast's own branch).
    """
    company = await _make_company(db)
    dealer = _overdue_dealer(
        risk_level="High", dealer_phone=_unique_phone(), direct_reminders_enabled=True
    )
    monkeypatch.setattr(get_settings(), "dealer_reminder_template_name", "dealer_reminder_tmpl")
    template_calls: list[tuple[str, str, list]] = []

    async def _fake_send_template(to, template_name, language_code, body_params=None, **kwargs):
        template_calls.append((to, template_name, body_params or []))
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.services.notifications.send_template_message", _fake_send_template)

    snap = _snapshot(company.id, overdue_dealers=[dealer])
    sent = await check_dealer_overdue_alerts(db, company, snap, NOW)
    await db.commit()

    assert sent == 1
    assert len(recorded_sends) == 1  # only the founder's free-form alert
    assert len(template_calls) == 1
    assert template_calls[0][0] == dealer.dealer_phone
    assert template_calls[0][1] == "dealer_reminder_tmpl"
    # dealer_payment_reminder_v2's 4 variables, discrete and in order — not
    # the single pre-composed message string this used to send.
    assert template_calls[0][2] == [
        dealer.dealer_name,
        company.business_name,
        "₹42,000",
        "20",
    ]

    log = await db.scalar(
        select(NotificationLog).where(
            NotificationLog.company_id == company.id,
            NotificationLog.notification_type == "dealer_direct_reminder",
        )
    )
    assert log is not None
    assert log.delivery_status == "sent"


@pytest.mark.asyncio
async def test_dealer_direct_reminder_records_failed_to_send_without_template_configured(
    db: AsyncSession, recorded_sends
) -> None:
    """Outside the session window with no template configured, the direct
    reminder is skipped (recorded failed_to_send) — never blocking the
    existing founder-facing alert.
    """
    company = await _make_company(db)
    dealer = _overdue_dealer(
        risk_level="High", dealer_phone=_unique_phone(), direct_reminders_enabled=True
    )
    snap = _snapshot(company.id, overdue_dealers=[dealer])
    sent = await check_dealer_overdue_alerts(db, company, snap, NOW)
    await db.commit()

    assert sent == 1
    assert len(recorded_sends) == 1  # founder alert only

    log = await db.scalar(
        select(NotificationLog).where(
            NotificationLog.company_id == company.id,
            NotificationLog.notification_type == "dealer_direct_reminder",
        )
    )
    assert log is not None
    assert log.delivery_status == "failed_to_send"


@pytest.mark.asyncio
async def test_dealer_alert_direct_reminder_shares_dedup_with_founder_alert(
    db: AsyncSession, recorded_sends
) -> None:
    """No separate dedup window for the direct-to-dealer send — it rides the
    same "no recent contact" gate as the founder alert, since both fire off
    the exact same fact about this one dealer.
    """
    company = await _make_company(db)
    dealer = _overdue_dealer(
        risk_level="High", dealer_phone=_unique_phone(), direct_reminders_enabled=True
    )
    db.add(
        ActivityTimeline(
            company_id=company.id,
            entity_type=ActivityEntityType.dealer,
            entity_id=dealer.dealer_id,
            event_type=ActivityEventType.follow_up_sent,
            amount=dealer.outstanding,
            notes="prior follow-up",
        )
    )
    await db.commit()

    snap = _snapshot(company.id, overdue_dealers=[dealer])
    sent = await check_dealer_overdue_alerts(db, company, snap, NOW)
    await db.commit()

    assert sent == 0
    assert recorded_sends == []
    log = await db.scalar(
        select(NotificationLog).where(
            NotificationLog.company_id == company.id,
            NotificationLog.notification_type == "dealer_direct_reminder",
        )
    )
    assert log is None


# ── Rule 5: cash-shortage forecast ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_cash_shortage_forecast_fires_with_trigger_payment(
    db: AsyncSession, recorded_sends
) -> None:
    company = await _make_company(db)
    trigger = _supplier_payment(
        supplier_name="Big Supplier",
        amount=Decimal("90000.00"),
        due_date=TODAY + timedelta(days=2),
    )
    snap = _snapshot(
        company.id,
        cash_deficit_forecast=CashDeficitForecast(days_until=2, trigger_payment=trigger),
    )
    sent = await check_cash_shortage_forecast(db, company, snap, NOW)
    await db.commit()

    assert sent == 1
    assert "Cash Shortage Forecast" in recorded_sends[0][1]
    assert "Big Supplier" in recorded_sends[0][1]
    event = await db.scalar(
        select(BusinessEvent).where(
            BusinessEvent.company_id == company.id,
            BusinessEvent.event_type == BusinessEventType.cash_shortage_forecast_sent,
        )
    )
    assert event is not None


@pytest.mark.asyncio
async def test_cash_shortage_forecast_skips_when_no_forecast(
    db: AsyncSession, recorded_sends
) -> None:
    company = await _make_company(db)
    snap = _snapshot(company.id, cash_deficit_forecast=None)
    sent = await check_cash_shortage_forecast(db, company, snap, NOW)
    await db.commit()
    assert sent == 0
    assert recorded_sends == []


@pytest.mark.asyncio
async def test_cash_shortage_forecast_dedups_within_quiet_window(
    db: AsyncSession, recorded_sends
) -> None:
    company = await _make_company(db)
    trigger = _supplier_payment(due_date=TODAY + timedelta(days=2))
    snap = _snapshot(
        company.id,
        cash_deficit_forecast=CashDeficitForecast(days_until=2, trigger_payment=trigger),
    )
    first = await check_cash_shortage_forecast(db, company, snap, NOW)
    await db.commit()
    second = await check_cash_shortage_forecast(db, company, snap, NOW)
    await db.commit()

    assert first == 1
    assert second == 0
    assert len(recorded_sends) == 1


@pytest.mark.asyncio
async def test_cash_shortage_forecast_retries_after_a_failed_send(
    db: AsyncSession, monkeypatch
) -> None:
    company = await _make_company(db)
    trigger = _supplier_payment(due_date=TODAY + timedelta(days=2))
    snap = _snapshot(
        company.id,
        cash_deficit_forecast=CashDeficitForecast(days_until=2, trigger_payment=trigger),
    )

    async def _failing_send(to: str, body: str) -> WhatsAppSendResult:
        raise WhatsAppSendError("Meta down")

    monkeypatch.setattr("app.services.notifications.send_text_message", _failing_send)
    first = await check_cash_shortage_forecast(db, company, snap, NOW)
    await db.commit()
    assert first == 0
    event = await db.scalar(
        select(BusinessEvent).where(
            BusinessEvent.company_id == company.id,
            BusinessEvent.event_type == BusinessEventType.cash_shortage_forecast_sent,
        )
    )
    assert event is None  # not deduped — a failed send must not suppress retry

    async def _working_send(to: str, body: str) -> WhatsAppSendResult:
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.services.notifications.send_text_message", _working_send)
    second = await check_cash_shortage_forecast(db, company, snap, NOW)
    await db.commit()
    assert second == 1


# ── Rule 6: stock-out forecast ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stock_out_forecast_fires_below_threshold(db: AsyncSession, recorded_sends) -> None:
    company = await _make_company(db)
    dealer_id = await _make_dealer(db, company.id)
    product_id = await _make_product(db, company.id, "Paracetamol", Decimal("20"))
    # 4 sales x 30 units = 120 units over 30 days -> 4 units/day; 20 in stock
    # -> 5 days of cover, within the 7-day threshold.
    for i in range(4):
        await _make_sale(
            db, company.id, dealer_id, product_id, Decimal("30"), TODAY - timedelta(days=i)
        )

    snap = _snapshot(company.id)
    sent = await check_stock_out_forecasts(db, company, snap, NOW)
    await db.commit()

    assert sent == 1
    assert "Paracetamol" in recorded_sends[0][1]


@pytest.mark.asyncio
async def test_stock_out_forecast_suppressed_by_min_sample_guard(
    db: AsyncSession, recorded_sends
) -> None:
    company = await _make_company(db)
    dealer_id = await _make_dealer(db, company.id)
    product_id = await _make_product(db, company.id, "Rare Item", Decimal("5"))
    # Well above the units floor but only 1 sale-day — below the 3-sale-day guard.
    await _make_sale(db, company.id, dealer_id, product_id, Decimal("50"), TODAY)

    snap = _snapshot(company.id)
    sent = await check_stock_out_forecasts(db, company, snap, NOW)
    await db.commit()
    assert sent == 0
    assert recorded_sends == []


@pytest.mark.asyncio
async def test_stock_out_forecast_skips_when_cover_above_threshold(
    db: AsyncSession, recorded_sends
) -> None:
    company = await _make_company(db)
    dealer_id = await _make_dealer(db, company.id)
    product_id = await _make_product(db, company.id, "Overstocked", Decimal("1000"))
    for i in range(4):
        await _make_sale(
            db, company.id, dealer_id, product_id, Decimal("30"), TODAY - timedelta(days=i)
        )
    # velocity 4/day, 1000 in stock -> 250 days of cover, well above threshold.

    snap = _snapshot(company.id)
    sent = await check_stock_out_forecasts(db, company, snap, NOW)
    await db.commit()
    assert sent == 0


@pytest.mark.asyncio
async def test_stock_out_forecast_dedups_per_product(db: AsyncSession, recorded_sends) -> None:
    company = await _make_company(db)
    dealer_id = await _make_dealer(db, company.id)
    product_id = await _make_product(db, company.id, "Widget", Decimal("20"))
    for i in range(4):
        await _make_sale(
            db, company.id, dealer_id, product_id, Decimal("30"), TODAY - timedelta(days=i)
        )

    snap = _snapshot(company.id)
    first = await check_stock_out_forecasts(db, company, snap, NOW)
    await db.commit()
    second = await check_stock_out_forecasts(db, company, snap, NOW)
    await db.commit()

    assert first == 1
    assert second == 0
    assert len(recorded_sends) == 1


# ── Rule 7: pre-due invoice nudge ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_predue_nudge_fires_for_due_in_two_days(db: AsyncSession, recorded_sends) -> None:
    company = await _make_company(db)
    snap = _snapshot(
        company.id, expected_collections_7d=[_dealer_collection(due_date=TODAY + timedelta(days=2))]
    )
    sent = await check_predue_invoice_nudges(db, company, snap, NOW)
    await db.commit()

    assert sent == 1
    assert "Due Soon" in recorded_sends[0][1]


@pytest.mark.asyncio
async def test_predue_nudge_excludes_due_today(db: AsyncSession, recorded_sends) -> None:
    # Due today/overdue stays followup.py's (and rule 2's) job, not this rule's.
    company = await _make_company(db)
    snap = _snapshot(company.id, expected_collections_7d=[_dealer_collection(due_date=TODAY)])
    sent = await check_predue_invoice_nudges(db, company, snap, NOW)
    await db.commit()
    assert sent == 0
    assert recorded_sends == []


@pytest.mark.asyncio
async def test_predue_nudge_excludes_beyond_window(db: AsyncSession, recorded_sends) -> None:
    company = await _make_company(db)
    snap = _snapshot(
        company.id, expected_collections_7d=[_dealer_collection(due_date=TODAY + timedelta(days=5))]
    )
    sent = await check_predue_invoice_nudges(db, company, snap, NOW)
    await db.commit()
    assert sent == 0
    assert recorded_sends == []


@pytest.mark.asyncio
async def test_predue_nudge_dedups_per_dealer(db: AsyncSession, recorded_sends) -> None:
    company = await _make_company(db)
    collection = _dealer_collection(due_date=TODAY + timedelta(days=1))
    snap = _snapshot(company.id, expected_collections_7d=[collection])
    first = await check_predue_invoice_nudges(db, company, snap, NOW)
    await db.commit()
    second = await check_predue_invoice_nudges(db, company, snap, NOW)
    await db.commit()

    assert first == 1
    assert second == 0
    assert len(recorded_sends) == 1


# ── Rule 3: stale-data founder alert ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_stale_digest_fires_to_founder(db: AsyncSession, recorded_sends, monkeypatch):
    founder = _unique_phone()
    _set_founder_number(monkeypatch, founder)
    company = await _make_company(db)  # never imported → stale

    result = await send_stale_data_digest(db, now=_pinned_now())
    await db.commit()

    assert result.companies_flagged == 1
    assert result.sent is True
    assert len(recorded_sends) == 1
    to, body = recorded_sends[0]
    assert to == founder
    assert company.business_name in body
    event = await db.scalar(
        select(BusinessEvent).where(
            BusinessEvent.company_id == company.id,
            BusinessEvent.event_type == BusinessEventType.founder_alert_sent,
        )
    )
    assert event is not None
    assert event.payload["reason"] == "stale_data"


@pytest.mark.asyncio
async def test_stale_digest_not_fired_when_fresh(db: AsyncSession, recorded_sends, monkeypatch):
    _set_founder_number(monkeypatch, _unique_phone())
    company = await _make_company(db)
    await _add_import(db, company.id, hours_ago=2)  # fresh

    result = await send_stale_data_digest(db, now=_pinned_now())
    await db.commit()

    assert result.companies_flagged == 0
    assert recorded_sends == []


@pytest.mark.asyncio
async def test_stale_digest_dedups_same_day(db: AsyncSession, recorded_sends, monkeypatch):
    _set_founder_number(monkeypatch, _unique_phone())
    await _make_company(db)  # never imported → stale

    first = await send_stale_data_digest(db, now=_pinned_now())
    await db.commit()
    second = await send_stale_data_digest(db, now=_pinned_now())
    await db.commit()

    assert first.companies_flagged == 1
    assert first.sent is True
    assert second.companies_flagged == 0
    assert len(recorded_sends) == 1


@pytest.mark.asyncio
async def test_stale_digest_aggregates_many_into_one_message(
    db: AsyncSession, recorded_sends, monkeypatch
):
    """The core fix: N stale companies → ONE founder message, but a per-company
    dedup marker for each so none re-fires the same day."""
    founder = _unique_phone()
    _set_founder_number(monkeypatch, founder)
    companies = [await _make_company(db, name=f"Stale Co {i}") for i in range(3)]

    result = await send_stale_data_digest(db, now=_pinned_now())
    await db.commit()

    assert result.companies_flagged == 3
    assert len(recorded_sends) == 1  # one physical WhatsApp send for all three
    to, body = recorded_sends[0]
    assert to == founder
    for company in companies:
        assert company.business_name in body
    markers = (
        await db.scalars(
            select(BusinessEvent).where(
                BusinessEvent.event_type == BusinessEventType.founder_alert_sent
            )
        )
    ).all()
    assert len(markers) == 3


@pytest.mark.asyncio
async def test_stale_digest_skipped_before_briefing_hour(
    db: AsyncSession, recorded_sends, monkeypatch
):
    _set_founder_number(monkeypatch, _unique_phone())
    await _make_company(db)  # stale, but the tick is pre-dawn (hour 3 < 8)

    result = await send_stale_data_digest(db, now=_pinned_now(hour=3))
    await db.commit()

    assert result.companies_flagged == 0
    assert recorded_sends == []


@pytest.mark.asyncio
async def test_stale_digest_global_ceiling_blocks_fresh_batch(
    db: AsyncSession, recorded_sends, monkeypatch
):
    """The anti-flood ceiling: a brand-new batch of stale companies appearing
    right after a digest must NOT trigger a second founder message within the
    min-interval. This is the exact failure that let 1,000+ leaked fixture
    companies stream digest after digest to the founder's real WhatsApp — the
    per-company dedup can't stop it because each new company is unseen, so only
    the global ceiling can.
    """
    _set_founder_number(monkeypatch, _unique_phone())
    await _make_company(db, name="Batch A Co")  # never imported → stale

    first = await send_stale_data_digest(db, now=_pinned_now())
    await db.commit()

    # A different company becomes stale seconds later — per-company dedup would
    # NOT suppress it (it has no marker yet); only the global interval ceiling can.
    await _make_company(db, name="Batch B Co")
    second = await send_stale_data_digest(db, now=_pinned_now())
    await db.commit()

    assert first.sent is True
    assert second.sent is False
    assert second.companies_flagged == 1  # Batch B was flagged but not sent
    assert len(recorded_sends) == 1  # exactly ONE founder message, not two


@pytest.mark.asyncio
async def test_founder_alert_skipped_when_number_unset(
    db: AsyncSession, recorded_sends, monkeypatch
):
    _set_founder_number(monkeypatch, None)
    company = await _make_company(db)
    fired = await send_founder_alert(db, company=company, reason="stale_data", message="hi")
    await db.commit()
    assert fired is False
    assert recorded_sends == []


# ── Rule 4: briefing-failure founder alert ───────────────────────────────────


@pytest.mark.asyncio
async def test_notify_briefing_failed_alerts_founder(db: AsyncSession, recorded_sends, monkeypatch):
    founder = _unique_phone()
    _set_founder_number(monkeypatch, founder)
    company = await _make_company(db)

    fired = await notify_briefing_failed(db, company)
    await db.commit()

    assert fired is True
    assert recorded_sends[0][0] == founder
    assert "Briefing Delivery Failed" in recorded_sends[0][1]
    event = await db.scalar(
        select(BusinessEvent).where(
            BusinessEvent.company_id == company.id,
            BusinessEvent.event_type == BusinessEventType.founder_alert_sent,
        )
    )
    assert event is not None
    assert event.payload["reason"] == "briefing_failed"


@pytest.mark.asyncio
async def test_notify_briefing_failed_dedups_same_day(
    db: AsyncSession, recorded_sends, monkeypatch
):
    # The retry hour is polled several times; a briefing that keeps failing to
    # send must alert the founder at most once per business day, not on every
    # tick — same guard as generation-failed / stale-data.
    _set_founder_number(monkeypatch, _unique_phone())
    company = await _make_company(db)

    first = await notify_briefing_failed(db, company)
    await db.commit()
    second = await notify_briefing_failed(db, company)
    await db.commit()

    assert first is True
    assert second is False
    assert len(recorded_sends) == 1


@pytest.mark.asyncio
async def test_notify_briefing_generation_failed_alerts_founder(
    db: AsyncSession, recorded_sends, monkeypatch
):
    founder = _unique_phone()
    _set_founder_number(monkeypatch, founder)
    company = await _make_company(db)

    fired = await notify_briefing_generation_failed(db, company, NOW)
    await db.commit()

    assert fired is True
    assert recorded_sends[0][0] == founder
    assert "Briefing Generation Failed" in recorded_sends[0][1]
    event = await db.scalar(
        select(BusinessEvent).where(
            BusinessEvent.company_id == company.id,
            BusinessEvent.event_type == BusinessEventType.founder_alert_sent,
        )
    )
    assert event is not None
    assert event.payload["reason"] == "briefing_failed"


@pytest.mark.asyncio
async def test_notify_briefing_generation_failed_dedups_same_day(
    db: AsyncSession, recorded_sends, monkeypatch
):
    _set_founder_number(monkeypatch, _unique_phone())
    company = await _make_company(db)

    first = await notify_briefing_generation_failed(db, company, NOW)
    await db.commit()
    second = await notify_briefing_generation_failed(db, company, NOW)
    await db.commit()

    assert first is True
    assert second is False
    assert len(recorded_sends) == 1


# ── Orchestrator durability ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_later_rule_failing_cannot_undo_an_earlier_rule_send(
    db: AsyncSession, recorded_sends, monkeypatch
) -> None:
    """Rule 1's dedup marker must survive rule 3 raising.

    Regression: run_notification_checks batched all five rules into one commit
    by the caller. Every rule sends real WhatsApp messages *before* writing its
    dedup marker, so a raise partway through rolled back the markers for
    messages that had already gone out — and the external cron re-ticks every
    ~10 minutes, sees no marker, and re-sends them. Indefinitely.
    """
    company = await _make_company(db)
    snap_payments = [_supplier_payment(due_date=TODAY + timedelta(days=1))]

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("simulated Neon drop mid-tick")

    monkeypatch.setattr(
        "app.services.notifications.check_cash_shortage_forecast", _boom
    )
    monkeypatch.setattr(
        "app.services.notifications.build_snapshot",
        lambda _db, _cid: _async_snapshot(company.id, expected_payments_7d=snap_payments),
    )

    with pytest.raises(RuntimeError):
        await run_notification_checks(db, company.id, now=NOW)

    # The reminder physically went out.
    assert len(recorded_sends) == 1

    # Its dedup marker must be durable despite the later failure. Asked from a
    # *separate* session on purpose: the failed session's own uncommitted (or
    # rolled-back) state can't answer "did this reach the database?", which is
    # exactly what the next scheduler tick will see.
    async with async_session_factory() as verifier:
        marker = await verifier.scalar(
            select(ActivityTimeline).where(
                ActivityTimeline.company_id == company.id,
                ActivityTimeline.event_type == ActivityEventType.reminder_sent,
            )
        )
    assert marker is not None, (
        "the supplier reminder was sent but its dedup marker was rolled back — "
        "the next tick (~10 min later) would send it again"
    )


async def _async_snapshot(company_id: uuid.UUID, **overrides):
    return _snapshot(company_id, **overrides)
