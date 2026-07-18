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
    # Language is picked first now; drive that pre-step (English) so the
    # business-field tests below start at the first business question. The
    # two-step language/script picker itself is covered by
    # test_language_selection_* below.
    await _send(db, company, "start")  # not_started -> awaiting_language
    await _send(db, company, "1")  # English -> awaiting_business_type
    return company


async def _bare_company(db: AsyncSession) -> Company:
    """A company at not_started — i.e. BEFORE the language pre-step (unlike
    _fresh_company, which drives past it). Used to exercise the language/script
    picker itself.
    """
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
    # _fresh_company already handled kick-off + the language pre-step, so we
    # start at the first business question.
    assert company.onboarding_state == OnboardingState.awaiting_business_type

    # Business type
    await _send(db, company, "Pharma Distributor")
    assert company.business_type == "Pharma Distributor"
    assert company.onboarding_state == OnboardingState.gst_mode_ask

    # GST mode: same rate for everything
    await _send(db, company, "same")
    assert company.onboarding_state == OnboardingState.gst_rate_same
    await _send(db, company, "12")
    assert company.gst_rate == Decimal("12.00")
    assert company.gst_varies_by_product is False
    assert company.onboarding_state == OnboardingState.product_awaiting_mode

    # Product mode: one by one
    await _send(db, company, "one by one")
    assert company.onboarding_state == OnboardingState.product_awaiting_name

    # Products: name -> quantity -> unit -> price -> purchase price, then done
    await _send(db, company, "Paracetamol")
    assert company.onboarding_state == OnboardingState.product_awaiting_quantity
    await _send(db, company, "150")
    assert company.onboarding_state == OnboardingState.product_awaiting_unit
    await _send(db, company, "strips")
    assert company.onboarding_state == OnboardingState.product_awaiting_price
    await _send(db, company, "12")
    assert company.onboarding_state == OnboardingState.product_awaiting_purchase_price
    await _send(db, company, "8")
    assert company.onboarding_state == OnboardingState.product_awaiting_name
    await _send(db, company, "done")
    assert company.onboarding_state == OnboardingState.dealer_awaiting_name
    assert await _count(db, Product, company.id) == 1
    product = await db.scalar(select(Product).where(Product.company_id == company.id))
    assert product.name == "Paracetamol"
    assert product.stock_quantity == Decimal("150")
    assert product.unit == "strips"
    assert product.selling_price == Decimal("12.00")
    assert product.purchase_price == Decimal("8.00")

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
    # Language is chosen up front now (English, via _fresh_company), so a "no"
    # to payables goes straight to the final briefing-hour step — there's no
    # language step at the end of the flow anymore.
    assert company.onboarding_state == OnboardingState.awaiting_briefing_hour
    assert await _count(db, Supplier, company.id) == 1
    assert company.preferred_language == "en"

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
    await _send(db, company, "Kirana")
    await _send(db, company, "not sure")  # decide GST setup later
    await _send(db, company, "done")  # no products
    await _send(db, company, "done")  # no dealers
    await _send(db, company, "done")  # no suppliers
    await _send(db, company, "50000")  # opening cash
    await _send(db, company, "no")  # no receivables
    await _send(db, company, "no")  # no payables (language was chosen up front)
    assert company.preferred_language == "en"
    await _send(db, company, "8")  # briefing hour
    assert company.onboarding_state == OnboardingState.completed
    assert company.briefing_hour == 8
    assert await _count(db, Product, company.id) == 0
    assert await _count(db, Dealer, company.id) == 0
    assert await _count(db, Invoice, company.id) == 0


# ── Language & script picker (asked first, two-step for Hindi/Odia) ───────────


@pytest.mark.asyncio
async def test_language_english_skips_script_step(db: AsyncSession) -> None:
    company = await _bare_company(db)
    reply = await _send(db, company, "hi")  # not_started -> awaiting_language
    assert company.onboarding_state == OnboardingState.awaiting_language
    assert "English" in reply and "Hindi" in reply  # the three-language prompt
    await _send(db, company, "1")  # English
    # English has no script variants, so it jumps straight into business setup.
    assert company.preferred_language == "en"
    assert company.onboarding_state == OnboardingState.awaiting_business_type


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("lang_choice", "script_reply", "expected"),
    [
        ("2", "1", "hi-Latn"),  # Hindi, Romanized (explicit)
        ("2", "", "hi-Latn"),  # Hindi, blank reply -> Romanized default
        ("2", "2", "hi-Deva"),  # Hindi, Native (Devanagari)
        ("3", "1", "or-Latn"),  # Odia, Romanized
        ("3", "2", "or-Orya"),  # Odia, Native (Odia script)
    ],
)
async def test_language_two_step_lands_on_locale(
    db: AsyncSession, lang_choice: str, script_reply: str, expected: str
) -> None:
    company = await _bare_company(db)
    await _send(db, company, "hi")
    await _send(db, company, lang_choice)  # Hindi/Odia -> ask script
    assert company.onboarding_state == OnboardingState.awaiting_script
    await _send(db, company, script_reply)
    assert company.preferred_language == expected
    assert company.onboarding_state == OnboardingState.awaiting_business_type


