"""generate_briefing atomic-claim concurrency test.

Same real bug class as tests/test_evening_brief.py::
test_concurrent_calls_from_separate_sessions_send_only_once, applied to the
morning briefing — see app/services/briefing.py::generate_briefing's
docstring. generate_briefing used to be a plain "read latest_briefing_today,
then decide, then INSERT" with no unique constraint behind it, reachable
from three largely-unlocked callers (the scheduler tick, the admin
POST /briefing endpoint, and the webhook's on-demand "give me my briefing"
reply). This drives two genuinely separate DB sessions through
generate_briefing concurrently (synchronized with asyncio.Event to force
real overlap, not timing luck) and proves the atomic claim
(MorningBriefing's unique (company_id, business_date) constraint) lets only
one attempt actually pay for a real LLM call and persist a row.
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

import pytest
from app.db.session import async_session_factory
from app.models.company import Company
from app.models.morning_briefing import MorningBriefing
from app.services.briefing import generate_briefing
from app.services.llm.base import ProviderResult
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _unique_phone() -> str:
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


async def _make_company(db: AsyncSession) -> uuid.UUID:
    company = Company(
        business_name="Briefing Race Co",
        owner_name="Owner",
        whatsapp_number=_unique_phone(),
        opening_balance=Decimal("10000.00"),
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company.id


@pytest.mark.asyncio
async def test_concurrent_generate_briefing_calls_claim_only_once(
    db: AsyncSession, monkeypatch
) -> None:
    company_id = await _make_company(db)

    call_count = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def _slow_generate(*, system_prompt: str, user_content: str) -> ProviderResult:
        # Widen the race window deterministically, same technique
        # test_evening_brief.py's _slow_send uses — only the claim-winner can
        # ever reach this call at all (the loser blocks earlier, inside its
        # own INSERT, on Postgres's unique-index row lock), so seeing this
        # called more than once would mean the claim failed to serialize.
        nonlocal call_count
        call_count += 1
        started.set()
        await release.wait()
        return ProviderResult(
            provider="fake", model="fake-model", text="Cash position is healthy today.",
            latency_seconds=0.01,
        )

    import app.services.briefing as briefing_module

    monkeypatch.setattr(briefing_module, "generate_with_fallback", _slow_generate)

    async def _attempt() -> MorningBriefing:
        async with async_session_factory() as session:
            briefing = await generate_briefing(session, company_id)
            return briefing

    async def _watcher() -> None:
        # Whichever attempt wins the claim reaches _slow_generate and blocks
        # there. The other is meanwhile blocked at the DB level on the same
        # unique (company_id, business_date) row's INSERT — it can never
        # reach _slow_generate at all. Release only after both are
        # demonstrably in-flight.
        await started.wait()
        await asyncio.sleep(0.2)
        release.set()

    results = await asyncio.gather(_attempt(), _attempt(), _watcher())
    briefings = results[:2]

    assert call_count == 1  # only the winner ever paid for a real LLM call
    assert briefings[0].id == briefings[1].id  # both callers got back the same row
    assert briefings[0].generated_text == briefings[1].generated_text

    async with async_session_factory() as verify_db:
        rows = (
            await verify_db.scalars(
                select(MorningBriefing).where(MorningBriefing.company_id == company_id)
            )
        ).all()
        assert len(rows) == 1  # no duplicate row persisted
        assert rows[0].generated_text != ""  # not left as the empty placeholder
