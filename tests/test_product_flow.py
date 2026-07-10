"""Guided add-product workflow — lets an onboarded company add more products
later via the same one-by-one/bulk process as onboarding.

Drives app/services/workflows/product_flow.py directly, same lightweight
convention as tests/test_onboarding_flow.py (the webhook wiring itself is
covered by tests/test_webhooks_whatsapp.py's keyword-trigger tests).

    uv run alembic upgrade head
    uv run pytest tests/test_product_flow.py -v
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models.company import Company, OnboardingState
from app.models.product import Product
from app.services.workflows.product_flow import (
    handle_add_product_workflow_message,
    start_add_product_workflow,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


def _unique_number() -> str:
    return f"+919{uuid.uuid4().int % 1_000_000_000:09d}"


async def _fresh_company(db: AsyncSession) -> Company:
    company = Company(
        business_name="Product Flow Co",
        owner_name="Owner",
        whatsapp_number=_unique_number(),
        subscription_active=True,
        onboarding_state=OnboardingState.completed,
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company


async def _send(db: AsyncSession, company: Company, text: str) -> str:
    reply = await handle_add_product_workflow_message(db, company, text)
    await db.flush()
    return reply


async def _count(db: AsyncSession, company_id: uuid.UUID) -> int:
    return await db.scalar(
        select(func.count()).select_from(Product).where(Product.company_id == company_id)
    )


@pytest.mark.asyncio
async def test_start_sets_active_workflow_and_asks_mode(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    reply = start_add_product_workflow(company)
    assert company.active_workflow == "add_product"
    assert "one by one" in reply.lower()
    assert "bulk" in reply.lower()


@pytest.mark.asyncio
async def test_one_by_one_add_then_done_clears_workflow(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    start_add_product_workflow(company)

    await _send(db, company, "one by one")
    await _send(db, company, "Rice")
    reply = await _send(db, company, "100")
    assert "Added product: Rice" in reply
    assert await _count(db, company.id) == 1

    reply = await _send(db, company, "done")
    assert company.active_workflow is None
    assert company.workflow_scratch is None
    assert "done" in reply.lower()

    product = await db.scalar(select(Product).where(Product.company_id == company.id))
    assert product.name == "Rice"
    assert product.stock_quantity == Decimal("100")


@pytest.mark.asyncio
async def test_bulk_add_saves_each_item_and_prices(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    start_add_product_workflow(company)

    await _send(db, company, "bulk")
    reply = await _send(db, company, "rice - 400, dal - 450")
    assert "Added 2 product" in reply
    assert await _count(db, company.id) == 2

    reply = await _send(db, company, "done")
    assert company.active_workflow is None
    assert "done" in reply.lower()

    rice = await db.scalar(select(Product).where(Product.name == "rice"))
    dal = await db.scalar(select(Product).where(Product.name == "dal"))
    assert rice.selling_price == Decimal("400.00")
    assert dal.selling_price == Decimal("450.00")


@pytest.mark.asyncio
async def test_cancel_mid_flow_clears_workflow_without_saving(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    start_add_product_workflow(company)
    await _send(db, company, "one by one")
    await _send(db, company, "Rice")
    reply = await _send(db, company, "cancel")
    assert company.active_workflow is None
    assert company.workflow_scratch is None
    assert "cancelled" in reply.lower()
    assert await _count(db, company.id) == 0


@pytest.mark.asyncio
async def test_unrecognized_mode_reasks_without_advancing(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    start_add_product_workflow(company)
    reply = await _send(db, company, "huh?")
    assert company.workflow_scratch["step"] == "awaiting_mode"
    assert "bulk" in reply.lower()


@pytest.mark.asyncio
async def test_done_at_mode_step_skips_without_saving(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    start_add_product_workflow(company)
    reply = await _send(db, company, "done")
    assert company.active_workflow is None
    assert await _count(db, company.id) == 0
    assert "no products" in reply.lower()
