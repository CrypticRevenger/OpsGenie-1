"""Guided WhatsApp onboarding state-machine tests.

Drives app/services/onboarding_flow.handle_onboarding_message directly (the
webhook wiring is covered in test_webhooks_whatsapp.py). Asserts each state
transition and the rows the conversation creates.

    uv run alembic upgrade head
    uv run pytest tests/test_onboarding_flow.py -v
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from app.models.company import Company, OnboardingState
from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceDirection, InvoiceSource, InvoiceStatus
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


async def _to_dealer_mode(db: AsyncSession, company: Company) -> None:
    """Drive a fresh company to dealer_awaiting_mode, skipping GST setup and
    products (neither matters to the dealer/supplier tests below)."""
    await _send(db, company, "FMCG")
    await _send(db, company, "not sure")  # decide GST setup later
    await _send(db, company, "done")  # skip products


async def _to_supplier_mode(db: AsyncSession, company: Company) -> None:
    await _to_dealer_mode(db, company)
    await _send(db, company, "done")  # skip dealers


async def _to_receivable_ask(db: AsyncSession, company: Company) -> None:
    await _to_supplier_mode(db, company)
    await _send(db, company, "done")  # skip suppliers
    await _send(db, company, "50000")  # opening cash


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
    assert company.onboarding_state == OnboardingState.dealer_awaiting_mode
    assert await _count(db, Product, company.id) == 1
    product = await db.scalar(select(Product).where(Product.company_id == company.id))
    assert product.name == "Paracetamol"
    assert product.stock_quantity == Decimal("150")
    assert product.unit == "strips"
    assert product.selling_price == Decimal("12.00")
    assert product.purchase_price == Decimal("8.00")

    # Dealer mode: one by one
    await _send(db, company, "one by one")
    assert company.onboarding_state == OnboardingState.dealer_awaiting_name

    # Dealer: name -> phone -> credit
    await _send(db, company, "Ram Traders")
    assert company.onboarding_state == OnboardingState.dealer_awaiting_phone
    await _send(db, company, "9876543210")
    assert company.onboarding_state == OnboardingState.dealer_awaiting_credit
    await _send(db, company, "15")
    assert company.onboarding_state == OnboardingState.dealer_awaiting_name
    await _send(db, company, "done")
    assert company.onboarding_state == OnboardingState.supplier_awaiting_mode

    dealer = await db.scalar(select(Dealer).where(Dealer.company_id == company.id))
    assert dealer.name == "Ram Traders"
    assert dealer.phone == "9876543210"
    assert dealer.payment_terms_days == 15

    # Supplier mode: one by one
    await _send(db, company, "one by one")
    assert company.onboarding_state == OnboardingState.supplier_awaiting_name

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
    products = (await db.scalars(select(Product).where(Product.company_id == company.id))).all()
    assert {p.name for p in products} == {"T-Shirt", "Shirt", "Jeans", "Kurti"}
    assert all(p.unit == "pcs" for p in products)

    await _send(db, company, "done")
    assert company.onboarding_state == OnboardingState.dealer_awaiting_mode


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
    assert company.onboarding_state == OnboardingState.dealer_awaiting_mode


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
async def test_product_bulk_format_omits_gst_column_when_same(db: AsyncSession) -> None:
    """Regression test: gst_mode_ask "same" (or "not sure") already answers
    GST for every product — the bulk-paste format shown afterward must not
    re-ask for a per-product GST% column, matching the one-by-one flow's own
    skip of the extra GST question in that case.
    """
    company = await _fresh_company(db)
    await _send(db, company, "Kirana")
    await _send(db, company, "same")
    reply = await _send(db, company, "5")  # GST rate
    assert company.onboarding_state == OnboardingState.product_awaiting_mode

    reply = await _send(db, company, "bulk")
    assert company.onboarding_state == OnboardingState.product_awaiting_bulk
    assert "GST%" not in reply
    assert "Name, Purchase Price, Selling Price, Unit, Stock\n" in reply

    # A line without a GST field parses fine and leaves gst_rate unset (falls
    # back to the company default set above at query time, not stored here).
    await _send(db, company, "Rice, 300, 400, kg, 100")
    rice = await db.scalar(
        select(Product).where(Product.company_id == company.id, Product.name == "Rice")
    )
    assert rice.gst_rate is None
    assert rice.stock_quantity == Decimal("100")


@pytest.mark.asyncio
async def test_product_bulk_format_includes_gst_column_when_varies(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    await _send(db, company, "Kirana")
    await _send(db, company, "varies")

    reply = await _send(db, company, "bulk")
    assert "GST%" in reply
    assert "Name, Purchase Price, Selling Price, Unit, Stock, GST%" in reply


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


# ── Dealer/supplier bulk-vs-one-by-one entry (mirrors the product step) ───────


@pytest.mark.asyncio
async def test_dealer_mode_unrecognized_reasks(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    await _to_dealer_mode(db, company)
    reply = await _send(db, company, "huh?")
    assert company.onboarding_state == OnboardingState.dealer_awaiting_mode  # stayed
    assert "bulk" in reply.lower()


@pytest.mark.asyncio
async def test_dealer_bulk_paste_saves_each_item_separately(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    await _to_dealer_mode(db, company)

    await _send(db, company, "bulk")
    assert company.onboarding_state == OnboardingState.dealer_awaiting_bulk

    reply = await _send(
        db,
        company,
        "Ram Traders, 9876543210, 15\nShree Enterprises, 9123456780, 30\nKirana Point, skip, skip",
    )
    assert company.onboarding_state == OnboardingState.dealer_awaiting_bulk  # loops for more
    assert "Added 3 dealer" in reply
    assert await _count(db, Dealer, company.id) == 3

    ram = await db.scalar(
        select(Dealer).where(Dealer.company_id == company.id, Dealer.name == "Ram Traders")
    )
    assert ram.phone == "9876543210"
    assert ram.payment_terms_days == 15
    kirana = await db.scalar(
        select(Dealer).where(Dealer.company_id == company.id, Dealer.name == "Kirana Point")
    )
    assert kirana.phone is None
    assert kirana.payment_terms_days is None

    await _send(db, company, "done")
    assert company.onboarding_state == OnboardingState.supplier_awaiting_mode


@pytest.mark.asyncio
async def test_dealer_bulk_paste_bad_credit_days_reasks(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    await _to_dealer_mode(db, company)
    await _send(db, company, "bulk")

    reply = await _send(db, company, "Ram Traders, 9876543210, lots")
    assert company.onboarding_state == OnboardingState.dealer_awaiting_bulk  # stayed
    assert "couldn't read" in reply.lower()
    assert await _count(db, Dealer, company.id) == 0


@pytest.mark.asyncio
async def test_supplier_mode_unrecognized_reasks(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    await _to_supplier_mode(db, company)
    reply = await _send(db, company, "huh?")
    assert company.onboarding_state == OnboardingState.supplier_awaiting_mode  # stayed
    assert "bulk" in reply.lower()


@pytest.mark.asyncio
async def test_supplier_bulk_paste_saves_each_item_separately(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    await _to_supplier_mode(db, company)

    await _send(db, company, "bulk")
    assert company.onboarding_state == OnboardingState.supplier_awaiting_bulk

    reply = await _send(
        db, company, "Metro Distributors, 9988776655, 30\nSuresh Wholesale, 9871234560, 15"
    )
    assert company.onboarding_state == OnboardingState.supplier_awaiting_bulk  # loops for more
    assert "Added 2 supplier" in reply
    assert await _count(db, Supplier, company.id) == 2

    metro = await db.scalar(
        select(Supplier).where(
            Supplier.company_id == company.id, Supplier.name == "Metro Distributors"
        )
    )
    assert metro.phone == "9988776655"
    assert metro.payment_terms_days == 30

    await _send(db, company, "done")
    assert company.onboarding_state == OnboardingState.awaiting_opening_balance


# ── Receivable/payable new-party confirmation ──────────────────────────────────


@pytest.mark.asyncio
async def test_receivable_unknown_name_asks_confirmation_before_creating(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    await _to_receivable_ask(db, company)
    await _send(db, company, "yes")
    assert company.onboarding_state == OnboardingState.receivable_dealer

    reply = await _send(db, company, "Brand New Traders")
    assert company.onboarding_state == OnboardingState.receivable_new_party_confirm
    assert "Brand New Traders" in reply
    assert await _count(db, Dealer, company.id) == 0  # not created yet

    await _send(db, company, "yes")
    assert company.onboarding_state == OnboardingState.receivable_amount
    await _send(db, company, "42000")
    await _send(db, company, "15 days")
    assert company.onboarding_state == OnboardingState.receivable_ask
    assert await _count(db, Dealer, company.id) == 1
    dealer = await db.scalar(select(Dealer).where(Dealer.company_id == company.id))
    assert dealer.name == "Brand New Traders"


@pytest.mark.asyncio
async def test_receivable_confirmation_no_reasks_for_name(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    await _to_receivable_ask(db, company)
    # Seed a real dealer directly (bypassing onboarding) so the corrected name
    # below has something to match against — seeded only now, after driving
    # past GST setup, so it doesn't trigger the import-confirm detour (which
    # fires when any Dealer/Supplier/Invoice already exists at that
    # checkpoint — see _after_gst).
    db.add(Dealer(company_id=company.id, name="Ram Traders"))
    await db.flush()

    await _send(db, company, "yes")
    await _send(db, company, "Typo Traderz")
    assert company.onboarding_state == OnboardingState.receivable_new_party_confirm

    reply = await _send(db, company, "no")
    assert company.onboarding_state == OnboardingState.receivable_dealer
    assert "which dealer" in reply.lower()
    assert await _count(db, Dealer, company.id) == 1  # only the seeded one

    # Corrected (matching) name resolves straight to the amount question,
    # skipping confirmation.
    await _send(db, company, "Ram Traders")
    assert company.onboarding_state == OnboardingState.receivable_amount


@pytest.mark.asyncio
async def test_receivable_known_dealer_skips_confirmation(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    await _to_dealer_mode(db, company)
    await _send(db, company, "one by one")
    await _send(db, company, "Ram Traders")
    await _send(db, company, "skip")
    await _send(db, company, "skip")
    await _send(db, company, "done")  # dealer_awaiting_mode -> supplier_awaiting_mode
    await _send(db, company, "done")  # skip suppliers
    await _send(db, company, "50000")  # opening cash
    await _send(db, company, "yes")
    reply = await _send(db, company, "Ram Traders")
    assert company.onboarding_state == OnboardingState.receivable_amount
    assert "how much does ram traders owe" in reply.lower()


@pytest.mark.asyncio
async def test_payable_unknown_name_asks_confirmation_before_creating(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    await _to_receivable_ask(db, company)
    await _send(db, company, "no")  # no receivables
    assert company.onboarding_state == OnboardingState.payable_ask
    await _send(db, company, "yes")
    assert company.onboarding_state == OnboardingState.payable_supplier

    reply = await _send(db, company, "Brand New Supplier Co")
    assert company.onboarding_state == OnboardingState.payable_new_party_confirm
    assert "Brand New Supplier Co" in reply
    assert await _count(db, Supplier, company.id) == 0

    await _send(db, company, "yes")
    assert company.onboarding_state == OnboardingState.payable_amount
    await _send(db, company, "82000")
    await _send(db, company, "friday")
    assert company.onboarding_state == OnboardingState.payable_ask
    assert await _count(db, Supplier, company.id) == 1


@pytest.mark.asyncio
async def test_payable_confirmation_no_reasks_for_name(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    await _to_receivable_ask(db, company)
    await _send(db, company, "no")
    await _send(db, company, "yes")
    await _send(db, company, "Typo Supplier")
    assert company.onboarding_state == OnboardingState.payable_new_party_confirm

    reply = await _send(db, company, "no")
    assert company.onboarding_state == OnboardingState.payable_supplier
    assert "which supplier" in reply.lower()
    assert await _count(db, Supplier, company.id) == 0


# ── Resume: progress checklist & restart ─────────────────────────────────────


@pytest.mark.asyncio
async def test_progress_shows_checklist_without_advancing_state(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    await _send(db, company, "Pharma Distributor")
    await _send(db, company, "same")
    await _send(db, company, "12")  # -> product_awaiting_mode (step 2)

    reply = await _send(db, company, "progress")
    # "progress" is a query, not an answer — state must be unchanged.
    assert company.onboarding_state == OnboardingState.product_awaiting_mode
    assert "business type" in reply.lower()
    assert "products" in reply.lower()
    assert "12%" in reply  # 1 of 8 sections done
    assert "restart" in reply.lower()

    # Still mid-flow afterwards — the next real answer is processed normally.
    await _send(db, company, "done")
    assert company.onboarding_state == OnboardingState.dealer_awaiting_mode


@pytest.mark.asyncio
async def test_progress_not_recognized_before_business_setup_starts(db: AsyncSession) -> None:
    company = await _bare_company(db)
    await _send(db, company, "hi")  # not_started -> awaiting_language
    reply = await _send(db, company, "progress")  # swallowed as a language choice
    assert company.onboarding_state == OnboardingState.awaiting_language
    assert "please reply 1" in reply.lower()


@pytest.mark.asyncio
async def test_restart_word_is_not_swallowed_as_data(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    reply = await _send(db, company, "restart")  # would otherwise become business_type
    assert company.onboarding_state == OnboardingState.restart_confirm
    assert company.business_type is None
    assert "yes/no" in reply or "(yes/no)" in reply.lower()


@pytest.mark.asyncio
async def test_restart_no_resumes_exactly_where_left_off(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    await _send(db, company, "Pharma Distributor")
    await _send(db, company, "same")
    await _send(db, company, "12")
    await _send(db, company, "one by one")
    await _send(db, company, "Paracetamol")  # mid product entry, scratch has "name"
    assert company.onboarding_state == OnboardingState.product_awaiting_quantity

    await _send(db, company, "restart")
    assert company.onboarding_state == OnboardingState.restart_confirm
    reply = await _send(db, company, "no")
    assert company.onboarding_state == OnboardingState.product_awaiting_quantity
    assert "continuing" in reply.lower()

    # The in-progress product's scratch survived the detour — answering the
    # quantity question still finishes that same product, not a new one.
    await _send(db, company, "100")
    assert company.onboarding_state == OnboardingState.product_awaiting_unit
    await _send(db, company, "kg")
    await _send(db, company, "skip")
    await _send(db, company, "skip")
    assert await _count(db, Product, company.id) == 1
    product = await db.scalar(select(Product).where(Product.company_id == company.id))
    assert product.name == "Paracetamol"
    # Nothing was wiped — company-level fields from before the detour stand.
    assert company.business_type == "Pharma Distributor"
    assert company.gst_rate == Decimal("12.00")


@pytest.mark.asyncio
async def test_restart_yes_wipes_everything_and_starts_over(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    await _send(db, company, "Pharma Distributor")
    await _send(db, company, "same")
    await _send(db, company, "12")
    await _send(db, company, "one by one")
    await _send(db, company, "Paracetamol")
    await _send(db, company, "100")
    await _send(db, company, "kg")
    await _send(db, company, "12")
    await _send(db, company, "8")
    await _send(db, company, "done")  # -> dealer_awaiting_mode
    await _send(db, company, "one by one")
    await _send(db, company, "Ram Traders")
    await _send(db, company, "skip")
    await _send(db, company, "15")  # dealer created
    assert await _count(db, Product, company.id) == 1
    assert await _count(db, Dealer, company.id) == 1

    await _send(db, company, "restart")
    assert company.onboarding_state == OnboardingState.restart_confirm
    reply = await _send(db, company, "yes")

    assert company.onboarding_state == OnboardingState.awaiting_business_type
    assert company.onboarding_scratch is None
    assert company.business_type is None
    assert company.gst_rate == Decimal("0")
    assert company.gst_varies_by_product is False
    assert await _count(db, Product, company.id) == 0
    assert await _count(db, Dealer, company.id) == 0
    assert "what kind of business" in reply.lower()

    # A full onboarding attempt can now run again from a clean slate.
    await _send(db, company, "FMCG Distributor")
    assert company.business_type == "FMCG Distributor"
    assert company.onboarding_state == OnboardingState.gst_mode_ask


@pytest.mark.asyncio
async def test_restart_yes_removes_opening_receivable_invoice(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    await _to_receivable_ask(db, company)
    await _send(db, company, "yes")
    await _send(db, company, "New Dealer Co")
    await _send(db, company, "yes")  # confirm creating the new dealer
    await _send(db, company, "42000")
    await _send(db, company, "friday")
    assert await _count(db, Invoice, company.id) == 1
    assert await _count(db, Dealer, company.id) == 1

    await _send(db, company, "restart")
    await _send(db, company, "yes")
    assert await _count(db, Invoice, company.id) == 0
    assert await _count(db, Dealer, company.id) == 0
    assert company.opening_balance == Decimal("0")


# ── Import confirm: skip already-imported sections ───────────────────────────
# Simulates a company seeded via the website's "seed from an existing export"
# step (POST /onboard/{id}/import, tested end-to-end in
# test_onboarding_import.py) — that endpoint runs entirely before WhatsApp
# ever starts, so from this state machine's point of view a seeded company
# just already has Product/Dealer/Supplier/Invoice rows in place before GST
# setup finishes (the first point _after_gst can see all of them at once).


async def _seed_product(db: AsyncSession, company: Company, *, complete: bool = False) -> None:
    """`complete=False` (the default) matches real import behavior — a
    products file with no GST% column leaves gst_rate NULL, same as
    app/services/importer/product_row.py does. Pass complete=True for tests
    whose actual purpose is the section skip-chain, not the missing-GST
    backfill feature — matches _seed_invoice's own complete= convention."""
    gst_rate = Decimal("5.00") if complete else None
    db.add(
        Product(
            company_id=company.id, name=f"Seed Product {uuid.uuid4().hex[:6]}", gst_rate=gst_rate
        )
    )
    await db.flush()


