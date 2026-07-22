"""Admin dealer endpoint tests — dashboard-driven full CRUD.

    uv run alembic upgrade head
    uv run pytest tests/test_admin_dealers.py -v
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from app.models.invoice import Invoice, InvoiceDirection, InvoiceSource, InvoiceStatus
from app.models.payment import Payment
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _unique_phone() -> str:
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


async def _create_company(client: AsyncClient) -> str:
    resp = await client.post(
        "/admin/companies",
        json={
            "business_name": "Dealer Test Co",
            "owner_name": "Owner",
            "whatsapp_number": _unique_phone(),
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _make_invoice_with_payment(
    db: AsyncSession, company_id: uuid.UUID, dealer_id: uuid.UUID
) -> Invoice:
    invoice = Invoice(
        company_id=company_id,
        invoice_number=f"INV-{uuid.uuid4().hex[:8]}",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        invoice_date=date(2026, 1, 5),
        due_date=date(2026, 2, 4),
        subtotal=Decimal("1000.00"),
        gst_amount=Decimal("0.00"),
        total_amount=Decimal("1000.00"),
        status=InvoiceStatus.Partially_Paid,
        source=InvoiceSource.csv_import,
    )
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)
    db.add(
        Payment(
            company_id=company_id,
            invoice_id=invoice.id,
            amount=Decimal("400.00"),
            payment_date=date(2026, 1, 20),
        )
    )
    await db.commit()
    return invoice


@pytest.mark.asyncio
async def test_update_dealer(client: AsyncClient) -> None:
    company_id = await _create_company(client)
    create_resp = await client.post(
        f"/admin/companies/{company_id}/dealers",
        json={"name": "Old Name", "phone": "+919111111111"},
    )
    dealer_id = create_resp.json()["id"]

    resp = await client.patch(
        f"/admin/companies/{company_id}/dealers/{dealer_id}", json={"name": "New Name"}
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["name"] == "New Name"
    assert data["phone"] == "+919111111111"


@pytest.mark.asyncio
async def test_create_dealer_normalizes_bare_phone_number(client: AsyncClient) -> None:
    company_id = await _create_company(client)
    resp = await client.post(
        f"/admin/companies/{company_id}/dealers",
        json={"name": "Bare Number Dealer", "phone": "9876543210"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["phone"] == "+919876543210"


@pytest.mark.asyncio
async def test_create_dealer_rejects_invalid_phone(client: AsyncClient) -> None:
    company_id = await _create_company(client)
    resp = await client.post(
        f"/admin/companies/{company_id}/dealers",
        json={"name": "Bad Phone Dealer", "phone": "123"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_update_dealer_not_found(client: AsyncClient) -> None:
    company_id = await _create_company(client)
    resp = await client.patch(
        f"/admin/companies/{company_id}/dealers/{uuid.uuid4()}", json={"name": "X"}
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_dealer_no_invoices(client: AsyncClient) -> None:
    company_id = await _create_company(client)
    create_resp = await client.post(
        f"/admin/companies/{company_id}/dealers", json={"name": "No Invoices"}
    )
    dealer_id = create_resp.json()["id"]

    resp = await client.delete(f"/admin/companies/{company_id}/dealers/{dealer_id}")
    assert resp.status_code == 204

    get_resp = await client.get(f"/admin/companies/{company_id}/dealers/{dealer_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_dealer_cascades_invoices_and_payments(
    client: AsyncClient, db: AsyncSession
) -> None:
    company_id = await _create_company(client)
    create_resp = await client.post(
        f"/admin/companies/{company_id}/dealers", json={"name": "Cascade Dealer"}
    )
    dealer_id = uuid.UUID(create_resp.json()["id"])

    invoice = await _make_invoice_with_payment(db, uuid.UUID(company_id), dealer_id)

    resp = await client.delete(f"/admin/companies/{company_id}/dealers/{dealer_id}")
    assert resp.status_code == 204

    get_resp = await client.get(f"/admin/companies/{company_id}/dealers/{dealer_id}")
    assert get_resp.status_code == 404

    remaining_invoice = await db.scalar(select(Invoice).where(Invoice.id == invoice.id))
    assert remaining_invoice is None
    remaining_payments = await db.scalars(select(Payment).where(Payment.invoice_id == invoice.id))
    assert remaining_payments.all() == []


@pytest.mark.asyncio
async def test_delete_dealer_preview_counts(client: AsyncClient, db: AsyncSession) -> None:
    company_id = await _create_company(client)
    create_resp = await client.post(
        f"/admin/companies/{company_id}/dealers", json={"name": "Preview Dealer"}
    )
    dealer_id = uuid.UUID(create_resp.json()["id"])

    await _make_invoice_with_payment(db, uuid.UUID(company_id), dealer_id)

    resp = await client.get(f"/admin/companies/{company_id}/dealers/{dealer_id}/delete-preview")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["invoice_count"] == 1
    assert Decimal(data["total_amount"]) == Decimal("1000.00")


@pytest.mark.asyncio
async def test_delete_nonexistent_dealer_404(client: AsyncClient) -> None:
    company_id = await _create_company(client)
    resp = await client.delete(f"/admin/companies/{company_id}/dealers/{uuid.uuid4()}")
    assert resp.status_code == 404
