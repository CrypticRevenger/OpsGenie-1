"""Scheduler dispatch tests — Phase 11.

The dispatch decisions (which action fires at which business-local hour, and
that each fires at most once/day) are the new logic here — generate_briefing,
send_text_message, send_due_today_follow_up, and run_notification_checks are
all already covered by their own suites, so they're monkeypatched to recording
stubs. Business time is pinned via the `now` override so tests don't depend on
the wall clock.

    uv run alembic upgrade head
    uv run pytest tests/test_scheduler.py -v
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from app.core import scheduler
from app.core.scheduler import _dispatch_for_company, run_scheduled_tick
from app.models.company import Company
from app.models.morning_briefing import MorningBriefing
from app.services.followup import FollowUpSendResult
from sqlalchemy.ext.asyncio import AsyncSession

IST = ZoneInfo("Asia/Kolkata")


def _unique_phone() -> str:
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


async def _make_company(db: AsyncSession, *, active: bool = True) -> Company:
    company = Company(
        business_name="Scheduler Test Co",
        owner_name="Owner",
        whatsapp_number=_unique_phone(),
        subscription_active=active,
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company


@pytest.fixture
def spies(monkeypatch):
    """Record calls to every side-effecting service the scheduler drives, so
    tests assert on *what fired* without doing real work or real sends.
    """
    calls = {"generate": [], "send": [], "followup": [], "notify": [], "briefing_failed": []}

    async def _gen(db, company_id):
        calls["generate"].append(company_id)
        briefing = MorningBriefing(
            company_id=company_id,
            generated_text="briefing body",
            snapshot_json={"cash_position": {}},
            confidence_score=Decimal("90.00"),
            data_freshness_hours=1,
        )
        db.add(briefing)
        await db.flush()
        return briefing

    async def _send(to, body):
        calls["send"].append((to, body))
        from app.services.whatsapp_client import WhatsAppSendResult

        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    async def _followup(db, company_id):
        calls["followup"].append(company_id)
        return FollowUpSendResult(status="none_due")

    async def _notify(db, company_id, now=None):
        calls["notify"].append(company_id)
        from app.services.notifications import NotificationRunResult

        return NotificationRunResult(supplier_reminders=0, dealer_alerts=0, stale_data_alert=False)

    async def _briefing_failed(db, company):
        calls["briefing_failed"].append(company.id)
        return True

    monkeypatch.setattr(scheduler, "generate_briefing", _gen)
    monkeypatch.setattr(scheduler, "send_text_message", _send)
    monkeypatch.setattr(scheduler, "send_due_today_follow_up", _followup)
    monkeypatch.setattr(scheduler, "run_notification_checks", _notify)
    monkeypatch.setattr(scheduler, "notify_briefing_failed", _briefing_failed)
    return calls


def _at(hour: int) -> datetime:
    # Anchor to *today's* IST date (not a hardcoded one) so the once-per-day
    # dedup check — which compares a briefing's real created_at against this
    # date — stays valid whatever day the suite runs on. Only .hour/.date()
    # are read by the scheduler.
    today = datetime.now(IST).date()
    return datetime(today.year, today.month, today.day, hour, 0, tzinfo=IST)


# ── Briefing dispatch ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_briefing_generates_and_sends_at_briefing_hour(db: AsyncSession, spies) -> None:
    company = await _make_company(db)
    await _dispatch_for_company(company.id, _at(8))

    assert spies["generate"] == [company.id]
    assert len(spies["send"]) == 1
    # Notification checks always run.
    assert spies["notify"] == [company.id]


@pytest.mark.asyncio
async def test_no_briefing_outside_briefing_hour(db: AsyncSession, spies) -> None:
    company = await _make_company(db)
    await _dispatch_for_company(company.id, _at(14))
    assert spies["generate"] == []
    assert spies["send"] == []
    assert spies["notify"] == [company.id]  # notifications still run


@pytest.mark.asyncio
async def test_notifications_gated_out_before_business_hours(db: AsyncSession, spies) -> None:
    # Pre-dawn tick (hour 3, before BRIEFING_HOUR=8) must not fire real
    # supplier/dealer WhatsApp alerts at odd hours.
    company = await _make_company(db)
    await _dispatch_for_company(company.id, _at(3))
    assert spies["notify"] == []


@pytest.mark.asyncio
async def test_briefing_not_regenerated_if_already_sent_today(db: AsyncSession, spies) -> None:
    company = await _make_company(db)
    await _dispatch_for_company(company.id, _at(8))  # first: generates
    await _dispatch_for_company(company.id, _at(8))  # second: must skip
    assert spies["generate"] == [company.id]  # only once


# ── Retry + founder alert ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retry_hour_resends_failed_briefing(db: AsyncSession, spies) -> None:
    company = await _make_company(db)
    # A briefing generated today whose send failed.
    briefing = MorningBriefing(
        company_id=company.id,
        generated_text="body",
        snapshot_json={"cash_position": {}},
        confidence_score=Decimal("90.00"),
        data_freshness_hours=1,
        delivery_status="failed_to_send",
    )
    db.add(briefing)
    await db.commit()

    await _dispatch_for_company(company.id, _at(9))
    # Retry attempted a send; generate was NOT called again.
    assert spies["generate"] == []
    assert len(spies["send"]) == 1
    assert spies["briefing_failed"] == []  # send succeeded on retry


@pytest.mark.asyncio
async def test_retry_hour_alerts_founder_when_retry_also_fails(
    db: AsyncSession, spies, monkeypatch
) -> None:
    company = await _make_company(db)
    briefing = MorningBriefing(
        company_id=company.id,
        generated_text="body",
        snapshot_json={"cash_position": {}},
        confidence_score=Decimal("90.00"),
        data_freshness_hours=1,
        delivery_status="failed_to_send",
    )
    db.add(briefing)
    await db.commit()

    from app.services.whatsapp_client import WhatsAppSendError

    async def _failing_send(to, body):
        raise WhatsAppSendError("still failing")

    monkeypatch.setattr(scheduler, "send_text_message", _failing_send)

    await _dispatch_for_company(company.id, _at(9))
    assert spies["briefing_failed"] == [company.id]


# ── Follow-up dispatch ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_followup_fires_at_followup_hour(db: AsyncSession, spies) -> None:
    company = await _make_company(db)
    await _dispatch_for_company(company.id, _at(10))
    assert spies["followup"] == [company.id]


@pytest.mark.asyncio
async def test_followup_not_fired_at_other_hours(db: AsyncSession, spies) -> None:
    company = await _make_company(db)
    await _dispatch_for_company(company.id, _at(8))
    assert spies["followup"] == []


# ── Company selection + isolation ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_inactive_company_skipped(db: AsyncSession, spies) -> None:
    company = await _make_company(db, active=False)
    await _dispatch_for_company(company.id, _at(8))
    assert spies["generate"] == []
    assert spies["notify"] == []


@pytest.mark.asyncio
async def test_run_tick_isolates_per_company_failure(db: AsyncSession, monkeypatch) -> None:
    """One company's dispatch raising must not stop the others in the pass."""
    good = await _make_company(db)
    dispatched: list = []

    async def _fake_dispatch(company_id, now):
        dispatched.append(company_id)
        if company_id == good.id:
            raise RuntimeError("boom")

    monkeypatch.setattr(scheduler, "_dispatch_for_company", _fake_dispatch)

    # Should not raise despite the injected failure.
    await run_scheduled_tick(now=_at(14))
    # The good company was attempted (and its failure swallowed); the pass
    # covered every active company, so at least this one is present.
    assert good.id in dispatched
