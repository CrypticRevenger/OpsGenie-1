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
    handle_delete_product_workflow_message,
    handle_update_product_workflow_message,
    start_add_product_workflow,
    start_delete_product_workflow,
    start_update_price_workflow,
    start_update_product_workflow,
    start_update_purchase_price_workflow,
    start_update_stock_workflow,
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
    assert "unit" in reply.lower()
    reply = await _send(db, company, "kg")
    assert "selling price" in reply.lower()
    reply = await _send(db, company, "40")
    assert "purchase price" in reply.lower()
    reply = await _send(db, company, "30")
    assert "Added product: Rice" in reply
    assert await _count(db, company.id) == 1

    reply = await _send(db, company, "done")
    assert company.active_workflow is None
    assert company.workflow_scratch is None
    assert "done" in reply.lower()

    product = await db.scalar(select(Product).where(Product.company_id == company.id))
    assert product.name == "Rice"
    assert product.stock_quantity == Decimal("100")
    assert product.unit == "kg"
    assert product.selling_price == Decimal("40.00")
    assert product.purchase_price == Decimal("30.00")


@pytest.mark.asyncio
async def test_one_by_one_add_rejects_negative_quantity_but_allows_zero(
    db: AsyncSession,
) -> None:
    company = await _fresh_company(db)
    start_add_product_workflow(company)
    await _send(db, company, "one by one")
    await _send(db, company, "Rice")
    reply = await _send(db, company, "-5")
    assert company.workflow_scratch["step"] == "awaiting_quantity"  # stayed
    assert "invalid" in reply.lower() or "number" in reply.lower()

    reply = await _send(db, company, "0")  # zero stock is legitimate (not yet restocked)
    assert "unit" in reply.lower()


