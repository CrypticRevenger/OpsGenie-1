"""Admin cashflow endpoint tests — Phase 5A.

Requires postgres running with migrations applied:

    uv run alembic upgrade head
    uv run pytest tests/test_admin_cashflow.py -v
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from app.models.company import Company
from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceDirection, InvoiceSource, InvoiceStatus
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


def _unique_phone() -> str:
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


async def _make_company(db: AsyncSession) -> uuid.UUID:
    company = Company(
        business_name="Cashflow API Test Co",
        owner_name="Owner",
        whatsapp_number=_unique_phone(),
        opening_balance=Decimal("50000.00"),
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company.id


async def _make_dealer(
    db: AsyncSession, company_id: uuid.UUID, name: str, credit_limit=None
) -> uuid.UUID:
    dealer = Dealer(company_id=company_id, name=name, credit_limit=credit_limit)
    db.add(dealer)
    await db.commit()
    await db.refresh(dealer)
    return dealer.id


@pytest.mark.asyncio
async def test_cashflow_endpoint_returns_snapshot_and_recommendations(
    client: AsyncClient, db: AsyncSession
) -> None:
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id, "Overdue Dealer", credit_limit=Decimal("100.00"))

    invoice = Invoice(
        company_id=company_id,
        invoice_number="INV-CF-1",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        invoice_date=date.today() - timedelta(days=40),
        due_date=date.today() - timedelta(days=25),
        subtotal=Decimal("20000.00"),
        gst_amount=Decimal("0.00"),
        total_amount=Decimal("20000.00"),
        status=InvoiceStatus.Pending,
        source=InvoiceSource.csv_import,
    )
    db.add(invoice)
    await db.commit()

    resp = await client.get(f"/admin/companies/{company_id}/cashflow")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["cash_available_today"] == "50000.00"
    assert data["data_completeness_score"] is None
    overdue_names = {d["dealer_name"] for d in data["overdue_dealers"]}
    assert "Overdue Dealer" in overdue_names
    action_types = {a["action_type"] for a in data["recommendations"]}
    assert "call_dealer" in action_types  # 25 days overdue, outstanding > credit_limit


@pytest.mark.asyncio
async def test_cashflow_company_not_found(client: AsyncClient) -> None:
    resp = await client.get(f"/admin/companies/{uuid.uuid4()}/cashflow")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cashflow_empty_company_no_recommendations_except_stale_data(
    client: AsyncClient, db: AsyncSession
) -> None:
    company_id = await _make_company(db)
    resp = await client.get(f"/admin/companies/{company_id}/cashflow")
    assert resp.status_code == 200
    data = resp.json()
    assert data["overdue_dealers"] == []
    action_types = [a["action_type"] for a in data["recommendations"]]
    assert action_types == ["stale_data_warning"]  # no import ever happened