async def _seed_invoice(
    db: AsyncSession, company: Company, direction: InvoiceDirection, *, complete: bool = False
) -> None:
    """`complete=False` (the default) matches real import behavior —
    find_or_create_party (app/services/importer/parties.py) only ever sets
    `name`, leaving phone/payment_terms_days NULL. Pass complete=True for
    tests whose actual purpose is the section skip-chain, not the
    missing-field backfill feature this default shape now triggers."""
    phone = "+919876543210" if complete else None
    credit_days = 15 if complete else None
    if direction == InvoiceDirection.receivable:
        party = Dealer(
            company_id=company.id,
            name=f"Seed Dealer {uuid.uuid4().hex[:6]}",
            phone=phone,
            payment_terms_days=credit_days,
        )
    else:
        party = Supplier(
            company_id=company.id,
            name=f"Seed Supplier {uuid.uuid4().hex[:6]}",
            phone=phone,
            payment_terms_days=credit_days,
        )
    db.add(party)
    await db.flush()
    db.add(
        Invoice(
            company_id=company.id,
            invoice_number=f"SEED-{uuid.uuid4().hex[:10]}",
            direction=direction,
            dealer_id=party.id if direction == InvoiceDirection.receivable else None,
            supplier_id=party.id if direction == InvoiceDirection.payable else None,
            invoice_date=date(2026, 1, 1),
            due_date=date(2026, 2, 1),
            subtotal=Decimal("1000.00"),
            gst_amount=Decimal("0.00"),
            total_amount=Decimal("1000.00"),
            status=InvoiceStatus.Pending,
            source=InvoiceSource.csv_import,
        )
    )
    await db.flush()


