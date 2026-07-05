"""Agent read-tool tests — each tool returns correct real numbers from the DB.

uv run alembic upgrade head
uv run pytest tests/test_agent_tools.py -v
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from app.models.company import Company, OnboardingState
from app.models.dealer import Dealer
from app.models.faq import FAQ
from app.models.invoice import Invoice, InvoiceDirection, InvoiceSource, InvoiceStatus
from app.models.product import Product
from app.services.agent.base import ToolContext
from app.services.agent.read_tools import READ_TOOLS
from sqlalchemy.ext.asyncio import AsyncSession

_TOOLS = {t.name: t for t in READ_TOOLS}


def _unique_number() -> str:
    return f"+919{uuid.uuid4().int % 1_000_000_000:09d}"


async def _seed(db: AsyncSession) -> Company:
    company = Company(
        business_name="Tool Co",
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
    db.add(
        Product(
            company_id=company.id,
            name="Rice",
            unit="kg",
            selling_price=Decimal("55.00"),
            stock_quantity=Decimal("120"),
        )
    )
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
            subtotal=Decimal("42000.00"),
            gst_amount=Decimal("0.00"),
            total_amount=Decimal("42000.00"),
            status=InvoiceStatus.Pending,
            source=InvoiceSource.csv_import,
        )
    )
    await db.commit()
    return company


async def _seed_company(db: AsyncSession, *, dealer_name: str, amount: str) -> Company:
    company = Company(
        business_name=f"Co {amount}",
        owner_name="Owner",
        whatsapp_number=_unique_number(),
        subscription_active=True,
        onboarding_state=OnboardingState.completed,
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    dealer = Dealer(company_id=company.id, name=dealer_name)
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


async def _call(db, company, tool_name, **args) -> dict:
    ctx = ToolContext(db=db, company=company, tools=_TOOLS)
    return await ctx.execute(tool_name, args)


@pytest.mark.asyncio
async def test_get_party_balance_matches_partial_name(db: AsyncSession) -> None:
    company = await _seed(db)
    out = await _call(db, company, "get_party_balance", name="ram")
    assert out["party"] == "Ram Traders"
    assert out["relationship"] == "dealer_owes_you"
    assert Decimal(out["outstanding"]) == Decimal("42000.00")


@pytest.mark.asyncio
async def test_get_party_balance_unknown(db: AsyncSession) -> None:
    company = await _seed(db)
    out = await _call(db, company, "get_party_balance", name="nobody")
    assert "error" in out


@pytest.mark.asyncio
async def test_list_top_debtors(db: AsyncSession) -> None:
    company = await _seed(db)
    out = await _call(db, company, "list_top_debtors")
    names = [d["name"] for d in out["dealers_who_owe_you"]]
    assert "Ram Traders" in names
    ram = next(d for d in out["dealers_who_owe_you"] if d["name"] == "Ram Traders")
    assert Decimal(ram["outstanding"]) == Decimal("42000.00")


@pytest.mark.asyncio
async def test_get_inventory(db: AsyncSession) -> None:
    company = await _seed(db)
    out = await _call(db, company, "get_inventory")
    rice = next(p for p in out["inventory"] if p["name"] == "Rice")
    assert rice["unit"] == "kg"
    assert Decimal(rice["selling_price"]) == Decimal("55.00")
    assert Decimal(rice["stock_quantity"]) == Decimal("120")


@pytest.mark.asyncio
async def test_get_faqs(db: AsyncSession) -> None:
    company = await _seed(db)
    db.add(FAQ(company_id=company.id, question="Delivery days?", answer="Mon-Sat"))
    await db.commit()
    out = await _call(db, company, "get_faqs")
    assert out["faqs"] == [{"question": "Delivery days?", "answer": "Mon-Sat"}]


@pytest.mark.asyncio
async def test_business_summary_shape(db: AsyncSession) -> None:
    company = await _seed(db)
    out = await _call(db, company, "get_business_summary")
    assert "cash_available_now" in out
    assert "net_cash_position" in out
    assert "overdue_dealers" in out


@pytest.mark.asyncio
async def test_unknown_tool_returns_error(db: AsyncSession) -> None:
    company = await _seed(db)
    out = await _call(db, company, "does_not_exist")
    assert "error" in out


@pytest.mark.asyncio
async def test_context_records_outputs(db: AsyncSession) -> None:
    company = await _seed(db)
    ctx = ToolContext(db=db, company=company, tools=_TOOLS)
    await ctx.execute("get_party_balance", {"name": "ram"})
    await ctx.execute("get_inventory", {})
    assert len(ctx.outputs) == 2  # every execution is recorded for the money gate


# ── Per-distributor data isolation (the critical property) ────────────────────


@pytest.mark.asyncio
async def test_two_distributors_are_isolated(db: AsyncSession) -> None:
    # Both have a dealer literally named "Ram Traders", but different balances.
    a = await _seed_company(db, dealer_name="Ram Traders", amount="42000.00")
    b = await _seed_company(db, dealer_name="Ram Traders", amount="99999.00")

    # Each company's tools return ONLY that company's number — never the other's.
    bal_a = await _call(db, a, "get_party_balance", name="ram")
    bal_b = await _call(db, b, "get_party_balance", name="ram")
    assert Decimal(bal_a["outstanding"]) == Decimal("42000.00")
    assert Decimal(bal_b["outstanding"]) == Decimal("99999.00")

    # A's dealer/debtor lists must not contain B's figure, and vice-versa.
    dealers_a = (await _call(db, a, "list_dealers"))["dealers"]
    assert all(Decimal(d["outstanding"]) != Decimal("99999.00") for d in dealers_a)

    top_a = (await _call(db, a, "list_top_debtors"))["dealers_who_owe_you"]
    assert [Decimal(d["outstanding"]) for d in top_a] == [Decimal("42000.00")]
    top_b = (await _call(db, b, "list_top_debtors"))["dealers_who_owe_you"]
    assert [Decimal(d["outstanding"]) for d in top_b] == [Decimal("99999.00")]

    # A's recent invoices are only A's; B's total never appears for A.
    inv_a = (await _call(db, a, "list_recent_invoices"))["invoices"]
    assert all(Decimal(i["total"]) != Decimal("99999.00") for i in inv_a)
    assert any(Decimal(i["total"]) == Decimal("42000.00") for i in inv_a)


@pytest.mark.asyncio
async def test_list_dealers_scoped_and_shaped(db: AsyncSession) -> None:
    company = await _seed(db)
    out = await _call(db, company, "list_dealers")
    assert len(out["dealers"]) == 1
    assert out["dealers"][0]["name"] == "Ram Traders"
    assert Decimal(out["dealers"][0]["outstanding"]) == Decimal("42000.00")
