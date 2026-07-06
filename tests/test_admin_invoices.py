"""Admin invoice read API tests — Phase 4.

Requires postgres running with migrations applied:

    uv run alembic upgrade head
    uv run pytest tests/test_admin_invoices.py -v
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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _unique_phone() -> str:
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


async def _make_company(db: AsyncSession) -> uuid.UUID:
    company = Company(
        business_name="Invoice API Test Co", owner_name="Owner", whatsapp_number=_unique_phone()
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
    status: InvoiceStatus = InvoiceStatus.Pending,
    due_date: date | None = None,
) -> Invoice:
    invoice = Invoice(
        company_id=company_id,
        invoice_number=invoice_number,
        direction=direction,
        dealer_id=dealer_id,
        supplier_id=supplier_id,
        invoice_date=date(2026, 1, 5),
        due_date=due_date or date(2026, 2, 4),
        subtotal=total_amount,
        gst_amount=Decimal("0.00"),
        total_amount=total_amount,
        status=status,
        source=InvoiceSource.csv_import,
    )
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)
    return invoice


async def _make_payment(
    db: AsyncSession, company_id: uuid.UUID, invoice_id: uuid.UUID, amount: Decimal
) -> None:
    db.add(
        Payment(
            company_id=company_id,
            invoice_id=invoice_id,
            amount=amount,
            payment_date=date(2026, 1, 20),
        )
    )
    await db.commit()


# ── Listing + filters ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_invoices_returns_all(client: AsyncClient, db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id, "Dealer A")
    await _make_invoice(
        db,
        company_id,
        invoice_number="INV-L1",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        total_amount=Decimal("1000.00"),
    )
    await _make_invoice(
        db,
        company_id,
        invoice_number="INV-L2",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        total_amount=Decimal("2000.00"),
    )

    resp = await client.get(f"/admin/companies/{company_id}/invoices")
    assert resp.status_code == 200
    data = resp.json()
    numbers = {inv["invoice_number"] for inv in data["items"]}
    assert numbers == {"INV-L1", "INV-L2"}
    assert data["total"] == 2


@pytest.mark.asyncio
async def test_list_invoices_filters_by_direction(client: AsyncClient, db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id, "Dealer B")
    supplier_id = await _make_supplier(db, company_id, "Supplier B")
    await _make_invoice(
        db,
        company_id,
        invoice_number="INV-DIR-R",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        total_amount=Decimal("1000.00"),
    )
    await _make_invoice(
        db,
        company_id,
        invoice_number="INV-DIR-P",
        direction=InvoiceDirection.payable,
        supplier_id=supplier_id,
        total_amount=Decimal("1000.00"),
    )

    resp = await client.get(
        f"/admin/companies/{company_id}/invoices", params={"direction": "payable"}
    )
    assert resp.status_code == 200
    numbers = {inv["invoice_number"] for inv in resp.json()["items"]}
    assert numbers == {"INV-DIR-P"}


@pytest.mark.asyncio
async def test_list_invoices_filters_by_status(client: AsyncClient, db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id, "Dealer C")
    await _make_invoice(
        db,
        company_id,
        invoice_number="INV-ST-PAID",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        total_amount=Decimal("1000.00"),
        status=InvoiceStatus.Paid,
    )
    await _make_invoice(
        db,
        company_id,
        invoice_number="INV-ST-PENDING",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        total_amount=Decimal("1000.00"),
        status=InvoiceStatus.Pending,
    )

    resp = await client.get(f"/admin/companies/{company_id}/invoices", params={"status": "Paid"})
    assert resp.status_code == 200
    numbers = {inv["invoice_number"] for inv in resp.json()["items"]}
    assert numbers == {"INV-ST-PAID"}


@pytest.mark.asyncio
async def test_list_invoices_filters_by_dealer_id(client: AsyncClient, db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer_a = await _make_dealer(db, company_id, "Dealer D1")
    dealer_b = await _make_dealer(db, company_id, "Dealer D2")
    await _make_invoice(
        db,
        company_id,
        invoice_number="INV-DEALER-A",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_a,
        total_amount=Decimal("1000.00"),
    )
    await _make_invoice(
        db,
        company_id,
        invoice_number="INV-DEALER-B",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_b,
        total_amount=Decimal("1000.00"),
    )

    resp = await client.get(
        f"/admin/companies/{company_id}/invoices", params={"dealer_id": str(dealer_a)}
    )
    assert resp.status_code == 200
    numbers = {inv["invoice_number"] for inv in resp.json()["items"]}
    assert numbers == {"INV-DEALER-A"}


# ── amount_paid / amount_outstanding ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_amount_paid_and_outstanding_across_statuses(
    client: AsyncClient, db: AsyncSession
) -> None:
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id, "Dealer E")

    await _make_invoice(
        db,
        company_id,
        invoice_number="INV-AMT-PENDING",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        total_amount=Decimal("5000.00"),
        status=InvoiceStatus.Pending,
    )
    partial = await _make_invoice(
        db,
        company_id,
        invoice_number="INV-AMT-PARTIAL",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        total_amount=Decimal("5000.00"),
        status=InvoiceStatus.Partially_Paid,
    )
    await _make_payment(db, company_id, partial.id, Decimal("2000.00"))
    paid = await _make_invoice(
        db,
        company_id,
        invoice_number="INV-AMT-PAID",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        total_amount=Decimal("5000.00"),
        status=InvoiceStatus.Paid,
    )
    await _make_payment(db, company_id, paid.id, Decimal("5000.00"))

    resp = await client.get(f"/admin/companies/{company_id}/invoices")
    by_number = {inv["invoice_number"]: inv for inv in resp.json()["items"]}

    assert Decimal(by_number["INV-AMT-PENDING"]["amount_paid"]) == Decimal("0.00")
    assert Decimal(by_number["INV-AMT-PENDING"]["amount_outstanding"]) == Decimal("5000.00")

    assert Decimal(by_number["INV-AMT-PARTIAL"]["amount_paid"]) == Decimal("2000.00")
    assert Decimal(by_number["INV-AMT-PARTIAL"]["amount_outstanding"]) == Decimal("3000.00")

    assert Decimal(by_number["INV-AMT-PAID"]["amount_paid"]) == Decimal("5000.00")
    assert Decimal(by_number["INV-AMT-PAID"]["amount_outstanding"]) == Decimal("0.00")


# ── Single invoice detail ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_invoice_includes_payments(client: AsyncClient, db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id, "Dealer F")
    invoice = await _make_invoice(
        db,
        company_id,
        invoice_number="INV-DETAIL",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        total_amount=Decimal("9000.00"),
        status=InvoiceStatus.Partially_Paid,
    )
    await _make_payment(db, company_id, invoice.id, Decimal("3000.00"))
    await _make_payment(db, company_id, invoice.id, Decimal("1000.00"))

    resp = await client.get(f"/admin/companies/{company_id}/invoices/{invoice.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["invoice_number"] == "INV-DETAIL"
    assert len(data["payments"]) == 2
    assert Decimal(data["amount_paid"]) == Decimal("4000.00")
    assert Decimal(data["amount_outstanding"]) == Decimal("5000.00")


@pytest.mark.asyncio
async def test_get_invoice_not_found(client: AsyncClient, db: AsyncSession) -> None:
    company_id = await _make_company(db)
    resp = await client.get(f"/admin/companies/{company_id}/invoices/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_invoice_wrong_company_returns_404(client: AsyncClient, db: AsyncSession) -> None:
    company_a = await _make_company(db)
    company_b = await _make_company(db)
    dealer_id = await _make_dealer(db, company_a, "Dealer G")
    invoice = await _make_invoice(
        db,
        company_a,
        invoice_number="INV-CROSS",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        total_amount=Decimal("1000.00"),
    )

    resp = await client.get(f"/admin/companies/{company_b}/invoices/{invoice.id}")
    assert resp.status_code == 404


# ── Cross-company isolation ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_invoices_scoped_to_company(client: AsyncClient, db: AsyncSession) -> None:
    company_a = await _make_company(db)
    company_b = await _make_company(db)
    dealer_a = await _make_dealer(db, company_a, "Dealer H")
    await _make_invoice(
        db,
        company_a,
        invoice_number="INV-ISOLATED",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_a,
        total_amount=Decimal("1000.00"),
    )

    resp = await client.get(f"/admin/companies/{company_b}/invoices")
    assert resp.status_code == 200
    numbers = {inv["invoice_number"] for inv in resp.json()["items"]}
    assert "INV-ISOLATED" not in numbers


@pytest.mark.asyncio
async def test_list_invoices_company_not_found(client: AsyncClient) -> None:
    resp = await client.get(f"/admin/companies/{uuid.uuid4()}/invoices")
    assert resp.status_code == 404


# ── Pagination ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_invoices_pagination_total_respects_filters(
    client: AsyncClient, db: AsyncSession
) -> None:
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id, "Dealer Page")
    supplier_id = await _make_supplier(db, company_id, "Supplier Page")
    for i in range(3):
        await _make_invoice(
            db,
            company_id,
            invoice_number=f"INV-PAGE-R{i}",
            direction=InvoiceDirection.receivable,
            dealer_id=dealer_id,
            total_amount=Decimal("1000.00"),
        )
    await _make_invoice(
        db,
        company_id,
        invoice_number="INV-PAGE-P",
        direction=InvoiceDirection.payable,
        supplier_id=supplier_id,
        total_amount=Decimal("1000.00"),
    )

    # total must reflect the filter, not the whole company's invoice count.
    resp = await client.get(
        f"/admin/companies/{company_id}/invoices",
        params={"direction": "receivable", "page": 1, "limit": 2},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["total"] == 3
    assert data["pages"] == 2


# ── Delete ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_invoice_cascades_items_and_payments(
    client: AsyncClient, db: AsyncSession
) -> None:
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id, "Dealer Delete")
    invoice = await _make_invoice(
        db,
        company_id,
        invoice_number="INV-DELETE",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        total_amount=Decimal("1000.00"),
    )
    await _make_payment(db, company_id, invoice.id, Decimal("300.00"))

    resp = await client.delete(f"/admin/companies/{company_id}/invoices/{invoice.id}")
    assert resp.status_code == 204

    remaining_payments = await db.scalars(select(Payment).where(Payment.invoice_id == invoice.id))
    assert remaining_payments.all() == []

    get_resp = await client.get(f"/admin/companies/{company_id}/invoices/{invoice.id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_invoice_not_found(client: AsyncClient, db: AsyncSession) -> None:
    company_id = await _make_company(db)
    resp = await client.delete(f"/admin/companies/{company_id}/invoices/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_invoice_wrong_company_404(client: AsyncClient, db: AsyncSession) -> None:
    company_a = await _make_company(db)
    company_b = await _make_company(db)
    dealer_id = await _make_dealer(db, company_a, "Dealer Cross Delete")
    invoice = await _make_invoice(
        db,
        company_a,
        invoice_number="INV-CROSS-DELETE",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        total_amount=Decimal("1000.00"),
    )
    resp = await client.delete(f"/admin/companies/{company_b}/invoices/{invoice.id}")
    assert resp.status_code == 404
