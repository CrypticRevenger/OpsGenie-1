"""Admin supplier endpoint tests — dashboard-driven full CRUD.

    uv run alembic upgrade head
    uv run pytest tests/test_admin_suppliers.py -v
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
            "business_name": "Supplier Test Co",
            "owner_name": "Owner",
            "whatsapp_number": _unique_phone(),
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _make_invoice_with_payment(
    db: AsyncSession, company_id: uuid.UUID, supplier_id: uuid.UUID
) -> Invoice:
    invoice = Invoice(
        company_id=company_id,
        invoice_number=f"INV-{uuid.uuid4().hex[:8]}",
        direction=InvoiceDirection.payable,
        supplier_id=supplier_id,
        invoice_date=date(2026, 1, 5),
        due_date=date(2026, 2, 4),
        subtotal=Decimal("2000.00"),
        gst_amount=Decimal("0.00"),
        total_amount=Decimal("2000.00"),
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
            amount=Decimal("500.00"),
            payment_date=date(2026, 1, 20),
        )
    )
    await db.commit()
    return invoice


@pytest.mark.asyncio
async def test_update_supplier(client: AsyncClient) -> None:
    company_id = await _create_company(client)
    create_resp = await client.post(
        f"/admin/companies/{company_id}/suppliers",
        json={"name": "Old Name", "phone": "+922222222222"},
    )
    supplier_id = create_resp.json()["id"]

    resp = await client.patch(
        f"/admin/companies/{company_id}/suppliers/{supplier_id}", json={"name": "New Name"}
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["name"] == "New Name"
    assert data["phone"] == "+922222222222"


@pytest.mark.asyncio
async def test_update_supplier_not_found(client: AsyncClient) -> None:
    company_id = await _create_company(client)
    resp = await client.patch(
        f"/admin/companies/{company_id}/suppliers/{uuid.uuid4()}", json={"name": "X"}
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_supplier_no_invoices(client: AsyncClient) -> None:
    company_id = await _create_company(client)
    create_resp = await client.post(
        f"/admin/companies/{company_id}/suppliers", json={"name": "No Invoices"}
    )
    supplier_id = create_resp.json()["id"]

    resp = await client.delete(f"/admin/companies/{company_id}/suppliers/{supplier_id}")
    assert resp.status_code == 204

    get_resp = await client.get(f"/admin/companies/{company_id}/suppliers/{supplier_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_supplier_cascades_invoices_and_payments(
    client: AsyncClient, db: AsyncSession
) -> None:
    company_id = await _create_company(client)
    create_resp = await client.post(
        f"/admin/companies/{company_id}/suppliers", json={"name": "Cascade Supplier"}
    )
    supplier_id = uuid.UUID(create_resp.json()["id"])

    invoice = await _make_invoice_with_payment(db, uuid.UUID(company_id), supplier_id)

    resp = await client.delete(f"/admin/companies/{company_id}/suppliers/{supplier_id}")
    assert resp.status_code == 204

    get_resp = await client.get(f"/admin/companies/{company_id}/suppliers/{supplier_id}")
    assert get_resp.status_code == 404

    remaining_invoice = await db.scalar(select(Invoice).where(Invoice.id == invoice.id))
    assert remaining_invoice is None
    remaining_payments = await db.scalars(select(Payment).where(Payment.invoice_id == invoice.id))
    assert remaining_payments.all() == []


@pytest.mark.asyncio
async def test_delete_supplier_preview_counts(client: AsyncClient, db: AsyncSession) -> None:
    company_id = await _create_company(client)
    create_resp = await client.post(
        f"/admin/companies/{company_id}/suppliers", json={"name": "Preview Supplier"}
    )
    supplier_id = uuid.UUID(create_resp.json()["id"])

    await _make_invoice_with_payment(db, uuid.UUID(company_id), supplier_id)

    resp = await client.get(f"/admin/companies/{company_id}/suppliers/{supplier_id}/delete-preview")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["invoice_count"] == 1
    assert Decimal(data["total_amount"]) == Decimal("2000.00")


@pytest.mark.asyncio
async def test_delete_nonexistent_supplier_404(client: AsyncClient) -> None:
    company_id = await _create_company(client)
    resp = await client.delete(f"/admin/companies/{company_id}/suppliers/{uuid.uuid4()}")
    assert resp.status_code == 404
