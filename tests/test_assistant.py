"""LLM assistant tests — the money-safety gate is the important part.

The LLM is stubbed (no network): one stub captures the grounded context handed
to the model to prove it contains the real outstanding; another returns a
hallucinated ₹ figure to prove `find_unverified_amounts` swaps it for the safe
fallback. A real-LLM smoke test is gated on a configured key.

    uv run alembic upgrade head
    uv run pytest tests/test_assistant.py -v
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

import pytest
from app.models.company import Company, OnboardingState
from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceDirection, InvoiceSource, InvoiceStatus
from app.services import assistant as assistant_mod
from app.services.assistant import _SAFE_FALLBACK, answer_question
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class _FakeLLMResult:
    text: str
    provider: str = "fake"
    model: str = "fake-1"
    latency_seconds: float = 0.0


def _unique_number() -> str:
    return f"+919{uuid.uuid4().int % 1_000_000_000:09d}"


async def _company_with_receivable(db: AsyncSession, amount: str = "42000.00") -> Company:
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

    dealer = Dealer(company_id=company.id, name="Ram Traders")
    db.add(dealer)
    await db.commit()
    await db.refresh(dealer)

    db.add(
        Invoice(
            company_id=company.id,
            invoice_number=f"INV-{uuid.uuid4().hex[:8]}",
            direction=InvoiceDirection.receivable,
            dealer_id=dealer.id,
            invoice_date=date.today() - timedelta(days=10),
            due_date=date.today() + timedelta(days=5),
            subtotal=Decimal(amount),
            gst_amount=Decimal("0.00"),
            total_amount=Decimal(amount),
            status=InvoiceStatus.Pending,
            source=InvoiceSource.csv_import,
        )
    )
    await db.commit()
    return company


@pytest.mark.asyncio
async def test_context_contains_real_outstanding_and_answer_passes(
    db: AsyncSession, monkeypatch
) -> None:
    company = await _company_with_receivable(db, amount="42000.00")
    captured = {}

    async def _fake_llm(*, system_prompt: str, user_content: str):
        captured["user_content"] = user_content
        # Model answers using the grounded figure — must pass the gate.
        return _FakeLLMResult(text="Ram Traders owes you ₹42,000.")

    monkeypatch.setattr(assistant_mod, "generate_with_fallback", _fake_llm)

    reply = await answer_question(db, company, "how much does ram owe")
    assert reply == "Ram Traders owes you ₹42,000."
    # The deterministic context handed to the model carried the real number and party.
    assert "42000.00" in captured["user_content"]
    assert "Ram Traders" in captured["user_content"]


@pytest.mark.asyncio
async def test_hallucinated_amount_is_gated_to_fallback(db: AsyncSession, monkeypatch) -> None:
    company = await _company_with_receivable(db, amount="42000.00")

    async def _fake_llm(*, system_prompt: str, user_content: str):
        # ₹99,999 is NOT in the grounded context — must be rejected.
        return _FakeLLMResult(text="Ram Traders owes you ₹99,999.")

    monkeypatch.setattr(assistant_mod, "generate_with_fallback", _fake_llm)

    reply = await answer_question(db, company, "how much does ram owe")
    assert reply == _SAFE_FALLBACK


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "hallucinated",
    [
        "Ram owes you ₹99,999.",  # ₹-prefixed
        "Ram owes you Rs 5,00,000.",  # Rs marker, no ₹ (prompt-injection style)
        "Ram owes you INR 500000.",  # INR marker
        "Ram owes you 500000 rupees.",  # marker after the number
        "Ram owes you 5,00,000.",  # comma-grouped, no marker
        "Ram owes you 987654.",  # bare 6-digit, no marker at all
    ],
)
async def test_unverified_money_any_framing_is_gated(
    db: AsyncSession, monkeypatch, hallucinated: str
) -> None:
    # None of these figures are in the grounded context (only ₹42,000 is), so
    # every framing — including ones without a ₹ prefix — must be rejected.
    company = await _company_with_receivable(db, amount="42000.00")

    async def _fake_llm(*, system_prompt: str, user_content: str):
        return _FakeLLMResult(text=hallucinated)

    monkeypatch.setattr(assistant_mod, "generate_with_fallback", _fake_llm)
    reply = await answer_question(db, company, "how much does ram owe")
    assert reply == _SAFE_FALLBACK


@pytest.mark.asyncio
async def test_llm_unavailable_returns_fallback(db: AsyncSession, monkeypatch) -> None:
    from app.services.llm import NoApiKeyConfiguredError

    company = await _company_with_receivable(db)

    async def _boom(*, system_prompt: str, user_content: str):
        raise NoApiKeyConfiguredError("no key")

    monkeypatch.setattr(assistant_mod, "generate_with_fallback", _boom)

    reply = await answer_question(db, company, "what's my cash")
    assert reply == _SAFE_FALLBACK


@pytest.mark.asyncio
async def test_unexpected_error_returns_fallback_never_raises(
    db: AsyncSession, monkeypatch
) -> None:
    # A non-fallback provider 4xx (e.g. revoked key) or any other error must not
    # propagate — the webhook would otherwise 500 and Meta would retry-storm.
    company = await _company_with_receivable(db)

    async def _boom(*, system_prompt: str, user_content: str):
        raise RuntimeError("401 unauthorized")

    monkeypatch.setattr(assistant_mod, "generate_with_fallback", _boom)

    reply = await answer_question(db, company, "what's my cash")
    assert reply == _SAFE_FALLBACK


@pytest.mark.asyncio
async def test_legit_grouped_amount_passes(db: AsyncSession, monkeypatch) -> None:
    # The real figure written Indian-grouped with ₹ must still pass the gate.
    company = await _company_with_receivable(db, amount="319828.00")

    async def _fake_llm(*, system_prompt: str, user_content: str):
        return _FakeLLMResult(text="Ram Traders owes you ₹3,19,828.")

    monkeypatch.setattr(assistant_mod, "generate_with_fallback", _fake_llm)
    reply = await answer_question(db, company, "how much does ram owe")
    assert reply == "Ram Traders owes you ₹3,19,828."
