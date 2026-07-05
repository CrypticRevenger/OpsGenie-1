"""Guided WhatsApp onboarding state-machine tests.

Drives app/services/onboarding_flow.handle_onboarding_message directly (the
webhook wiring is covered in test_webhooks_whatsapp.py). Asserts each state
transition and the rows the conversation creates.

    uv run alembic upgrade head
    uv run pytest tests/test_onboarding_flow.py -v
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models.company import Company, OnboardingState
from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceDirection
from app.models.product import Product
from app.models.supplier import Supplier
from app.services.onboarding_flow import handle_onboarding_message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


def _unique_number() -> str:
    return f"+919{uuid.uuid4().int % 1_000_000_000:09d}"


async def _fresh_company(db: AsyncSession) -> Company:
    company = Company(
        business_name="Onboard Co",
        owner_name="Owner",
        whatsapp_number=_unique_number(),
        subscription_active=True,
        onboarding_state=OnboardingState.not_started,
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company


async def _send(db: AsyncSession, company: Company, text: str) -> str:
    reply = await handle_onboarding_message(db, company, text)
    await db.flush()
    return reply


async def _count(db: AsyncSession, model, company_id: uuid.UUID) -> int:
    return await db.scalar(
        select(func.count()).select_from(model).where(model.company_id == company_id)
    )


@pytest.mark.asyncio
async def test_full_happy_path(db: AsyncSession) -> None:
    company = await _fresh_company(db)

    # Kick-off
    await _send(db, company, "hi")
    assert company.onboarding_state == OnboardingState.awaiting_business_type

    # Business type
    await _send(db, company, "Pharma Distributor")
    assert company.business_type == "Pharma Distributor"
    assert company.onboarding_state == OnboardingState.product_awaiting_name

    # Products (one, then done)
    await _send(db, company, "Paracetamol")
    await _send(db, company, "done")
    assert company.onboarding_state == OnboardingState.dealer_awaiting_name
    assert await _count(db, Product, company.id) == 1

    # Dealer: name -> phone -> credit
    await _send(db, company, "Ram Traders")
    assert company.onboarding_state == OnboardingState.dealer_awaiting_phone
    await _send(db, company, "9876543210")
    assert company.onboarding_state == OnboardingState.dealer_awaiting_credit
    await _send(db, company, "15")
    assert company.onboarding_state == OnboardingState.dealer_awaiting_name
    await _send(db, company, "done")
    assert company.onboarding_state == OnboardingState.supplier_awaiting_name

    dealer = await db.scalar(select(Dealer).where(Dealer.company_id == company.id))
    assert dealer.name == "Ram Traders"
    assert dealer.phone == "9876543210"
    assert dealer.payment_terms_days == 15

    # Supplier: name -> skip phone -> skip credit
    await _send(db, company, "ABC Pharma")
    await _send(db, company, "skip")
    await _send(db, company, "skip")
    assert company.onboarding_state == OnboardingState.supplier_awaiting_name
    await _send(db, company, "done")
    assert company.onboarding_state == OnboardingState.awaiting_opening_balance
    supplier = await db.scalar(select(Supplier).where(Supplier.company_id == company.id))
    assert supplier.name == "ABC Pharma"
    assert supplier.phone is None
    assert supplier.payment_terms_days is None

    # Opening cash
    await _send(db, company, "3,20,000")
    assert company.opening_balance == Decimal("320000")
    assert company.onboarding_state == OnboardingState.receivable_ask

    # Receivable — reuses the existing Ram Traders dealer (no duplicate)
    await _send(db, company, "yes")
    await _send(db, company, "Ram Traders")
    await _send(db, company, "42000")
    await _send(db, company, "15 days")
    assert company.onboarding_state == OnboardingState.receivable_ask
    await _send(db, company, "no")
    assert company.onboarding_state == OnboardingState.payable_ask
    assert await _count(db, Dealer, company.id) == 1  # dealer was not duplicated

    # Payable — reuses ABC Pharma supplier
    await _send(db, company, "yes")
    await _send(db, company, "ABC Pharma")
    await _send(db, company, "82000")
    await _send(db, company, "friday")
    assert company.onboarding_state == OnboardingState.payable_ask
    await _send(db, company, "no")
    assert company.onboarding_state == OnboardingState.awaiting_language
    assert await _count(db, Supplier, company.id) == 1

    # Language
    await _send(db, company, "Hindi")
    assert company.preferred_language == "Hindi"
    assert company.onboarding_state == OnboardingState.awaiting_briefing_hour

    # Briefing hour -> completed
    reply = await _send(db, company, "7")
    assert company.briefing_hour == 7
    assert company.onboarding_state == OnboardingState.completed
    assert "Setup complete" in reply

    # Two opening invoices, one each direction
    invoices = (await db.scalars(select(Invoice).where(Invoice.company_id == company.id))).all()
    assert len(invoices) == 2
    by_dir = {inv.direction: inv for inv in invoices}
    assert by_dir[InvoiceDirection.receivable].total_amount == Decimal("42000")
    assert by_dir[InvoiceDirection.payable].total_amount == Decimal("82000")
    assert by_dir[InvoiceDirection.receivable].dealer_id == dealer.id
    assert by_dir[InvoiceDirection.payable].supplier_id == supplier.id


@pytest.mark.asyncio
async def test_skip_everything_optional(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    await _send(db, company, "hi")
    await _send(db, company, "Kirana")
    await _send(db, company, "done")  # no products
    await _send(db, company, "done")  # no dealers
    await _send(db, company, "done")  # no suppliers
    await _send(db, company, "50000")  # opening cash
    await _send(db, company, "no")  # no receivables
    await _send(db, company, "no")  # no payables
    await _send(db, company, "English")  # language
    assert company.preferred_language == "English"
    await _send(db, company, "8")  # briefing hour
    assert company.onboarding_state == OnboardingState.completed
    assert company.briefing_hour == 8
    assert await _count(db, Product, company.id) == 0
    assert await _count(db, Dealer, company.id) == 0
    assert await _count(db, Invoice, company.id) == 0


@pytest.mark.asyncio
async def test_bad_amount_reasks_without_advancing(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    await _send(db, company, "hi")
    await _send(db, company, "FMCG")
    await _send(db, company, "done")
    await _send(db, company, "done")
    await _send(db, company, "done")
    assert company.onboarding_state == OnboardingState.awaiting_opening_balance
    reply = await _send(db, company, "lots of money")
    assert company.onboarding_state == OnboardingState.awaiting_opening_balance  # stayed
    assert "amount" in reply.lower()
    await _send(db, company, "100000")
    assert company.onboarding_state == OnboardingState.receivable_ask


@pytest.mark.asyncio
async def test_bad_hour_reasks(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    company.onboarding_state = OnboardingState.awaiting_briefing_hour
    await db.flush()
    reply = await _send(db, company, "morning")
    assert company.onboarding_state == OnboardingState.awaiting_briefing_hour
    assert "hour" in reply.lower()
    reply = await _send(db, company, "25")  # out of range
    assert company.onboarding_state == OnboardingState.awaiting_briefing_hour
    # 23 is a valid clock hour but rejected — it would make retry hour 24 (never
    # fires) and distort the notification-window gate, so only 5-11 is accepted.
    await _send(db, company, "23")
    assert company.onboarding_state == OnboardingState.awaiting_briefing_hour
    assert company.briefing_hour is None
    await _send(db, company, "9")
    assert company.onboarding_state == OnboardingState.completed
    assert company.briefing_hour == 9
