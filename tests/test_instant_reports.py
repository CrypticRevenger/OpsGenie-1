"""Deterministic WhatsApp report formatters — no LLM involved.

Direct function-level tests against app/services/instant_reports.py (fast,
no HTTP/webhook overhead) — the webhook-wiring itself (menu-row tap /
keyword -> _INSTANT_COMMANDS -> these functions, bypassing the LLM
assistant entirely) is covered by a few smoke tests in
tests/test_webhooks_whatsapp.py instead of repeating per command here.

    uv run alembic upgrade head
    uv run pytest tests/test_instant_reports.py -v
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from app.models.company import Company
from app.models.dealer import Dealer
from app.models.faq import FAQ
from app.models.invoice import Invoice, InvoiceDirection, InvoiceSource, InvoiceStatus
from app.models.payment import Payment, PaymentSource
from app.models.product import Product
from app.models.supplier import Supplier
from app.services import instant_reports
from sqlalchemy.ext.asyncio import AsyncSession


def _unique_number() -> str:
    return f"+919{uuid.uuid4().int % 1_000_000_000:09d}"


async def _fresh_company(db: AsyncSession) -> Company:
    company = Company(
        business_name="Instant Reports Co", owner_name="Owner", whatsapp_number=_unique_number()
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company


@pytest.mark.asyncio
async def test_empty_states_never_crash(db: AsyncSession) -> None:
    """A brand-new company with no data at all — every formatter must
    degrade to a friendly "nothing yet" message, never raise.
    """
    company = await _fresh_company(db)

    expectations = [
        (instant_reports.cash_position_reply, "cash"),
        (instant_reports.business_summary_reply, "summary"),
        # A brand-new company always gets a "no data imported yet" priority
        # action (build_recommendations' own rule) — never truly empty.
        (instant_reports.priorities_reply, "priorities"),
        (instant_reports.overdue_dealers_reply, "no overdue"),
        (instant_reports.upcoming_collections_reply, "no collections"),
        (instant_reports.upcoming_payments_reply, "no supplier payments"),
        (instant_reports.all_dealers_reply, "don't have any dealers"),
        (instant_reports.all_suppliers_reply, "don't have any suppliers"),
        (instant_reports.top_debtors_reply, "no dealer"),
        (instant_reports.top_creditors_reply, "don't currently owe"),
        (instant_reports.inventory_reply, "don't have any products"),
        (instant_reports.faqs_reply, "don't have any saved policy"),
        (instant_reports.invoices_reply, "don't have any invoices"),
        (instant_reports.payments_reply, "don't have any payments"),
    ]
    for fn, expected_substring in expectations:
        reply = await fn(db, company)
        assert expected_substring in reply.lower(), f"{fn.__name__}: {reply!r}"


@pytest.mark.asyncio
async def test_all_dealers_and_top_debtors_show_real_outstanding(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    dealer = Dealer(company_id=company.id, name="Ram Traders", phone="9876543210")
    db.add(dealer)
    await db.flush()
    db.add(
        Invoice(
            company_id=company.id,
            invoice_number="INV-1",
            direction=InvoiceDirection.receivable,
            dealer_id=dealer.id,
            invoice_date=date(2026, 1, 1),
            due_date=date(2026, 1, 1),
            subtotal=Decimal("20000.00"),
            gst_amount=Decimal("0.00"),
            total_amount=Decimal("20000.00"),
            status=InvoiceStatus.Pending,
            source=InvoiceSource.csv_import,
        )
    )
    await db.commit()

    dealers_reply = await instant_reports.all_dealers_reply(db, company)
    assert "Ram Traders" in dealers_reply
    assert "9876543210" in dealers_reply
    assert "20,000" in dealers_reply

    debtors_reply = await instant_reports.top_debtors_reply(db, company)
    assert "Ram Traders" in debtors_reply
    assert "20,000" in debtors_reply


@pytest.mark.asyncio
async def test_all_suppliers_and_top_creditors_show_real_outstanding(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    supplier = Supplier(company_id=company.id, name="ABC Pharma", phone="9123456789")
    db.add(supplier)
    await db.flush()
    db.add(
        Invoice(
            company_id=company.id,
            invoice_number="INV-P1",
            direction=InvoiceDirection.payable,
            supplier_id=supplier.id,
            invoice_date=date(2026, 1, 1),
            due_date=date(2026, 1, 1),
            subtotal=Decimal("15000.00"),
            gst_amount=Decimal("0.00"),
            total_amount=Decimal("15000.00"),
            status=InvoiceStatus.Pending,
            source=InvoiceSource.csv_import,
        )
    )
    await db.commit()

    suppliers_reply = await instant_reports.all_suppliers_reply(db, company)
    assert "ABC Pharma" in suppliers_reply
    assert "9123456789" in suppliers_reply
    assert "15,000" in suppliers_reply

    creditors_reply = await instant_reports.top_creditors_reply(db, company)
    assert "ABC Pharma" in creditors_reply
    assert "15,000" in creditors_reply


@pytest.mark.asyncio
async def test_inventory_shows_real_products(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    db.add(
        Product(
            company_id=company.id,
            name="Rice",
            unit="kg",
            selling_price=Decimal("400.00"),
            purchase_price=Decimal("300.00"),
            stock_quantity=Decimal("100"),
        )
    )
    db.add(
        Product(
            company_id=company.id,
            name="Dal",
            unit=None,
            selling_price=None,
            stock_quantity=Decimal("0"),
        )
    )
    await db.commit()

    reply = await instant_reports.inventory_reply(db, company)
    assert "Rice" in reply
    assert "kg" in reply
    assert "400" in reply
    assert "Dal" in reply
    assert "price not set" in reply


@pytest.mark.asyncio
async def test_faqs_shows_real_qa_pairs(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    db.add(FAQ(company_id=company.id, question="What are delivery days?", answer="Mon-Sat"))
    await db.commit()

    reply = await instant_reports.faqs_reply(db, company)
    assert "What are delivery days?" in reply
    assert "Mon-Sat" in reply


@pytest.mark.asyncio
async def test_invoices_reply_lists_all_and_targets_right_ones(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    dealer = Dealer(company_id=company.id, name="Matru")
    db.add(dealer)
    await db.flush()
    db.add(
        Invoice(
            company_id=company.id,
            invoice_number="INV-OLD",
            direction=InvoiceDirection.receivable,
            dealer_id=dealer.id,
            invoice_date=date(2026, 1, 1),
            due_date=date(2026, 1, 1),
            subtotal=Decimal("50000.00"),
            gst_amount=Decimal("0.00"),
            total_amount=Decimal("50000.00"),
            status=InvoiceStatus.Pending,
            source=InvoiceSource.csv_import,
        )
    )
    db.add(
        Invoice(
            company_id=company.id,
            invoice_number="INV-NEW",
            direction=InvoiceDirection.receivable,
            dealer_id=dealer.id,
            invoice_date=date(2026, 1, 10),
            due_date=date(2026, 1, 10),
            subtotal=Decimal("30000.00"),
            gst_amount=Decimal("0.00"),
            total_amount=Decimal("30000.00"),
            status=InvoiceStatus.Paid,
            source=InvoiceSource.csv_import,
        )
    )
    await db.commit()

    reply = await instant_reports.invoices_reply(db, company)
    assert "INV-OLD" in reply
    assert "INV-NEW" in reply
    assert "Invoices (2):" in reply
    assert "…and" not in reply  # under the cap, no truncation note


@pytest.mark.asyncio
async def test_invoices_reply_truncates_with_accurate_count(db: AsyncSession, monkeypatch) -> None:
    """A party with more invoices than the reply cap must still report the
    true total (not the capped batch size) in the "…and N more" note.
    """
    monkeypatch.setattr(instant_reports, "_LIST_REPLY_CAP", 2)
    company = await _fresh_company(db)
    dealer = Dealer(company_id=company.id, name="Matru")
    db.add(dealer)
    await db.flush()
    for i in range(5):
        db.add(
            Invoice(
                company_id=company.id,
                invoice_number=f"INV-{i}",
                direction=InvoiceDirection.receivable,
                dealer_id=dealer.id,
                invoice_date=date(2026, 1, 1) + timedelta(days=i),
                due_date=date(2026, 1, 1) + timedelta(days=i),
                subtotal=Decimal("1000.00"),
                gst_amount=Decimal("0.00"),
                total_amount=Decimal("1000.00"),
                status=InvoiceStatus.Pending,
                source=InvoiceSource.csv_import,
            )
        )
    await db.commit()

    reply = await instant_reports.invoices_reply(db, company)
    assert "Invoices (2 of 5):" in reply
    assert "…and 3 more" in reply


@pytest.mark.asyncio
async def test_payments_reply_lists_real_payments(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    dealer = Dealer(company_id=company.id, name="Matru")
    db.add(dealer)
    await db.flush()
    invoice = Invoice(
        company_id=company.id,
        invoice_number="INV-1",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer.id,
        invoice_date=date(2026, 1, 1),
        due_date=date(2026, 1, 1),
        subtotal=Decimal("30000.00"),
        gst_amount=Decimal("0.00"),
        total_amount=Decimal("30000.00"),
        status=InvoiceStatus.Paid,
        source=InvoiceSource.csv_import,
    )
    db.add(invoice)
    await db.flush()
    db.add(
        Payment(
            company_id=company.id,
            invoice_id=invoice.id,
            amount=Decimal("30000.00"),
            payment_date=date(2026, 1, 15),
            source=PaymentSource.whatsapp,
        )
    )
    await db.commit()

    reply = await instant_reports.payments_reply(db, company)
    assert "30,000" in reply
    assert "INV-1" in reply
    assert "2026-01-15" in reply
