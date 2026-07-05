"""Assistant tests — agent wiring, multi-turn memory, and the money-safety gate.

`run_agent` is stubbed (no network). The gate and memory persistence are the
important behaviours here.

    uv run alembic upgrade head
    uv run pytest tests/test_assistant.py -v
"""

from __future__ import annotations

import uuid

import pytest
from app.models.company import Company, OnboardingState
from app.models.conversation_turn import ConversationTurn
from app.services import assistant as assistant_mod
from app.services.agent.runner import AgentResult
from app.services.assistant import _SAFE_FALLBACK, answer_question
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _unique_number() -> str:
    return f"+919{uuid.uuid4().int % 1_000_000_000:09d}"


async def _company(db: AsyncSession) -> Company:
    company = Company(
        business_name="Assist Co",
        owner_name="Owner",
        whatsapp_number=_unique_number(),
        subscription_active=True,
        onboarding_state=OnboardingState.completed,
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company


def _stub_agent(monkeypatch, *, text: str, tool_outputs: list[dict]):
    captured = {}

    async def _fake_run_agent(*, system_prompt, messages, ctx, settings=None):
        captured["messages"] = messages
        captured["system_prompt"] = system_prompt
        return AgentResult(text=text, tool_outputs=tool_outputs, provider="fake", model="m")

    monkeypatch.setattr(assistant_mod, "run_agent", _fake_run_agent)
    return captured


@pytest.mark.asyncio
async def test_grounded_answer_passes_and_persists_turns(db: AsyncSession, monkeypatch) -> None:
    company = await _company(db)
    _stub_agent(
        monkeypatch,
        text="Ram Traders owes you ₹42,000.",
        tool_outputs=[{"outstanding": "42000.00"}],
    )
    reply = await answer_question(db, company, "how much does ram owe")
    assert reply == "Ram Traders owes you ₹42,000."
    await db.commit()

    turns = (
        await db.scalars(
            select(ConversationTurn)
            .where(ConversationTurn.company_id == company.id)
            .order_by(ConversationTurn.created_at)
        )
    ).all()
    assert [t.role for t in turns] == ["user", "assistant"]
    assert turns[0].content == "how much does ram owe"
    assert turns[1].content == reply


@pytest.mark.asyncio
async def test_multi_turn_history_is_passed(db: AsyncSession, monkeypatch) -> None:
    company = await _company(db)
    # Seed a prior exchange.
    _stub_agent(monkeypatch, text="Ram owes ₹42,000.", tool_outputs=[{"o": "42000.00"}])
    await answer_question(db, company, "how much does ram owe")
    await db.commit()

    captured = _stub_agent(
        monkeypatch, text="Shyam owes ₹10,000.", tool_outputs=[{"o": "10000.00"}]
    )
    await answer_question(db, company, "and shyam?")
    # The follow-up call sees the prior user+assistant turns before the new message.
    roles = [m["role"] for m in captured["messages"]]
    assert roles == ["user", "assistant", "user"]
    assert captured["messages"][-1]["content"] == "and shyam?"


@pytest.mark.asyncio
async def test_hallucinated_amount_gated_to_fallback(db: AsyncSession, monkeypatch) -> None:
    company = await _company(db)
    # Tool returned 42000 but the model states 99,999 → must be discarded.
    _stub_agent(
        monkeypatch,
        text="Ram owes you ₹99,999.",
        tool_outputs=[{"outstanding": "42000.00"}],
    )
    reply = await answer_question(db, company, "how much does ram owe")
    assert reply == _SAFE_FALLBACK


@pytest.mark.asyncio
async def test_non_rupee_hallucination_gated(db: AsyncSession, monkeypatch) -> None:
    company = await _company(db)
    _stub_agent(
        monkeypatch, text="Ram owes Rs 5,00,000.", tool_outputs=[{"outstanding": "42000.00"}]
    )
    reply = await answer_question(db, company, "how much does ram owe")
    assert reply == _SAFE_FALLBACK


@pytest.mark.asyncio
async def test_greeting_with_no_numbers_passes(db: AsyncSession, monkeypatch) -> None:
    company = await _company(db)
    _stub_agent(monkeypatch, text="Hi! How can I help with your business?", tool_outputs=[])
    reply = await answer_question(db, company, "hello")
    assert reply == "Hi! How can I help with your business?"


@pytest.mark.asyncio
async def test_agent_error_returns_fallback_never_raises(db: AsyncSession, monkeypatch) -> None:
    company = await _company(db)

    async def _boom(*, system_prompt, messages, ctx, settings=None):
        raise RuntimeError("all providers exhausted")

    monkeypatch.setattr(assistant_mod, "run_agent", _boom)
    reply = await answer_question(db, company, "what's my cash")
    assert reply == _SAFE_FALLBACK
