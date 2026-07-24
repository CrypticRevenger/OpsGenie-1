"""_deliver_briefing atomic delivery-claim concurrency test.

Same real bug class as the generation-side test in
tests/test_briefing_concurrency.py — see app/core/scheduler.py::
_deliver_briefing's docstring. Closes the narrower "two overlapping
scheduler ticks" send-side race: even with generation claimed atomically,
two dispatch attempts that both retrieve the same already-generated
MorningBriefing row must not both physically send it (the same real-world
shape as the evening brief's proven 3x-send production bug — see
tests/test_evening_brief.py::
test_concurrent_calls_from_separate_sessions_send_only_once).
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from app.core.scheduler import _deliver_briefing
from app.db.session import async_session_factory
from app.models.company import Company
from app.models.morning_briefing import MorningBriefing
from app.services.whatsapp_client import WhatsAppSendResult
from sqlalchemy.ext.asyncio import AsyncSession


def _unique_phone() -> str:
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


async def _make_company_with_briefing(db: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    company = Company(
        business_name="Delivery Race Co",
        owner_name="Owner",
        whatsapp_number=_unique_phone(),
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)

    briefing = MorningBriefing(
        company_id=company.id,
        generated_text="Cash is fine today.",
        snapshot_json={},
    )
    db.add(briefing)
    await db.commit()
    await db.refresh(briefing)
    return company.id, briefing.id


@pytest.mark.asyncio
async def test_concurrent_deliver_briefing_sends_only_once(db: AsyncSession, monkeypatch) -> None:
    company_id, briefing_id = await _make_company_with_briefing(db)

    sent: list[str] = []
    started = asyncio.Event()
    release = asyncio.Event()

    async def _slow_send(to: str, body: str) -> WhatsAppSendResult:
        # Widen the race window deterministically, same technique
        # test_evening_brief.py's _slow_send uses.
        started.set()
        await release.wait()
        sent.append(body)
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    import app.core.scheduler as scheduler_module

    monkeypatch.setattr(scheduler_module, "send_text_message", _slow_send)

    async def _attempt() -> bool:
        async with async_session_factory() as session:
            company = await session.get(Company, company_id)
            briefing = await session.get(MorningBriefing, briefing_id)
            result = await _deliver_briefing(session, company, briefing)
            await session.commit()
            return result

    async def _watcher() -> None:
        # Whichever attempt wins the claim reaches _slow_send and blocks
        # there (holding the claim, uncommitted). The other is blocked at
        # the DB level on the same row's conditional UPDATE — it can never
        # reach _slow_send at all.
        await started.wait()
        await asyncio.sleep(0.2)
        release.set()

    results = await asyncio.gather(_attempt(), _attempt(), _watcher())
    attempt_results = results[:2]

    # Both attempts correctly report "delivered" — the loser blocks on the
    # claim until the winner resolves, then sees the row really is "sent"
    # and truthfully reports that (rather than falsely claiming failure).
    # The real invariant is the physical send count below: exactly one.
    assert attempt_results == [True, True]
    assert len(sent) == 1

    async with async_session_factory() as verify_db:
        refreshed = await verify_db.get(MorningBriefing, briefing_id)
        assert refreshed.delivery_status == "sent"
        assert refreshed.delivery_claimed_at is not None