@pytest.mark.asyncio
async def test_one_by_one_add_rejects_zero_and_negative_price(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    start_add_product_workflow(company)
    await _send(db, company, "one by one")
    await _send(db, company, "Rice")
    await _send(db, company, "100")
    await _send(db, company, "kg")

    reply = await _send(db, company, "0")
    assert company.workflow_scratch["step"] == "awaiting_price"  # stayed
    reply = await _send(db, company, "-10")
    assert company.workflow_scratch["step"] == "awaiting_price"  # stayed

    reply = await _send(db, company, "40")
    assert "purchase price" in reply.lower()


@pytest.mark.asyncio
async def test_one_by_one_add_rejects_zero_and_negative_purchase_price(
    db: AsyncSession,
) -> None:
    company = await _fresh_company(db)
    start_add_product_workflow(company)
    await _send(db, company, "one by one")
    await _send(db, company, "Rice")
    await _send(db, company, "100")
    await _send(db, company, "kg")
    await _send(db, company, "40")

    reply = await _send(db, company, "0")
    assert company.workflow_scratch["step"] == "awaiting_purchase_price"  # stayed
    reply = await _send(db, company, "-30")
    assert company.workflow_scratch["step"] == "awaiting_purchase_price"  # stayed

    reply = await _send(db, company, "30")
    assert "Added product: Rice" in reply


@pytest.mark.asyncio
async def test_one_by_one_add_asks_gst_when_company_varies_by_product(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    company.gst_varies_by_product = True
    await db.flush()
    start_add_product_workflow(company)

    await _send(db, company, "one by one")
    await _send(db, company, "Rice")
    await _send(db, company, "100")
    await _send(db, company, "kg")
    await _send(db, company, "40")
    reply = await _send(db, company, "30")
    assert "GST%" in reply
    reply = await _send(db, company, "5")
    assert "Added product: Rice" in reply

    product = await db.scalar(select(Product).where(Product.company_id == company.id))
    assert product.gst_rate == Decimal("5.00")


@pytest.mark.asyncio
async def test_bulk_add_saves_each_item_and_prices(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    start_add_product_workflow(company)

    await _send(db, company, "bulk")
    reply = await _send(
        db, company, "rice, 300, 400, kg, skip, skip\ndal, 320, 450, kg, skip, skip"
    )
    assert "Added 2 product" in reply
    assert await _count(db, company.id) == 2

    reply = await _send(db, company, "done")
    assert company.active_workflow is None
    assert "done" in reply.lower()

    rice = await db.scalar(
        select(Product).where(Product.company_id == company.id, Product.name == "rice")
    )
    dal = await db.scalar(
        select(Product).where(Product.company_id == company.id, Product.name == "dal")
    )
    assert rice.selling_price == Decimal("400.00")
    assert rice.unit == "kg"
    assert rice.purchase_price == Decimal("300.00")
    assert dal.selling_price == Decimal("450.00")
    assert dal.unit == "kg"
    assert dal.purchase_price == Decimal("320.00")


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


# ── Delete product ───────────────────────────────────────────────────────────


async def _send_delete(db: AsyncSession, company: Company, text: str) -> str:
    reply = await handle_delete_product_workflow_message(db, company, text)
    await db.flush()
    return reply


@pytest.mark.asyncio
async def test_delete_single_match_confirms_then_deletes(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    db.add(Product(company_id=company.id, name="Rice", stock_quantity=Decimal("100")))
    await db.commit()

    reply = start_delete_product_workflow(company)
    assert "which product" in reply.lower()

    reply = await _send_delete(db, company, "Rice")
    assert company.workflow_scratch["step"] == "awaiting_confirm"
    assert "delete" in reply.lower() and "rice" in reply.lower()

    reply = await _send_delete(db, company, "yes")
    assert company.active_workflow is None
    assert company.workflow_scratch is None
    assert "deleted" in reply.lower()
    assert await _count(db, company.id) == 0


@pytest.mark.asyncio
async def test_delete_confirm_no_keeps_product(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    db.add(Product(company_id=company.id, name="Rice", stock_quantity=Decimal("100")))
    await db.commit()

    start_delete_product_workflow(company)
    await _send_delete(db, company, "Rice")
    reply = await _send_delete(db, company, "no")
    assert company.active_workflow is None
    assert "not deleted" in reply.lower()
    assert await _count(db, company.id) == 1


@pytest.mark.asyncio
async def test_delete_not_found_reasks_without_advancing(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    start_delete_product_workflow(company)
    reply = await _send_delete(db, company, "Nonexistent")
    assert company.workflow_scratch["step"] == "awaiting_name"
    assert "couldn't find" in reply.lower()


@pytest.mark.asyncio
async def test_delete_multiple_matches_disambiguates_by_number(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    db.add(Product(company_id=company.id, name="Rice", stock_quantity=Decimal("100")))
    db.add(Product(company_id=company.id, name="Rice", stock_quantity=Decimal("50")))
    await db.commit()

    start_delete_product_workflow(company)
    reply = await _send_delete(db, company, "rice")  # case-insensitive match
    assert company.workflow_scratch["step"] == "awaiting_disambiguation"
    assert "found 2 products" in reply.lower()

    reply = await _send_delete(db, company, "2")
    assert company.workflow_scratch["step"] == "awaiting_confirm"

    reply = await _send_delete(db, company, "yes")
    assert "deleted" in reply.lower()
    assert await _count(db, company.id) == 1
    remaining = await db.scalar(select(Product).where(Product.company_id == company.id))
    assert remaining.stock_quantity == Decimal("100")  # the other duplicate survives


@pytest.mark.asyncio
async def test_delete_cancel_mid_flow_keeps_product(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    db.add(Product(company_id=company.id, name="Rice", stock_quantity=Decimal("100")))
    await db.commit()

    start_delete_product_workflow(company)
    await _send_delete(db, company, "Rice")
    reply = await _send_delete(db, company, "cancel")
    assert company.active_workflow is None
    assert "cancelled" in reply.lower()
    assert await _count(db, company.id) == 1


# ── Update product price ─────────────────────────────────────────────────────


async def _send_update_price(db: AsyncSession, company: Company, text: str) -> str:
    reply = await handle_update_product_workflow_message(db, company, text)
    await db.flush()
    return reply


@pytest.mark.asyncio
async def test_update_price_single_match_updates_immediately(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    db.add(
        Product(
            company_id=company.id,
            name="Rice",
            stock_quantity=Decimal("100"),
            selling_price=Decimal("400.00"),
        )
    )
    await db.commit()

    reply = start_update_price_workflow(company)
    assert "which product" in reply.lower()

    reply = await _send_update_price(db, company, "Rice")
    assert company.workflow_scratch["step"] == "awaiting_value"
    assert "₹400" in reply and "new price" in reply.lower()

    reply = await _send_update_price(db, company, "450")
    assert company.active_workflow is None
    assert company.workflow_scratch is None
    assert "updated" in reply.lower()

    product = await db.scalar(select(Product).where(Product.company_id == company.id))
    assert product.selling_price == Decimal("450.00")


@pytest.mark.asyncio
async def test_update_purchase_price_single_match_updates_immediately(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    db.add(
        Product(
            company_id=company.id,
            name="Rice",
            stock_quantity=Decimal("100"),
            selling_price=Decimal("400.00"),
            purchase_price=Decimal("300.00"),
        )
    )
    await db.commit()

    reply = start_update_purchase_price_workflow(company)
    assert "which product" in reply.lower()
    assert "purchase price" in reply.lower()

    reply = await _send_update_price(db, company, "Rice")
    assert company.workflow_scratch["step"] == "awaiting_value"
    assert "₹300" in reply and "new purchase price" in reply.lower()

    reply = await _send_update_price(db, company, "350")
    assert company.active_workflow is None
    assert company.workflow_scratch is None
    assert "updated" in reply.lower()
    assert "purchase price" in reply.lower()

    product = await db.scalar(select(Product).where(Product.company_id == company.id))
    assert product.purchase_price == Decimal("350.00")
    assert product.selling_price == Decimal("400.00")  # selling price untouched


@pytest.mark.asyncio
async def test_update_purchase_price_no_existing_price_shows_not_set(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    db.add(Product(company_id=company.id, name="Rice", stock_quantity=Decimal("100")))
    await db.commit()

    start_update_purchase_price_workflow(company)
    reply = await _send_update_price(db, company, "Rice")
    assert "not set" in reply.lower()

    await _send_update_price(db, company, "280")
    product = await db.scalar(select(Product).where(Product.company_id == company.id))
    assert product.purchase_price == Decimal("280.00")


@pytest.mark.asyncio
async def test_generic_update_product_offers_purchase_price_field(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    db.add(
        Product(
            company_id=company.id,
            name="Rice",
            stock_quantity=Decimal("100"),
            purchase_price=Decimal("300.00"),
        )
    )
    await db.commit()

    reply = start_update_product_workflow(company)
    assert "purchase price" in reply.lower()

    reply = await _send_update_price(db, company, "purchase price")
    assert company.workflow_scratch["field"] == "purchase_price"

    await _send_update_price(db, company, "Rice")
    await _send_update_price(db, company, "310")
    product = await db.scalar(select(Product).where(Product.company_id == company.id))
    assert product.purchase_price == Decimal("310.00")


@pytest.mark.asyncio
async def test_update_price_no_existing_price_shows_not_set(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    db.add(Product(company_id=company.id, name="Rice", stock_quantity=Decimal("100")))
    await db.commit()

    start_update_price_workflow(company)
    reply = await _send_update_price(db, company, "Rice")
    assert "not set" in reply.lower()

    await _send_update_price(db, company, "450")
    product = await db.scalar(select(Product).where(Product.company_id == company.id))
    assert product.selling_price == Decimal("450.00")


@pytest.mark.asyncio
async def test_update_price_bad_amount_reasks_without_advancing(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    db.add(Product(company_id=company.id, name="Rice", stock_quantity=Decimal("100")))
    await db.commit()

    start_update_price_workflow(company)
    await _send_update_price(db, company, "Rice")
    reply = await _send_update_price(db, company, "a lot")
    assert company.workflow_scratch["step"] == "awaiting_value"  # stayed
    assert "number" in reply.lower()


@pytest.mark.asyncio
async def test_update_price_to_zero_now_rejected(db: AsyncSession) -> None:
    """Deliberate tightening: a selling/purchase price of exactly 0 is a
    data-entry mistake, unlike stock (which may legitimately be 0) — the
    update-product handler used to allow it via a single `value < 0` check
    shared across all three fields.
    """
    company = await _fresh_company(db)
    db.add(
        Product(
            company_id=company.id,
            name="Rice",
            stock_quantity=Decimal("100"),
            selling_price=Decimal("400.00"),
        )
    )
    await db.commit()

    start_update_price_workflow(company)
    await _send_update_price(db, company, "Rice")
    reply = await _send_update_price(db, company, "0")
    assert company.workflow_scratch["step"] == "awaiting_value"  # stayed, not advanced
    assert "greater than zero" in reply.lower()

    product = await db.scalar(select(Product).where(Product.company_id == company.id))
    assert product.selling_price == Decimal("400.00")  # untouched


@pytest.mark.asyncio
async def test_update_stock_to_zero_still_allowed(db: AsyncSession) -> None:
    """Unlike price/purchase_price, stock may legitimately be set to 0
    (a product that's completely sold out) — the field-aware guard must not
    over-tighten this one."""
    company = await _fresh_company(db)
    db.add(
        Product(company_id=company.id, name="Rice", stock_quantity=Decimal("100"), unit="kg")
    )
    await db.commit()

    start_update_stock_workflow(company)
    await _send_update_price(db, company, "Rice")
    reply = await _send_update_price(db, company, "0")
    assert "updated" in reply.lower()

    product = await db.scalar(select(Product).where(Product.company_id == company.id))
    assert product.stock_quantity == Decimal("0")


@pytest.mark.asyncio
async def test_update_price_not_found_reasks_without_advancing(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    start_update_price_workflow(company)
    reply = await _send_update_price(db, company, "Nonexistent")
    assert company.workflow_scratch["step"] == "awaiting_name"
    assert "couldn't find" in reply.lower()


@pytest.mark.asyncio
async def test_update_price_multiple_matches_disambiguates_by_number(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    db.add(
        Product(
            company_id=company.id,
            name="Rice",
            stock_quantity=Decimal("100"),
            selling_price=Decimal("400.00"),
        )
    )
    db.add(
        Product(
            company_id=company.id,
            name="Rice",
            stock_quantity=Decimal("50"),
            selling_price=Decimal("500.00"),
        )
    )
    await db.commit()

    start_update_price_workflow(company)
    reply = await _send_update_price(db, company, "rice")  # case-insensitive match
    assert company.workflow_scratch["step"] == "awaiting_disambiguation"
    assert "found 2 products" in reply.lower()

    await _send_update_price(db, company, "2")
    assert company.workflow_scratch["step"] == "awaiting_value"
    await _send_update_price(db, company, "600")

    updated = await db.scalar(
        select(Product).where(Product.company_id == company.id, Product.stock_quantity == 50)
    )
    untouched = await db.scalar(
        select(Product).where(Product.company_id == company.id, Product.stock_quantity == 100)
    )
    assert updated.selling_price == Decimal("600.00")
    assert untouched.selling_price == Decimal("400.00")


@pytest.mark.asyncio
async def test_update_price_cancel_mid_flow_leaves_price_unchanged(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    db.add(
        Product(
            company_id=company.id,
            name="Rice",
            stock_quantity=Decimal("100"),
            selling_price=Decimal("400.00"),
        )
    )
    await db.commit()

    start_update_price_workflow(company)
    await _send_update_price(db, company, "Rice")
    reply = await _send_update_price(db, company, "cancel")
    assert company.active_workflow is None
    assert "cancelled" in reply.lower()

    product = await db.scalar(select(Product).where(Product.company_id == company.id))
    assert product.selling_price == Decimal("400.00")


# ── Update product stock, and the generic field-choice entry point ──────────


@pytest.mark.asyncio
async def test_update_stock_direct_entry_skips_field_question(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    db.add(
        Product(company_id=company.id, name="Rice", stock_quantity=Decimal("100"), unit="kg")
    )
    await db.commit()

    reply = start_update_stock_workflow(company)
    assert company.workflow_scratch == {"step": "awaiting_name", "field": "stock"}
    assert "stock" in reply.lower()

    reply = await _send_update_price(db, company, "Rice")
    assert company.workflow_scratch["step"] == "awaiting_value"
    assert "100 kg" in reply and "new stock" in reply.lower()

    reply = await _send_update_price(db, company, "250")
    assert company.active_workflow is None
    assert "updated" in reply.lower()

    product = await db.scalar(select(Product).where(Product.company_id == company.id))
    assert product.stock_quantity == Decimal("250")
    assert product.selling_price is None  # only stock changed


@pytest.mark.asyncio
async def test_generic_update_product_asks_field_first(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    db.add(
        Product(
            company_id=company.id,
            name="Rice",
            stock_quantity=Decimal("100"),
            selling_price=Decimal("400.00"),
        )
    )
    await db.commit()

    reply = start_update_product_workflow(company)
    assert company.workflow_scratch == {"step": "awaiting_field"}
    assert "price" in reply.lower() and "stock" in reply.lower()

    reply = await _send_update_price(db, company, "stock")
    assert company.workflow_scratch == {"step": "awaiting_name", "field": "stock"}
    assert "stock" in reply.lower()

    await _send_update_price(db, company, "Rice")
    await _send_update_price(db, company, "300")

    product = await db.scalar(select(Product).where(Product.company_id == company.id))
    assert product.stock_quantity == Decimal("300")
    assert product.selling_price == Decimal("400.00")  # price untouched


@pytest.mark.asyncio
async def test_generic_update_product_unrecognized_field_reasks(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    start_update_product_workflow(company)
    reply = await _send_update_price(db, company, "huh?")
    assert company.workflow_scratch["step"] == "awaiting_field"
    assert "price" in reply.lower() and "stock" in reply.lower()
