"""Admin follow-up trigger endpoint tests — Phase 9.

uv run alembic upgrade head
uv run pytest tests/test_admin_followup.py -v
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceDirection, InvoiceSource, InvoiceStatus
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


def _unique_phone() -> str:
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


async def _create_company(client: AsyncClient) -> str:
    resp = await client.post(
        "/admin/companies",
        json={
            "business_name": "Followup Endpoint Test Co",
            "owner_name": "Owner",
            "whatsapp_number": _unique_phone(),
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_send_due_today_sends_when_invoice_due(client: AsyncClient, db: AsyncSession) -> None:
    company_id = await _create_company(client)
    dealer = Dealer(company_id=uuid.UUID(company_id), name="Ram Traders")
    db.add(dealer)
    await db.commit()
    await db.refresh(dealer)

    invoice = Invoice(
        company_id=uuid.UUID(company_id),
        invoice_number=f"INV-{uuid.uuid4().hex[:8]}",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer.id,
        invoice_date=date.today() - timedelta(days=30),
        due_date=date.today(),
        subtotal=Decimal("49350.00"),
        gst_amount=Decimal("0.00"),
        total_amount=Decimal("49350.00"),
        status=InvoiceStatus.Pending,
        source=InvoiceSource.csv_import,
    )
    db.add(invoice)
    await db.commit()

    resp = await client.post(f"/admin/companies/{company_id}/follow-ups/send-due-today")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "sent"
    assert data["invoice_number"] == invoice.invoice_number


@pytest.mark.asyncio
async def test_send_due_today_none_due(client: AsyncClient) -> None:
    company_id = await _create_company(client)
    resp = await client.post(f"/admin/companies/{company_id}/follow-ups/send-due-today")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "none_due"
    assert data["invoice_number"] is None


@pytest.mark.asyncio
async def test_send_due_today_unknown_company_404(client: AsyncClient) -> None:
    resp = await client.post(f"/admin/companies/{uuid.uuid4()}/follow-ups/send-due-today")
    assert resp.status_code == 404
