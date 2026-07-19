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
from app.models.activity_timeline import ActivityEntityType, ActivityEventType, ActivityTimeline
from app.models.business_event import BusinessEvent, BusinessEventType
from app.models.company import Company
from app.models.import_log import ImportLog
from app.models.notification_log import NotificationLog
from app.services.notifications import (
    check_dealer_overdue_alerts,
    check_supplier_payment_reminders,
    notify_briefing_failed,
    notify_briefing_generation_failed,
    send_founder_alert,
    send_stale_data_digest,
)
from app.services.snapshot import (
    DEFAULT_BUSINESS_TIMEZONE,
    OverdueDealer,
    Snapshot,
    SupplierPayment,
    business_now,
)
from app.services.whatsapp_client import WhatsAppSendResult
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
