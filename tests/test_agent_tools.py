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
    db.add(Product(company_id=company.id, name="Rice"))
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
async def test_list_products(db: AsyncSession) -> None:
    company = await _seed(db)
    out = await _call(db, company, "list_products")
    assert "Rice" in out["products"]


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
    await ctx.execute("list_products", {})
    assert len(ctx.outputs) == 2  # every execution is recorded for the money gate
