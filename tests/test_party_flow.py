"""Guided add-dealer / add-supplier workflows — let an onboarded company add
a dealer or supplier any time via the same one-by-one/bulk process as
onboarding.

Drives app/services/workflows/party_flow.py directly, same lightweight
convention as tests/test_product_flow.py (the webhook wiring itself is
covered by tests/test_webhooks_whatsapp.py's keyword-trigger tests).

    uv run alembic upgrade head
    uv run pytest tests/test_party_flow.py -v
"""

from __future__ import annotations

import uuid

import pytest
from app.models.company import Company, OnboardingState
from app.models.dealer import Dealer
from app.models.supplier import Supplier
from app.services.workflows.party_flow import (
    handle_add_dealer_workflow_message,
    handle_add_supplier_workflow_message,
    start_add_dealer_workflow,
    start_add_supplier_workflow,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


def _unique_number() -> str:
    return f"+919{uuid.uuid4().int % 1_000_000_000:09d}"


async def _fresh_company(db: AsyncSession) -> Company:
    company = Company(
        business_name="Party Flow Co",
        owner_name="Owner",
        whatsapp_number=_unique_number(),
        subscription_active=True,
        onboarding_state=OnboardingState.completed,
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company


async def _count(db: AsyncSession, model, company_id: uuid.UUID) -> int:
    return await db.scalar(
        select(func.count()).select_from(model).where(model.company_id == company_id)
    )


# ── Add dealer ────────────────────────────────────────────────────────────────


async def _send_dealer(db: AsyncSession, company: Company, text: str) -> str:
    reply = await handle_add_dealer_workflow_message(db, company, text)
    await db.flush()
    return reply


@pytest.mark.asyncio
async def test_dealer_start_sets_active_workflow_and_asks_mode(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    reply = start_add_dealer_workflow(company)
    assert company.active_workflow == "add_dealer"
    assert "one by one" in reply.lower()
    assert "bulk" in reply.lower()


@pytest.mark.asyncio
async def test_dealer_one_by_one_add_then_done_clears_workflow(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    start_add_dealer_workflow(company)

    await _send_dealer(db, company, "one by one")
    await _send_dealer(db, company, "Ram Traders")
    reply = await _send_dealer(db, company, "9876543210")
    assert "credit" in reply.lower()
    reply = await _send_dealer(db, company, "15")
    assert "Added dealer Ram Traders" in reply
    assert await _count(db, Dealer, company.id) == 1

    reply = await _send_dealer(db, company, "done")
    assert company.active_workflow is None
    assert company.workflow_scratch is None
    assert "done" in reply.lower()

    dealer = await db.scalar(select(Dealer).where(Dealer.company_id == company.id))
    assert dealer.name == "Ram Traders"
    assert dealer.phone == "9876543210"
    assert dealer.payment_terms_days == 15


@pytest.mark.asyncio
async def test_dealer_one_by_one_loops_for_a_second_dealer(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    start_add_dealer_workflow(company)
    await _send_dealer(db, company, "one by one")
    await _send_dealer(db, company, "Ram Traders")
    await _send_dealer(db, company, "skip")
    await _send_dealer(db, company, "skip")

    await _send_dealer(db, company, "Shree Enterprises")
    await _send_dealer(db, company, "skip")
    reply = await _send_dealer(db, company, "skip")
    assert "Added dealer Shree Enterprises" in reply
    assert await _count(db, Dealer, company.id) == 2


@pytest.mark.asyncio
async def test_dealer_bulk_add_saves_each_item(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    start_add_dealer_workflow(company)

    await _send_dealer(db, company, "bulk")
    reply = await _send_dealer(
        db, company, "Ram Traders, 9876543210, 15\nShree Enterprises, skip, skip"
    )
    assert "Added 2 dealer" in reply
    assert await _count(db, Dealer, company.id) == 2

    reply = await _send_dealer(db, company, "done")
    assert company.active_workflow is None
    assert "done" in reply.lower()

    ram = await db.scalar(
        select(Dealer).where(Dealer.company_id == company.id, Dealer.name == "Ram Traders")
    )
    assert ram.phone == "9876543210"
    assert ram.payment_terms_days == 15


@pytest.mark.asyncio
async def test_dealer_bulk_bad_credit_days_reasks(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    start_add_dealer_workflow(company)
    await _send_dealer(db, company, "bulk")

    reply = await _send_dealer(db, company, "Ram Traders, 9876543210, lots")
    assert company.workflow_scratch["step"] == "awaiting_bulk"  # stayed
    assert "couldn't read" in reply.lower()
    assert await _count(db, Dealer, company.id) == 0


@pytest.mark.asyncio
async def test_dealer_cancel_mid_flow_clears_workflow_without_saving(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    start_add_dealer_workflow(company)
    await _send_dealer(db, company, "one by one")
    await _send_dealer(db, company, "Ram Traders")
    reply = await _send_dealer(db, company, "cancel")
    assert company.active_workflow is None
    assert company.workflow_scratch is None
    assert "cancelled" in reply.lower()
    assert await _count(db, Dealer, company.id) == 0


@pytest.mark.asyncio
async def test_dealer_unrecognized_mode_reasks_without_advancing(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    start_add_dealer_workflow(company)
    reply = await _send_dealer(db, company, "huh?")
    assert company.workflow_scratch["step"] == "awaiting_mode"
    assert "bulk" in reply.lower()


@pytest.mark.asyncio
async def test_dealer_done_at_mode_step_skips_without_saving(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    start_add_dealer_workflow(company)
    reply = await _send_dealer(db, company, "done")
    assert company.active_workflow is None
    assert await _count(db, Dealer, company.id) == 0
    assert "no dealers" in reply.lower()


# ── Add supplier (same shape as dealer) ────────────────────────────────────────


async def _send_supplier(db: AsyncSession, company: Company, text: str) -> str:
    reply = await handle_add_supplier_workflow_message(db, company, text)
    await db.flush()
    return reply


@pytest.mark.asyncio
async def test_supplier_start_sets_active_workflow_and_asks_mode(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    reply = start_add_supplier_workflow(company)
    assert company.active_workflow == "add_supplier"
    assert "one by one" in reply.lower()
    assert "bulk" in reply.lower()


@pytest.mark.asyncio
async def test_supplier_one_by_one_add_then_done_clears_workflow(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    start_add_supplier_workflow(company)

    await _send_supplier(db, company, "one by one")
    await _send_supplier(db, company, "Metro Distributors")
    reply = await _send_supplier(db, company, "9988776655")
    assert "pay" in reply.lower()
    reply = await _send_supplier(db, company, "30")
    assert "Added supplier Metro Distributors" in reply
    assert await _count(db, Supplier, company.id) == 1

    reply = await _send_supplier(db, company, "done")
    assert company.active_workflow is None
    assert company.workflow_scratch is None
    assert "done" in reply.lower()

    supplier = await db.scalar(select(Supplier).where(Supplier.company_id == company.id))
    assert supplier.name == "Metro Distributors"
    assert supplier.phone == "9988776655"
    assert supplier.payment_terms_days == 30


@pytest.mark.asyncio
async def test_supplier_bulk_add_saves_each_item(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    start_add_supplier_workflow(company)

    await _send_supplier(db, company, "bulk")
    reply = await _send_supplier(
        db, company, "Metro Distributors, 9988776655, 30\nSuresh Wholesale, skip, skip"
    )
    assert "Added 2 supplier" in reply
    assert await _count(db, Supplier, company.id) == 2

    reply = await _send_supplier(db, company, "done")
    assert company.active_workflow is None
    assert "done" in reply.lower()

    metro = await db.scalar(
        select(Supplier).where(
            Supplier.company_id == company.id, Supplier.name == "Metro Distributors"
        )
    )
    assert metro.phone == "9988776655"
    assert metro.payment_terms_days == 30


@pytest.mark.asyncio
async def test_supplier_cancel_mid_flow_clears_workflow_without_saving(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    start_add_supplier_workflow(company)
    await _send_supplier(db, company, "one by one")
    await _send_supplier(db, company, "Metro Distributors")
    reply = await _send_supplier(db, company, "cancel")
    assert company.active_workflow is None
    assert company.workflow_scratch is None
    assert "cancelled" in reply.lower()
    assert await _count(db, Supplier, company.id) == 0


@pytest.mark.asyncio
async def test_supplier_unrecognized_mode_reasks_without_advancing(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    start_add_supplier_workflow(company)
    reply = await _send_supplier(db, company, "huh?")
    assert company.workflow_scratch["step"] == "awaiting_mode"
    assert "bulk" in reply.lower()


@pytest.mark.asyncio
async def test_supplier_done_at_mode_step_skips_without_saving(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    start_add_supplier_workflow(company)
    reply = await _send_supplier(db, company, "done")
    assert company.active_workflow is None
    assert await _count(db, Supplier, company.id) == 0
    assert "no suppliers" in reply.lower()
