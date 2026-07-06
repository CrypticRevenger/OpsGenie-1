"""Admin payment read API tests — Phase 4.

Requires postgres running with migrations applied:

    uv run alembic upgrade head
    uv run pytest tests/test_admin_payments.py -v
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from app.models.company import Company
from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceDirection, InvoiceSource, InvoiceStatus
from app.models.payment import Payment
from app.models.supplier import Supplier
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


def _unique_phone() -> str:
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


async def _make_company(db: AsyncSession) -> uuid.UUID:
    company = Company(
        business_name="Payment API Test Co", owner_name="Owner", whatsapp_number=_unique_phone()
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company.id


async def _make_dealer(db: AsyncSession, company_id: uuid.UUID, name: str) -> uuid.UUID:
    dealer = Dealer(company_id=company_id, name=name)
    db.add(dealer)
    await db.commit()
    await db.refresh(dealer)
    return dealer.id


async def _make_supplier(db: AsyncSession, company_id: uuid.UUID, name: str) -> uuid.UUID:
    supplier = Supplier(company_id=company_id, name=name)
    db.add(supplier)
    await db.commit()
    await db.refresh(supplier)
    return supplier.id


async def _make_invoice(
    db: AsyncSession,
    company_id: uuid.UUID,
    *,
    invoice_number: str,
    direction: InvoiceDirection,
    dealer_id: uuid.UUID | None = None,
    supplier_id: uuid.UUID | None = None,
    total_amount: Decimal,
) -> Invoice:
    invoice = Invoice(
        company_id=company_id,
        invoice_number=invoice_number,
        direction=direction,
        dealer_id=dealer_id,
        supplier_id=supplier_id,
        invoice_date=date(2026, 1, 5),
        due_date=date(2026, 2, 4),
        subtotal=total_amount,
        gst_amount=Decimal("0.00"),
        total_amount=total_amount,
        status=InvoiceStatus.Pending,
        source=InvoiceSource.csv_import,
    )
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)
    return invoice


async def _make_payment(
    db: AsyncSession, company_id: uuid.UUID, invoice_id: uuid.UUID, amount: Decimal
) -> Payment:
    payment = Payment(
        company_id=company_id,
        invoice_id=invoice_id,
        amount=amount,
        payment_date=date(2026, 1, 20),
    )
    db.add(payment)
    await db.commit()
    await db.refresh(payment)
    return payment


@pytest.mark.asyncio
async def test_list_payments_returns_all(client: AsyncClient, db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id, "Dealer P1")
    invoice = await _make_invoice(
        db,
        company_id,
        invoice_number="INV-PAY-1",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        total_amount=Decimal("5000.00"),
    )
    await _make_payment(db, company_id, invoice.id, Decimal("2000.00"))
    await _make_payment(db, company_id, invoice.id, Decimal("3000.00"))

    resp = await client.get(f"/admin/companies/{company_id}/payments")
    assert resp.status_code == 200
    data = resp.json()
    amounts = sorted(Decimal(p["amount"]) for p in data["items"])
    assert amounts == [Decimal("2000.00"), Decimal("3000.00")]
    assert data["total"] == 2


@pytest.mark.asyncio
async def test_list_payments_filters_by_invoice_id(client: AsyncClient, db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id, "Dealer P2")
    invoice_a = await _make_invoice(
        db,
        company_id,
        invoice_number="INV-PAY-A",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        total_amount=Decimal("1000.00"),
    )
    invoice_b = await _make_invoice(
        db,
        company_id,
        invoice_number="INV-PAY-B",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        total_amount=Decimal("1000.00"),
    )
    await _make_payment(db, company_id, invoice_a.id, Decimal("500.00"))
    await _make_payment(db, company_id, invoice_b.id, Decimal("700.00"))

    resp = await client.get(
        f"/admin/companies/{company_id}/payments", params={"invoice_id": str(invoice_a.id)}
    )
    assert resp.status_code == 200
    data = resp.json()["items"]
    assert len(data) == 1
    assert Decimal(data[0]["amount"]) == Decimal("500.00")


@pytest.mark.asyncio
async def test_list_payments_filters_by_dealer_id(client: AsyncClient, db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer_a = await _make_dealer(db, company_id, "Dealer P3")
    dealer_b = await _make_dealer(db, company_id, "Dealer P4")
    invoice_a = await _make_invoice(
        db,
        company_id,
        invoice_number="INV-PAY-DA",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_a,
        total_amount=Decimal("1000.00"),
    )
    invoice_b = await _make_invoice(
        db,
        company_id,
        invoice_number="INV-PAY-DB",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_b,
        total_amount=Decimal("1000.00"),
    )
    await _make_payment(db, company_id, invoice_a.id, Decimal("111.00"))
    await _make_payment(db, company_id, invoice_b.id, Decimal("222.00"))

    resp = await client.get(
        f"/admin/companies/{company_id}/payments", params={"dealer_id": str(dealer_a)}
    )
    assert resp.status_code == 200
    data = resp.json()["items"]
    assert len(data) == 1
    assert Decimal(data[0]["amount"]) == Decimal("111.00")


@pytest.mark.asyncio
async def test_list_payments_filters_by_supplier_id(client: AsyncClient, db: AsyncSession) -> None:
    company_id = await _make_company(db)
    supplier_id = await _make_supplier(db, company_id, "Supplier P1")
    invoice = await _make_invoice(
        db,
        company_id,
        invoice_number="INV-PAY-SUP",
        direction=InvoiceDirection.payable,
        supplier_id=supplier_id,
        total_amount=Decimal("1000.00"),
    )
    await _make_payment(db, company_id, invoice.id, Decimal("999.00"))

    resp = await client.get(
        f"/admin/companies/{company_id}/payments", params={"supplier_id": str(supplier_id)}
    )
    assert resp.status_code == 200
    data = resp.json()["items"]
    assert len(data) == 1
    assert Decimal(data[0]["amount"]) == Decimal("999.00")


@pytest.mark.asyncio
async def test_payments_scoped_to_company(client: AsyncClient, db: AsyncSession) -> None:
    company_a = await _make_company(db)
    company_b = await _make_company(db)
    dealer_a = await _make_dealer(db, company_a, "Dealer P5")
    invoice_a = await _make_invoice(
        db,
        company_a,
        invoice_number="INV-PAY-ISOLATED",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_a,
        total_amount=Decimal("1000.00"),
    )
    await _make_payment(db, company_a, invoice_a.id, Decimal("444.00"))

    resp = await client.get(f"/admin/companies/{company_b}/payments")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["pages"] == 0


@pytest.mark.asyncio
async def test_list_payments_company_not_found(client: AsyncClient) -> None:
    resp = await client.get(f"/admin/companies/{uuid.uuid4()}/payments")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_payments_pagination_total_respects_filters(
    client: AsyncClient, db: AsyncSession
) -> None:
    company_id = await _make_company(db)
    dealer_a = await _make_dealer(db, company_id, "Dealer P6")
    dealer_b = await _make_dealer(db, company_id, "Dealer P7")
    invoice_a = await _make_invoice(
        db,
        company_id,
        invoice_number="INV-PAGE-PAY-A",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_a,
        total_amount=Decimal("5000.00"),
    )
    invoice_b = await _make_invoice(
        db,
        company_id,
        invoice_number="INV-PAGE-PAY-B",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_b,
        total_amount=Decimal("5000.00"),
    )
    for amount in (Decimal("100.00"), Decimal("200.00"), Decimal("300.00")):
        await _make_payment(db, company_id, invoice_a.id, amount)
    await _make_payment(db, company_id, invoice_b.id, Decimal("999.00"))

    resp = await client.get(
        f"/admin/companies/{company_id}/payments",
        params={"dealer_id": str(dealer_a), "page": 1, "limit": 2},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["total"] == 3  # filtered count, not all 4 payments in the company
    assert data["pages"] == 2


# ── Delete ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_payment(client: AsyncClient, db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id, "Dealer Delete Payment")
    invoice = await _make_invoice(
        db,
        company_id,
        invoice_number="INV-PAY-DELETE",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        total_amount=Decimal("1000.00"),
    )
    payment = await _make_payment(db, company_id, invoice.id, Decimal("300.00"))

    resp = await client.delete(f"/admin/companies/{company_id}/payments/{payment.id}")
    assert resp.status_code == 204

    list_resp = await client.get(f"/admin/companies/{company_id}/payments")
    assert list_resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_delete_payment_not_found(client: AsyncClient, db: AsyncSession) -> None:
    company_id = await _make_company(db)
    resp = await client.delete(f"/admin/companies/{company_id}/payments/{uuid.uuid4()}")
    assert resp.status_code == 404