async def _to_gst_done(db: AsyncSession, company: Company) -> str:
    await _send(db, company, "FMCG")
    return await _send(db, company, "not sure")  # decide GST setup later


@pytest.mark.asyncio
async def test_no_import_confirm_when_nothing_imported(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    reply = await _to_gst_done(db, company)
    assert company.onboarding_state == OnboardingState.product_awaiting_mode
    assert "found" not in reply.lower()


@pytest.mark.asyncio
async def test_import_confirm_shown_with_everything_imported(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    await _seed_product(db, company)
    await _seed_invoice(db, company, InvoiceDirection.receivable)
    await _seed_invoice(db, company, InvoiceDirection.payable)

    reply = await _to_gst_done(db, company)
    assert company.onboarding_state == OnboardingState.import_confirm
    assert "1 product" in reply.lower()
    assert "1 dealer" in reply.lower()
    assert "1 supplier" in reply.lower()
    assert "1 outstanding receivable" in reply.lower()
    assert "1 outstanding payable" in reply.lower()
    assert "(yes/no)" in reply.lower()


@pytest.mark.asyncio
async def test_import_confirm_yes_skips_everything_to_opening_balance(db: AsyncSession) -> None:
    # This test is about the section skip-chain itself, not the missing-field
    # backfill feature — complete=True keeps every seeded row fully filled so
    # "yes" really does skip straight through, same as it always did.
    company = await _fresh_company(db)
    await _seed_product(db, company, complete=True)
    await _seed_invoice(db, company, InvoiceDirection.receivable, complete=True)
    await _seed_invoice(db, company, InvoiceDirection.payable, complete=True)
    await _to_gst_done(db, company)
    assert company.onboarding_state == OnboardingState.import_confirm

    reply = await _send(db, company, "yes")
    assert company.onboarding_state == OnboardingState.awaiting_opening_balance
    assert "how much cash" in reply.lower()
    # Nothing was re-asked or re-created.
    assert await _count(db, Product, company.id) == 1
    assert await _count(db, Dealer, company.id) == 1
    assert await _count(db, Supplier, company.id) == 1


@pytest.mark.asyncio
async def test_import_confirm_no_still_skips_but_shows_correction_hint(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    await _seed_product(db, company)
    await _to_gst_done(db, company)

    reply = await _send(db, company, "no")
    # "no" still skips ahead (re-collecting risks duplicate rows) — it just
    # points at the existing correction commands instead of re-asking. Only
    # products were imported, so dealers still get asked normally next.
    assert company.onboarding_state == OnboardingState.dealer_awaiting_mode
    assert "edit dealer" in reply.lower()


@pytest.mark.asyncio
async def test_import_confirm_invalid_reply_reasks(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    await _seed_product(db, company)
    await _to_gst_done(db, company)
    assert company.onboarding_state == OnboardingState.import_confirm

    reply = await _send(db, company, "maybe")
    assert company.onboarding_state == OnboardingState.import_confirm
    assert "yes or no" in reply.lower()


@pytest.mark.asyncio
async def test_import_confirm_partial_products_only_still_asks_dealers(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    await _seed_product(db, company)

    reply = await _to_gst_done(db, company)
    assert company.onboarding_state == OnboardingState.import_confirm
    assert "product" in reply.lower()
    assert "dealer" not in reply.lower()
    assert "supplier" not in reply.lower()

    reply = await _send(db, company, "yes")
    assert company.onboarding_state == OnboardingState.dealer_awaiting_mode
    assert await _count(db, Product, company.id) == 1  # not duplicated


@pytest.mark.asyncio
async def test_import_confirm_partial_receivables_skips_dealers_asks_rest(db: AsyncSession) -> None:
    # A sales-register-only import creates a Dealer + a receivable Invoice
    # together, but no products/suppliers/payables — the chain should skip
    # exactly the dealer section and ask normally for everything else. This
    # test is about that skip-chain, not the missing-field backfill feature —
    # complete=True keeps the seeded dealer fully filled so the section is
    # really skipped, not routed into the new dealer_missing_ask flow.
    company = await _fresh_company(db)
    await _seed_invoice(db, company, InvoiceDirection.receivable, complete=True)
    await _to_gst_done(db, company)
    await _send(db, company, "yes")
    assert company.onboarding_state == OnboardingState.product_awaiting_mode

    await _send(db, company, "done")  # skip products (not imported)
    assert company.onboarding_state == OnboardingState.supplier_awaiting_mode  # dealers skipped
    await _send(db, company, "done")  # skip suppliers (not imported)
    assert company.onboarding_state == OnboardingState.awaiting_opening_balance

    await _send(db, company, "50000")
    assert company.onboarding_state == OnboardingState.payable_ask  # receivables skipped
    assert await _count(db, Dealer, company.id) == 1  # not duplicated


# ── GST: only ask about imported products missing a rate ────────────────────


@pytest.mark.asyncio
async def test_gst_all_imported_products_have_rate_skips_question(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    db.add(Product(company_id=company.id, name="Rice", gst_rate=Decimal("5.00")))
    db.add(Product(company_id=company.id, name="Dal", gst_rate=Decimal("12.00")))
    await db.flush()

    reply = await _send(db, company, "FMCG")
    # Straight to import_confirm — the GST question never appeared at all.
    assert company.onboarding_state == OnboardingState.import_confirm
    assert "gst" not in reply.lower()
    assert company.gst_varies_by_product is True


@pytest.mark.asyncio
async def test_gst_some_imported_products_missing_rate_asks_only_for_those(
    db: AsyncSession,
) -> None:
    company = await _fresh_company(db)
    db.add(Product(company_id=company.id, name="Rice", gst_rate=Decimal("5.00")))
    db.add(Product(company_id=company.id, name="Dal", gst_rate=None))
    db.add(Product(company_id=company.id, name="Oil", gst_rate=None))
    await db.flush()

    reply = await _send(db, company, "FMCG")
    assert company.onboarding_state == OnboardingState.gst_missing_rate_ask
    assert "dal" in reply.lower()
    assert "oil" in reply.lower()
    assert "rice" not in reply.lower()  # already has a rate — not named

    await _send(db, company, "18")
    assert company.onboarding_state == OnboardingState.import_confirm

    products = (
        (await db.execute(select(Product).where(Product.company_id == company.id))).scalars().all()
    )
    by_name = {p.name: p.gst_rate for p in products}
    assert by_name["Rice"] == Decimal("5.00")  # untouched
    assert by_name["Dal"] == Decimal("18.00")
    assert by_name["Oil"] == Decimal("18.00")


@pytest.mark.asyncio
async def test_gst_missing_rate_can_be_skipped(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    db.add(Product(company_id=company.id, name="Dal", gst_rate=None))
    await db.flush()

    await _send(db, company, "FMCG")
    assert company.onboarding_state == OnboardingState.gst_missing_rate_ask
    await _send(db, company, "skip")
    assert company.onboarding_state == OnboardingState.import_confirm

    product = await db.scalar(select(Product).where(Product.company_id == company.id))
    assert product.gst_rate is None


# ── Dealer/supplier missing-field backfill (import path only) ───────────────


async def _company_with_incomplete_dealer(db: AsyncSession) -> Company:
    """A company just past import_confirm's "yes", with one dealer imported
    with no phone/credit days — lands on dealer_missing_ask."""
    company = await _fresh_company(db)
    await _seed_product(db, company, complete=True)  # skips the GST question
    await _seed_invoice(db, company, InvoiceDirection.receivable)  # incomplete dealer
    await _send(db, company, "FMCG")
    assert company.onboarding_state == OnboardingState.import_confirm
    await _send(db, company, "yes")
    assert company.onboarding_state == OnboardingState.dealer_missing_ask
    return company


async def _company_with_incomplete_supplier(db: AsyncSession) -> Company:
    """Same shape, but the dealer section is already complete (auto-skips)
    and it's the supplier that's missing phone/credit days — lands on
    supplier_missing_ask."""
    company = await _fresh_company(db)
    await _seed_product(db, company, complete=True)
    await _seed_invoice(db, company, InvoiceDirection.receivable, complete=True)
    await _seed_invoice(db, company, InvoiceDirection.payable)  # incomplete supplier
    await _send(db, company, "FMCG")
    assert company.onboarding_state == OnboardingState.import_confirm
    await _send(db, company, "yes")
    assert company.onboarding_state == OnboardingState.supplier_missing_ask
    return company


@pytest.mark.asyncio
async def test_dealer_missing_ask_later_leaves_rows_unchanged(db: AsyncSession) -> None:
    company = await _company_with_incomplete_dealer(db)

    await _send(db, company, "later")
    assert company.onboarding_state == OnboardingState.supplier_awaiting_mode  # chain continues
    dealer = await db.scalar(select(Dealer).where(Dealer.company_id == company.id))
    assert dealer.phone is None
    assert dealer.payment_terms_days is None


@pytest.mark.asyncio
async def test_dealer_missing_now_shows_list_and_asks_mode(db: AsyncSession) -> None:
    company = await _company_with_incomplete_dealer(db)

    reply = await _send(db, company, "now")
    assert company.onboarding_state == OnboardingState.dealer_missing_mode
    assert "1." in reply
    assert "bulk" in reply.lower()
    assert "one by one" in reply.lower()


@pytest.mark.asyncio
async def test_dealer_missing_one_by_one_updates_existing_row(db: AsyncSession) -> None:
    company = await _company_with_incomplete_dealer(db)
    await _send(db, company, "now")
    await _send(db, company, "one by one")
    assert company.onboarding_state == OnboardingState.dealer_missing_phone

    await _send(db, company, "9876543210")
    assert company.onboarding_state == OnboardingState.dealer_missing_credit
    await _send(db, company, "15")
    # Only one dealer was missing — the queue's now empty, so the chain moves on.
    assert company.onboarding_state == OnboardingState.supplier_awaiting_mode

    assert await _count(db, Dealer, company.id) == 1  # not duplicated
    dealer = await db.scalar(select(Dealer).where(Dealer.company_id == company.id))
    assert dealer.phone == "9876543210"
    assert dealer.payment_terms_days == 15


@pytest.mark.asyncio
async def test_dealer_missing_bulk_updates_matched_and_reports_unmatched(
    db: AsyncSession,
) -> None:
    company = await _fresh_company(db)
    await _seed_product(db, company, complete=True)
    db.add(Dealer(company_id=company.id, name="Ram Traders"))
    db.add(Dealer(company_id=company.id, name="Shree Enterprises"))
    await db.flush()
    await _send(db, company, "FMCG")
    assert company.onboarding_state == OnboardingState.import_confirm
    await _send(db, company, "yes")
    assert company.onboarding_state == OnboardingState.dealer_missing_ask

    await _send(db, company, "now")
    await _send(db, company, "bulk")
    assert company.onboarding_state == OnboardingState.dealer_missing_bulk

    reply = await _send(db, company, "Ram Traders, 9876543210, 15\nUnknown Dealer, 9000000000, 10")
    assert company.onboarding_state == OnboardingState.supplier_awaiting_mode  # chain continued
    assert "unknown dealer" in reply.lower()  # reported back as unmatched

    dealers = (
        (await db.execute(select(Dealer).where(Dealer.company_id == company.id))).scalars().all()
    )
    assert len(dealers) == 2  # no duplicate row created for "Unknown Dealer"
    by_name = {d.name: d for d in dealers}
    assert by_name["Ram Traders"].phone == "9876543210"
    assert by_name["Ram Traders"].payment_terms_days == 15
    assert by_name["Shree Enterprises"].phone is None  # untouched — not in the pasted lines


@pytest.mark.asyncio
async def test_supplier_missing_ask_later_leaves_rows_unchanged(db: AsyncSession) -> None:
    company = await _company_with_incomplete_supplier(db)

    await _send(db, company, "later")
    assert company.onboarding_state == OnboardingState.awaiting_opening_balance  # chain continues
    supplier = await db.scalar(select(Supplier).where(Supplier.company_id == company.id))
    assert supplier.phone is None
    assert supplier.payment_terms_days is None


@pytest.mark.asyncio
async def test_supplier_missing_one_by_one_updates_existing_row(db: AsyncSession) -> None:
    company = await _company_with_incomplete_supplier(db)
    await _send(db, company, "now")
    await _send(db, company, "one by one")
    assert company.onboarding_state == OnboardingState.supplier_missing_phone

    await _send(db, company, "9988776655")
    assert company.onboarding_state == OnboardingState.supplier_missing_credit
    await _send(db, company, "30")
    assert company.onboarding_state == OnboardingState.awaiting_opening_balance

    assert await _count(db, Supplier, company.id) == 1  # not duplicated
    supplier = await db.scalar(select(Supplier).where(Supplier.company_id == company.id))
    assert supplier.phone == "9988776655"
    assert supplier.payment_terms_days == 30


@pytest.mark.asyncio
async def test_supplier_missing_bulk_updates_matched_row(db: AsyncSession) -> None:
    company = await _company_with_incomplete_supplier(db)
    await _send(db, company, "now")
    await _send(db, company, "bulk")
    assert company.onboarding_state == OnboardingState.supplier_missing_bulk

    supplier_before = await db.scalar(select(Supplier).where(Supplier.company_id == company.id))
    reply = await _send(db, company, f"{supplier_before.name}, 9988776655, 30")
    assert company.onboarding_state == OnboardingState.awaiting_opening_balance
    assert supplier_before.name.lower() in reply.lower()  # named in the "updated" confirmation

    supplier = await db.get(Supplier, supplier_before.id)
    assert supplier.phone == "9988776655"
    assert supplier.payment_terms_days == 30
