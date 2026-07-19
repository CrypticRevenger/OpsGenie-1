"""Guided "stock take" workflow — bulk stock recount/adjustment.

Drives app/services/workflows/stock_take_flow.py directly, same lightweight
convention as tests/test_party_flow.py. Covers the multi-product loop,
absolute vs. signed-delta parsing, the summary+confirm step, and the
negative-stock warning (flagged, not blocked).

    uv run alembic upgrade head
    uv run pytest tests/test_stock_take_flow.py -v
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models.business_event import BusinessEvent, BusinessEventType
from app.models.company import Company, OnboardingState
from app.models.product import Product
from app.services.workflows.stock_take_flow import (
    handle_stock_take_workflow_message,
    start_stock_take_workflow,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _unique_number() -> str:
    return f"+919{uuid.uuid4().int % 1_000_000_000:09d}"


async def _fresh_company(db: AsyncSession) -> Company:
    company = Company(
        business_name="Stock Take Co",
        owner_name="Owner",
        whatsapp_number=_unique_number(),
        subscription_active=True,
        onboarding_state=OnboardingState.completed,
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company


async def _make_product(
    db: AsyncSession, company_id: uuid.UUID, name: str = "Widget", *, stock: Decimal = Decimal("50")
) -> Product:
    product = Product(company_id=company_id, name=name, stock_quantity=stock)
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


async def _send(db: AsyncSession, company: Company, text: str) -> str:
    reply = await handle_stock_take_workflow_message(db, company, text)
    await db.flush()
    return reply


@pytest.mark.asyncio
async def test_stock_take_start_sets_active_workflow(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    reply = start_stock_take_workflow(company)
    assert company.active_workflow == "stock_take"
    assert "stock take" in reply.lower()


@pytest.mark.asyncio
async def test_stock_take_done_with_nothing_collected(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    start_stock_take_workflow(company)
    reply = await _send(db, company, "done")
    assert "no changes" in reply.lower()
    assert company.active_workflow is None


@pytest.mark.asyncio
async def test_stock_take_absolute_recount_full_round_trip(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    product = await _make_product(db, company.id, stock=Decimal("50"))

    start_stock_take_workflow(company)
    reply = await _send(db, company, "Widget")
    assert "widget" in reply.lower()
    reply = await _send(db, company, "40")
    assert "40" in reply

    await _send(db, company, "done")
    await _send(db, company, "recount after audit")
    reply = await _send(db, company, "YES")
    await db.commit()

    assert "✅" in reply
    await db.refresh(product)
    assert product.stock_quantity == Decimal("40")

    event = await db.scalar(
        select(BusinessEvent).where(BusinessEvent.event_type == BusinessEventType.stock_adjusted)
    )
    assert event is not None
    assert event.payload["mode"] == "absolute"
    assert event.payload["reason"] == "recount after audit"


@pytest.mark.asyncio
async def test_stock_take_signed_delta_positive_and_negative(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    soap = await _make_product(db, company.id, name="Soap", stock=Decimal("100"))
    rice = await _make_product(db, company.id, name="Rice", stock=Decimal("20"))

    start_stock_take_workflow(company)
    await _send(db, company, "Soap")
    await _send(db, company, "+15")
    await _send(db, company, "Rice")
    await _send(db, company, "-3")
    await _send(db, company, "done")
    await _send(db, company, "skip")
    reply = await _send(db, company, "yes")
    await db.commit()

    assert "✅" in reply
    await db.refresh(soap)
    await db.refresh(rice)
    assert soap.stock_quantity == Decimal("115")
    assert rice.stock_quantity == Decimal("17")


@pytest.mark.asyncio
async def test_stock_take_negative_result_is_flagged_not_blocked(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    product = await _make_product(db, company.id, stock=Decimal("5"))

    start_stock_take_workflow(company)
    await _send(db, company, "Widget")
    await _send(db, company, "-10")
    await _send(db, company, "done")
    await _send(db, company, "skip")
    reply = await _send(db, company, "yes")
    await db.commit()

    assert "negative" in reply.lower()
    await db.refresh(product)
    assert product.stock_quantity == Decimal("-5")


@pytest.mark.asyncio
async def test_stock_take_confirm_no_applies_nothing(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    product = await _make_product(db, company.id, stock=Decimal("50"))

    start_stock_take_workflow(company)
    await _send(db, company, "Widget")
    await _send(db, company, "40")
    await _send(db, company, "done")
    await _send(db, company, "skip")
    reply = await _send(db, company, "no")
    await db.commit()

    assert "cancel" in reply.lower()
    assert company.active_workflow is None
    await db.refresh(product)
    assert product.stock_quantity == Decimal("50")


@pytest.mark.asyncio
async def test_stock_take_multi_product_loop(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    soap = await _make_product(db, company.id, name="Soap", stock=Decimal("10"))
    rice = await _make_product(db, company.id, name="Rice", stock=Decimal("10"))
    oil = await _make_product(db, company.id, name="Oil", stock=Decimal("10"))

    start_stock_take_workflow(company)
    for name, value in (("Soap", "40"), ("Rice", "+12"), ("Oil", "-3")):
        await _send(db, company, name)
        await _send(db, company, value)
    await _send(db, company, "done")
    await _send(db, company, "skip")
    reply = await _send(db, company, "yes")
    await db.commit()

    assert "3 product" in reply.lower()
    await db.refresh(soap)
    await db.refresh(rice)
    await db.refresh(oil)
    assert soap.stock_quantity == Decimal("40")
    assert rice.stock_quantity == Decimal("22")
    assert oil.stock_quantity == Decimal("7")


@pytest.mark.asyncio
async def test_stock_take_cancel_mid_flow(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    await _make_product(db, company.id, stock=Decimal("50"))

    start_stock_take_workflow(company)
    await _send(db, company, "Widget")
    reply = await _send(db, company, "cancel")
    assert "cancel" in reply.lower()
    assert company.active_workflow is None


@pytest.mark.asyncio
async def test_stock_take_disambiguates_duplicate_product_names(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    db.add_all(
        [
            Product(company_id=company.id, name="Widget", stock_quantity=Decimal("10")),
            Product(company_id=company.id, name="Widget", stock_quantity=Decimal("20")),
        ]
    )
    await db.commit()

    start_stock_take_workflow(company)
    reply = await _send(db, company, "Widget")
    assert "2" in reply
    reply = await _send(db, company, "2")
    assert "widget" in reply.lower()


@pytest.mark.asyncio
async def test_stock_take_invalid_value_reprompts(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    await _make_product(db, company.id, stock=Decimal("50"))

    start_stock_take_workflow(company)
    await _send(db, company, "Widget")
    reply = await _send(db, company, "not a number")
    assert "number" in reply.lower()
