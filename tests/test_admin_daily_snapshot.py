"""Admin Daily Business Summary endpoint tests.

Requires postgres running with migrations applied:

    uv run alembic upgrade head
    uv run pytest tests/test_admin_daily_snapshot.py -v
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from app.models.company import Company
from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceDirection, InvoiceSource, InvoiceStatus
from app.models.invoice_item import InvoiceItem
from app.models.product import Product
from app.services.whatsapp_client import WhatsAppSendResult
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


def _unique_phone() -> str:
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


async def _make_company(db: AsyncSession) -> uuid.UUID:
    company = Company(
        business_name="Daily Snapshot API Test Co",
        owner_name="Owner",
        whatsapp_number=_unique_phone(),
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company.id


async def _make_sale_today(db: AsyncSession, company_id: uuid.UUID) -> None:
    dealer = Dealer(company_id=company_id, name="Ram Traders")
    db.add(dealer)
    await db.flush()
    product = Product(
        company_id=company_id,
        name="Rice",
        selling_price=Decimal("100.00"),
        purchase_price=Decimal("70.00"),
    )
    db.add(product)
    await db.flush()
    today = date.today()
    invoice = Invoice(
        company_id=company_id,
        invoice_number=f"WA-{uuid.uuid4().hex[:10]}",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer.id,
        invoice_date=today,
        due_date=today,
        subtotal=Decimal("1000.00"),
        gst_amount=Decimal("0.00"),
        total_amount=Decimal("1000.00"),
        status=InvoiceStatus.Pending,
        source=InvoiceSource.whatsapp,
    )
    db.add(invoice)
    await db.flush()
    db.add(
        InvoiceItem(
            invoice_id=invoice.id,
            product_id=product.id,
            description="Rice",
            quantity=Decimal("10"),
            unit_price=Decimal("100.00"),
            line_total=Decimal("1000.00"),
        )
    )
    await db.commit()


@pytest.mark.asyncio
async def test_today_snapshot_reflects_real_sale(client: AsyncClient, db: AsyncSession) -> None:
    company_id = await _make_company(db)
    await _make_sale_today(db, company_id)

    resp = await client.get(f"/admin/companies/{company_id}/daily-snapshot/today")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["sales_amount"] == "1000.00"
    assert data["sales_margin"] == "300.00"
    assert data["orders_created"] == 1


@pytest.mark.asyncio
async def test_today_snapshot_company_not_found(client: AsyncClient) -> None:
    resp = await client.get(f"/admin/companies/{uuid.uuid4()}/daily-snapshot/today")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_month_summary_includes_live_today(client: AsyncClient, db: AsyncSession) -> None:
    company_id = await _make_company(db)
    await _make_sale_today(db, company_id)
    today = date.today()

    resp = await client.get(
        f"/admin/companies/{company_id}/daily-snapshot/month-summary",
        params={"year": today.year, "month": today.month},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["totals"]["sales_amount"] == "1000.00"
    assert data["days"] == []  # nothing finalized yet


@pytest.mark.asyncio
async def test_evening_brief_manual_send_finalizes_and_appears_in_month_summary(
    client: AsyncClient, db: AsyncSession, monkeypatch
) -> None:
    async def _fake_send(to: str, body: str) -> WhatsAppSendResult:
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.services.evening_brief.send_text_message", _fake_send)

    company_id = await _make_company(db)
    await _make_sale_today(db, company_id)

    send_resp = await client.post(f"/admin/companies/{company_id}/evening-brief/send")
    assert send_resp.status_code == 200, send_resp.text
    assert send_resp.json()["sent"] is True

    today = date.today()
    summary_resp = await client.get(
        f"/admin/companies/{company_id}/daily-snapshot/month-summary",
        params={"year": today.year, "month": today.month},
    )
    data = summary_resp.json()
    assert len(data["days"]) == 1
    assert data["days"][0]["sales_amount"] == "1000.00"
