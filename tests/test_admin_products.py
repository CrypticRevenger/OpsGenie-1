"""Admin product endpoint tests — Phase 2B.

    uv run alembic upgrade head
    uv run pytest tests/test_admin_products.py -v
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceDirection, InvoiceSource, InvoiceStatus
from app.models.invoice_item import InvoiceItem
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _unique_phone() -> str:
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


async def _create_company(client: AsyncClient) -> str:
    resp = await client.post(
        "/admin/companies",
        json={
            "business_name": "Product Test Co",
            "owner_name": "Owner",
            "whatsapp_number": _unique_phone(),
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_create_product(client: AsyncClient) -> None:
    company_id = await _create_company(client)
    payload = {
        "name": "Rice",
        "unit": "kg",
        "selling_price": "55.00",
        "purchase_price": "45.00",
        "stock_quantity": "100",
    }
    resp = await client.post(f"/admin/companies/{company_id}/products", json=payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["name"] == "Rice"
    assert data["company_id"] == company_id
    assert Decimal(data["selling_price"]) == Decimal("55.00")
    assert Decimal(data["stock_quantity"]) == Decimal("100")


@pytest.mark.asyncio
async def test_create_product_defaults_stock_to_zero(client: AsyncClient) -> None:
    company_id = await _create_company(client)
    resp = await client.post(
        f"/admin/companies/{company_id}/products", json={"name": "Wheat"}
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert Decimal(data["stock_quantity"]) == Decimal("0")
    assert data["selling_price"] is None


@pytest.mark.asyncio
async def test_create_product_company_not_found(client: AsyncClient) -> None:
    resp = await client.post(
        f"/admin/companies/{uuid.uuid4()}/products", json={"name": "Ghost Product"}
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_products(client: AsyncClient) -> None:
    company_id = await _create_company(client)
    for name in ("Rice", "Wheat"):
        await client.post(f"/admin/companies/{company_id}/products", json={"name": name})

    resp = await client.get(f"/admin/companies/{company_id}/products")
    assert resp.status_code == 200
    data = resp.json()
    names = [p["name"] for p in data["items"]]
    assert "Rice" in names
    assert "Wheat" in names
    assert data["total"] == 2


@pytest.mark.asyncio
async def test_get_product(client: AsyncClient) -> None:
    company_id = await _create_company(client)
    create_resp = await client.post(
        f"/admin/companies/{company_id}/products", json={"name": "Sugar"}
    )
    product_id = create_resp.json()["id"]

    resp = await client.get(f"/admin/companies/{company_id}/products/{product_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == product_id


@pytest.mark.asyncio
async def test_update_product_sets_price_and_restocks(client: AsyncClient) -> None:
    company_id = await _create_company(client)
    create_resp = await client.post(
        f"/admin/companies/{company_id}/products", json={"name": "Onboarded Product"}
    )
    product_id = create_resp.json()["id"]
    assert create_resp.json()["selling_price"] is None

    resp = await client.patch(
        f"/admin/companies/{company_id}/products/{product_id}",
        json={"selling_price": "20.00", "stock_quantity": "500"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert Decimal(data["selling_price"]) == Decimal("20.00")
    assert Decimal(data["stock_quantity"]) == Decimal("500")


@pytest.mark.asyncio
async def test_update_product_not_found(client: AsyncClient) -> None:
    company_id = await _create_company(client)
    resp = await client.patch(
        f"/admin/companies/{company_id}/products/{uuid.uuid4()}",
        json={"stock_quantity": "10"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_product(client: AsyncClient) -> None:
    company_id = await _create_company(client)
    create_resp = await client.post(
        f"/admin/companies/{company_id}/products", json={"name": "Salt"}
    )
    product_id = create_resp.json()["id"]

    resp = await client.delete(f"/admin/companies/{company_id}/products/{product_id}")
    assert resp.status_code == 204

    get_resp = await client.get(f"/admin/companies/{company_id}/products/{product_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_product_not_found(client: AsyncClient) -> None:
    company_id = await _create_company(client)
    resp = await client.delete(f"/admin/companies/{company_id}/products/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_product_with_invoice_items_sets_null(
    client: AsyncClient, db: AsyncSession
) -> None:
    company_id = await _create_company(client)
    create_resp = await client.post(
        f"/admin/companies/{company_id}/products", json={"name": "Linked Product"}
    )
    product_id = uuid.UUID(create_resp.json()["id"])

    company_uuid = uuid.UUID(company_id)
    invoice = Invoice(
        company_id=company_uuid,
        invoice_number=f"INV-{uuid.uuid4().hex[:8]}",
        direction=InvoiceDirection.receivable,
        invoice_date=date(2026, 1, 5),
        due_date=date(2026, 2, 4),
        subtotal=Decimal("100.00"),
        gst_amount=Decimal("0.00"),
        total_amount=Decimal("100.00"),
        status=InvoiceStatus.Pending,
        source=InvoiceSource.csv_import,
    )
    # dealer_id/supplier_id both null is fine for this test since we only
    # care about the product FK, not the CHECK constraint's own behavior.
    dealer = Dealer(company_id=company_uuid, name="Item Dealer")
    db.add(dealer)
    await db.commit()
    await db.refresh(dealer)
    invoice.dealer_id = dealer.id
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)

    item = InvoiceItem(
        invoice_id=invoice.id,
        product_id=product_id,
        description="Linked Product",
        quantity=Decimal("1"),
        unit_price=Decimal("100.00"),
        line_total=Decimal("100.00"),
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)

    resp = await client.delete(f"/admin/companies/{company_id}/products/{product_id}")
    assert resp.status_code == 204

    # The delete happened through the client's own DB session, not this
    # fixture's — refresh so we see the committed row instead of this
    # session's stale identity-mapped copy of `item`.
    await db.refresh(item)
    refreshed_item = item
    assert refreshed_item is not None
    assert refreshed_item.product_id is None
    refreshed_invoice = await db.scalar(select(Invoice).where(Invoice.id == invoice.id))
    assert refreshed_invoice is not None