@pytest.mark.asyncio
async def test_change_language_command_reenters_two_step_flow(db: AsyncSession) -> None:
    """A completed company can switch language: `change language` re-enters the
    same picker and returns to `completed` with the new locale (not back into
    business setup).
    """
    from app.services.onboarding_flow import start_language_change

    company = await _bare_company(db)
    company.onboarding_state = OnboardingState.completed
    await db.flush()

    prompt = start_language_change(company)
    assert company.onboarding_state == OnboardingState.awaiting_language
    assert "Hindi" in prompt

    await _send(db, company, "3")  # Odia -> ask script
    assert company.onboarding_state == OnboardingState.awaiting_script
    await _send(db, company, "1")  # Romanized
    assert company.preferred_language == "or-Latn"
    assert company.onboarding_state == OnboardingState.completed


@pytest.mark.asyncio
async def test_bad_amount_reasks_without_advancing(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    await _send(db, company, "FMCG")
    await _send(db, company, "not sure")  # decide GST setup later
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
async def test_product_quantity_skip_and_bad_input(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    await _send(db, company, "FMCG")
    await _send(db, company, "not sure")  # decide GST setup later
    await _send(db, company, "one by one")

    # Bad quantity re-asks without advancing
    await _send(db, company, "Rice")
    assert company.onboarding_state == OnboardingState.product_awaiting_quantity
    reply = await _send(db, company, "a lot")
    assert company.onboarding_state == OnboardingState.product_awaiting_quantity  # stayed
    assert "number" in reply.lower()

    # Skipping quantity defaults to 0, then unit, then price, then purchase price
    await _send(db, company, "skip")
    assert company.onboarding_state == OnboardingState.product_awaiting_unit
    await _send(db, company, "skip")
    assert company.onboarding_state == OnboardingState.product_awaiting_price
    await _send(db, company, "skip")
    assert company.onboarding_state == OnboardingState.product_awaiting_purchase_price
    await _send(db, company, "skip")
    assert company.onboarding_state == OnboardingState.product_awaiting_name
    product = await db.scalar(select(Product).where(Product.company_id == company.id))
    assert product.name == "Rice"
    assert product.stock_quantity == Decimal("0")
    assert product.unit is None
    assert product.selling_price is None
    assert product.purchase_price is None


@pytest.mark.asyncio
async def test_product_mode_unrecognized_reasks(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    await _send(db, company, "FMCG")
    await _send(db, company, "not sure")  # decide GST setup later
    reply = await _send(db, company, "huh?")
    assert company.onboarding_state == OnboardingState.product_awaiting_mode  # stayed
    assert "bulk" in reply.lower()


@pytest.mark.asyncio
async def test_product_bulk_paste_saves_each_item_separately(db: AsyncSession) -> None:
    """Regression test: pasting a whole product list used to be swallowed
    whole as a single product name. Bulk mode must save each line/item as its
    own Product row.
    """
    company = await _fresh_company(db)
    await _send(db, company, "Cloth store")
    await _send(db, company, "not sure")  # decide GST setup later
    assert company.onboarding_state == OnboardingState.product_awaiting_mode

    await _send(db, company, "bulk")
    assert company.onboarding_state == OnboardingState.product_awaiting_bulk

    reply = await _send(
        db,
        company,
        "T-Shirt, skip, skip, pcs, skip, skip\n"
        "Shirt, skip, skip, pcs, skip, skip\n"
        "Jeans, skip, skip, pcs, skip, skip\n"
        "Kurti, skip, skip, pcs, skip, skip",
    )
    assert company.onboarding_state == OnboardingState.product_awaiting_bulk  # loops for more
    assert "Added 4 product" in reply
    assert await _count(db, Product, company.id) == 4
    products = (
        await db.scalars(select(Product).where(Product.company_id == company.id))
    ).all()
    assert {p.name for p in products} == {"T-Shirt", "Shirt", "Jeans", "Kurti"}
    assert all(p.unit == "pcs" for p in products)

    await _send(db, company, "done")
    assert company.onboarding_state == OnboardingState.dealer_awaiting_name


@pytest.mark.asyncio
async def test_product_bulk_paste_with_prices(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    await _send(db, company, "Kirana")
    await _send(db, company, "not sure")  # decide GST setup later
    await _send(db, company, "bulk")

    await _send(db, company, "rice, 300, 400, kg, skip, skip\ndal, 320, 450, kg, skip, skip")
    assert await _count(db, Product, company.id) == 2
    rice = await db.scalar(
        select(Product).where(Product.company_id == company.id, Product.name == "rice")
    )
    dal = await db.scalar(
        select(Product).where(Product.company_id == company.id, Product.name == "dal")
    )
    assert rice.selling_price == Decimal("400.00")
    assert rice.unit == "kg"
    assert rice.purchase_price == Decimal("300.00")
    assert rice.gst_rate is None
    assert dal.selling_price == Decimal("450.00")
    assert dal.unit == "kg"
    assert dal.purchase_price == Decimal("320.00")

    # A second bulk message keeps adding without resetting the earlier ones.
    await _send(db, company, "Sugar, skip, skip, skip, skip, skip")
    assert await _count(db, Product, company.id) == 3

    await _send(db, company, "done")
    assert company.onboarding_state == OnboardingState.dealer_awaiting_name


@pytest.mark.asyncio
async def test_product_bulk_paste_with_gst(db: AsyncSession) -> None:
    """Each bulk line can set its own GST% (the 6th field), independent of
    the same/varies mode picked earlier."""
    company = await _fresh_company(db)
    await _send(db, company, "Kirana")
    await _send(db, company, "varies")
    await _send(db, company, "bulk")

    await _send(db, company, "Rice, 300, 400, kg, 100, 5\nDal, 320, 450, kg, 50, 12")
    rice = await db.scalar(
        select(Product).where(Product.company_id == company.id, Product.name == "Rice")
    )
    dal = await db.scalar(
        select(Product).where(Product.company_id == company.id, Product.name == "Dal")
    )
    assert rice.gst_rate == Decimal("5.00")
    assert rice.stock_quantity == Decimal("100")
    assert dal.gst_rate == Decimal("12.00")
    assert dal.stock_quantity == Decimal("50")


@pytest.mark.asyncio
async def test_product_bulk_paste_missing_name_reasks(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    await _send(db, company, "Kirana")
    await _send(db, company, "not sure")  # decide GST setup later
    await _send(db, company, "bulk")

    reply = await _send(db, company, ",  , ")
    assert company.onboarding_state == OnboardingState.product_awaiting_bulk  # stayed
    assert "couldn't read" in reply.lower()
    assert await _count(db, Product, company.id) == 0


@pytest.mark.asyncio
async def test_product_bulk_paste_bad_gst_reasks(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    await _send(db, company, "Kirana")
    await _send(db, company, "varies")
    await _send(db, company, "bulk")

    reply = await _send(db, company, "Rice, 300, 400, kg, 100, 150")  # 150% is out of range
    assert company.onboarding_state == OnboardingState.product_awaiting_bulk  # stayed
    assert "couldn't read" in reply.lower()
    assert await _count(db, Product, company.id) == 0


@pytest.mark.asyncio
async def test_gst_mode_ask_invalid_reasks(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    await _send(db, company, "FMCG")
    assert company.onboarding_state == OnboardingState.gst_mode_ask
    reply = await _send(db, company, "huh?")
    assert company.onboarding_state == OnboardingState.gst_mode_ask  # stayed
    assert "same" in reply.lower() and "varies" in reply.lower()


@pytest.mark.asyncio
async def test_gst_mode_not_sure_never_blocks(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    await _send(db, company, "FMCG")
    await _send(db, company, "not sure")
    assert company.onboarding_state == OnboardingState.product_awaiting_mode
    assert company.gst_rate == Decimal("0")
    assert company.gst_varies_by_product is False


@pytest.mark.asyncio
async def test_gst_rate_same_bad_input_reasks(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    await _send(db, company, "FMCG")
    await _send(db, company, "same")
    assert company.onboarding_state == OnboardingState.gst_rate_same
    reply = await _send(db, company, "a lot")
    assert company.onboarding_state == OnboardingState.gst_rate_same  # stayed
    assert "0 and 100" in reply
    reply = await _send(db, company, "150")  # out of range
    assert company.onboarding_state == OnboardingState.gst_rate_same  # stayed
    assert "0 and 100" in reply
    await _send(db, company, "18")
    assert company.gst_rate == Decimal("18.00")
    assert company.onboarding_state == OnboardingState.product_awaiting_mode


@pytest.mark.asyncio
async def test_gst_varies_asks_per_product_rate(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    await _send(db, company, "FMCG")
    await _send(db, company, "varies")
    assert company.gst_varies_by_product is True
    assert company.onboarding_state == OnboardingState.product_awaiting_mode

    await _send(db, company, "one by one")
    await _send(db, company, "Rice")
    await _send(db, company, "100")  # quantity
    await _send(db, company, "kg")  # unit
    await _send(db, company, "400")  # price
    await _send(db, company, "300")  # purchase price
    assert company.onboarding_state == OnboardingState.product_awaiting_gst_rate
    reply = await _send(db, company, "18")
    assert company.onboarding_state == OnboardingState.product_awaiting_name
    assert "Added product" in reply

    product = await db.scalar(select(Product).where(Product.company_id == company.id))
    assert product.gst_rate == Decimal("18.00")


@pytest.mark.asyncio
async def test_gst_varies_per_product_rate_can_be_skipped(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    await _send(db, company, "FMCG")
    await _send(db, company, "varies")
    await _send(db, company, "one by one")
    await _send(db, company, "Rice")
    await _send(db, company, "skip")
    await _send(db, company, "skip")
    await _send(db, company, "skip")
    await _send(db, company, "skip")
    assert company.onboarding_state == OnboardingState.product_awaiting_gst_rate
    await _send(db, company, "skip")

    product = await db.scalar(select(Product).where(Product.company_id == company.id))
    assert product.gst_rate is None


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
