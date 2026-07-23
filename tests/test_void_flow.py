"""Guided void-payment / void-order workflows — undo the single most-recently
WhatsApp-recorded payment or order.

Drives app/services/workflows/void_flow.py + the generic PendingOperation
confirm gate end-to-end (start -> reason -> YES), same lightweight
convention as tests/test_party_flow.py.

    uv run alembic upgrade head
    uv run pytest tests/test_void_flow.py -v
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from app.models.business_event import BusinessEvent, BusinessEventType
from app.models.company import Company, OnboardingState
from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceDirection, InvoiceSource, InvoiceStatus
from app.models.invoice_item import InvoiceItem
from app.models.payment import Payment, PaymentSource
from app.models.product import Product
from app.services.workflows.void_flow import (
    handle_void_order_workflow_message,
    handle_void_payment_workflow_message,
    start_void_order_workflow,
    start_void_payment_workflow,
)
from app.services.writes.pending_operation import handle_pending_operation_reply
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _unique_number() -> str:
    return f"+919{uuid.uuid4().int % 1_000_000_000:09d}"


async def _fresh_company(db: AsyncSession) -> Company:
    company = Company(
        business_name="Void Flow Co",
        owner_name="Owner",
        whatsapp_number=_unique_number(),
        subscription_active=True,
        onboarding_state=OnboardingState.completed,
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company


async def _make_dealer(
    db: AsyncSession, company_id: uuid.UUID, name: str = "Ram Traders"
) -> Dealer:
    dealer = Dealer(company_id=company_id, name=name)
    db.add(dealer)
    await db.commit()
    await db.refresh(dealer)
    return dealer


async def _make_invoice(
    db: AsyncSession,
    company_id: uuid.UUID,
    dealer_id: uuid.UUID,
    *,
    total_amount: Decimal = Decimal("1000.00"),
    status: InvoiceStatus = InvoiceStatus.Pending,
    source: InvoiceSource = InvoiceSource.whatsapp,
) -> Invoice:
    invoice = Invoice(
        company_id=company_id,
        invoice_number=f"WA-{uuid.uuid4().hex[:8]}",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        invoice_date=date(2026, 1, 5),
        due_date=date(2026, 1, 19),
        subtotal=total_amount,
        gst_amount=Decimal("0.00"),
        total_amount=total_amount,
        status=status,
        source=source,
    )
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)
    return invoice


async def _make_payment(
    db: AsyncSession,
    company_id: uuid.UUID,
    invoice_id: uuid.UUID,
    amount: Decimal,
    *,
    source: PaymentSource = PaymentSource.whatsapp,
) -> Payment:
    payment = Payment(
        company_id=company_id,
        invoice_id=invoice_id,
        amount=amount,
        payment_date=date(2026, 1, 10),
        source=source,
    )
    db.add(payment)
    await db.commit()
    await db.refresh(payment)
    return payment


async def _make_product(
    db: AsyncSession, company_id: uuid.UUID, *, stock: Decimal = Decimal("50")
) -> Product:
    product = Product(company_id=company_id, name="Widget", stock_quantity=stock)
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


# ── Void payment ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_void_payment_start_with_nothing_to_undo(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    reply = await start_void_payment_workflow(db, company)
    assert "no" in reply.lower()
    assert company.active_workflow is None


@pytest.mark.asyncio
async def test_void_payment_ignores_csv_imported_payments(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    dealer = await _make_dealer(db, company.id)
    invoice = await _make_invoice(db, company.id, dealer.id)
    await _make_payment(
        db, company.id, invoice.id, Decimal("500.00"), source=PaymentSource.csv_import
    )

    reply = await start_void_payment_workflow(db, company)
    assert "no" in reply.lower()
    assert company.active_workflow is None


@pytest.mark.asyncio
async def test_void_payment_start_sets_workflow_and_shows_preview(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    dealer = await _make_dealer(db, company.id)
    invoice = await _make_invoice(db, company.id, dealer.id, status=InvoiceStatus.Partially_Paid)
    await _make_payment(db, company.id, invoice.id, Decimal("500.00"))

    reply = await start_void_payment_workflow(db, company)
    assert company.active_workflow == "void_payment"
    assert "500" in reply
    assert invoice.invoice_number in reply
    assert "Ram Traders" in reply


@pytest.mark.asyncio
async def test_void_payment_cancel_clears_workflow_without_voiding(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    dealer = await _make_dealer(db, company.id)
    invoice = await _make_invoice(db, company.id, dealer.id, status=InvoiceStatus.Partially_Paid)
    await _make_payment(db, company.id, invoice.id, Decimal("500.00"))
    await start_void_payment_workflow(db, company)

    reply = await handle_void_payment_workflow_message(db, company, "cancel")
    await db.commit()

    assert "cancel" in reply.lower()
    assert company.active_workflow is None
    assert company.active_pending_operation_id is None


@pytest.mark.asyncio
async def test_void_payment_full_round_trip_partially_paid_invoice_reverts_to_pending(
    db: AsyncSession,
) -> None:
    company = await _fresh_company(db)
    dealer = await _make_dealer(db, company.id)
    invoice = await _make_invoice(
        db,
        company.id,
        dealer.id,
        total_amount=Decimal("1000.00"),
        status=InvoiceStatus.Partially_Paid,
    )
    payment = await _make_payment(db, company.id, invoice.id, Decimal("500.00"))

    await start_void_payment_workflow(db, company)
    reply = await handle_void_payment_workflow_message(db, company, "typo'd the amount")
    await db.commit()
    assert "YES" in reply

    op_id = company.active_pending_operation_id
    assert op_id is not None
    from app.services.writes.pending_operation import get_pending_operation

    op = await get_pending_operation(db, op_id)
    reply = await handle_pending_operation_reply(db, company, op, "YES")
    await db.commit()

    assert "voided" in reply.lower() or "✅" in reply
    assert (await db.get(Payment, payment.id)) is None
    await db.refresh(invoice)
    assert invoice.status == InvoiceStatus.Pending
    assert company.active_pending_operation_id is None

    event = await db.scalar(
        select(BusinessEvent).where(BusinessEvent.event_type == BusinessEventType.payment_voided)
    )
    assert event is not None
    assert event.payload["reason"] == "typo'd the amount"
    assert event.payload["amount"] == "500.00"


@pytest.mark.asyncio
async def test_void_payment_leaves_invoice_partially_paid_when_another_payment_remains(
    db: AsyncSession,
) -> None:
    company = await _fresh_company(db)
    dealer = await _make_dealer(db, company.id)
    invoice = await _make_invoice(
        db, company.id, dealer.id, total_amount=Decimal("1000.00"), status=InvoiceStatus.Paid
    )
    await _make_payment(db, company.id, invoice.id, Decimal("600.00"))
    newest = await _make_payment(db, company.id, invoice.id, Decimal("400.00"))

    await start_void_payment_workflow(db, company)
    await handle_void_payment_workflow_message(db, company, "skip")
    await db.commit()

    from app.services.writes.pending_operation import get_pending_operation

    op = await get_pending_operation(db, company.active_pending_operation_id)
    await handle_pending_operation_reply(db, company, op, "YES")
    await db.commit()

    assert (await db.get(Payment, newest.id)) is None
    await db.refresh(invoice)
    assert invoice.status == InvoiceStatus.Partially_Paid


# ── Void order ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_void_order_start_with_nothing_to_undo(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    reply = await start_void_order_workflow(db, company)
    assert "no" in reply.lower()
    assert company.active_workflow is None


@pytest.mark.asyncio
async def test_void_order_refuses_when_payment_already_recorded(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    dealer = await _make_dealer(db, company.id)
    invoice = await _make_invoice(db, company.id, dealer.id, status=InvoiceStatus.Partially_Paid)
    await _make_payment(db, company.id, invoice.id, Decimal("200.00"))

    reply = await start_void_order_workflow(db, company)
    assert "payment" in reply.lower()
    assert company.active_workflow is None


@pytest.mark.asyncio
async def test_void_order_full_round_trip_cancels_and_restores_stock(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    dealer = await _make_dealer(db, company.id)
    product = await _make_product(db, company.id, stock=Decimal("30"))
    invoice = await _make_invoice(db, company.id, dealer.id, total_amount=Decimal("500.00"))
    db.add(
        InvoiceItem(
            invoice_id=invoice.id,
            product_id=product.id,
            description=product.name,
            quantity=Decimal("10"),
            unit_price=Decimal("50.00"),
            line_total=Decimal("500.00"),
        )
    )
    await db.commit()

    await start_void_order_workflow(db, company)
    await handle_void_order_workflow_message(db, company, "skip")
    await db.commit()

    from app.services.writes.pending_operation import get_pending_operation

    op = await get_pending_operation(db, company.active_pending_operation_id)
    reply = await handle_pending_operation_reply(db, company, op, "YES")
    await db.commit()

    assert "voided" in reply.lower() or "✅" in reply
    await db.refresh(invoice)
    assert invoice.status == InvoiceStatus.Cancelled
    await db.refresh(product)
    assert product.stock_quantity == Decimal("40")

    event = await db.scalar(
        select(BusinessEvent).where(BusinessEvent.event_type == BusinessEventType.invoice_voided)
    )
    assert event is not None
    assert event.payload["reason"] is None


@pytest.mark.asyncio
async def test_void_order_cannot_be_repeated_on_an_already_cancelled_invoice(
    db: AsyncSession,
) -> None:
    """A second 'undo order' after the order is already voided must not find
    it again and double-restore stock — Invoice.status alone (Cancelled, no
    payment) used to still pass void_order's only guard (has_payment), so
    the still-most-recent-by-created_at Cancelled invoice kept getting
    re-voided, crediting stock back a second time."""
    company = await _fresh_company(db)
    dealer = await _make_dealer(db, company.id)
    product = await _make_product(db, company.id, stock=Decimal("30"))
    invoice = await _make_invoice(db, company.id, dealer.id, total_amount=Decimal("500.00"))
    db.add(
        InvoiceItem(
            invoice_id=invoice.id,
            product_id=product.id,
            description=product.name,
            quantity=Decimal("10"),
            unit_price=Decimal("50.00"),
            line_total=Decimal("500.00"),
        )
    )
    await db.commit()

    from app.services.writes.pending_operation import get_pending_operation

    await start_void_order_workflow(db, company)
    await handle_void_order_workflow_message(db, company, "skip")
    await db.commit()
    op = await get_pending_operation(db, company.active_pending_operation_id)
    await handle_pending_operation_reply(db, company, op, "YES")
    await db.commit()
    await db.refresh(product)
    assert product.stock_quantity == Decimal("40")

    # Second "undo order" — the invoice is still the company's most-recent
    # WhatsApp order by created_at, but it's already Cancelled.
    reply = await start_void_order_workflow(db, company)
    assert "no" in reply.lower()
    assert company.active_workflow is None

    await db.refresh(product)
    assert product.stock_quantity == Decimal("40")  # not double-restored


@pytest.mark.asyncio
async def test_void_order_write_service_refuses_an_already_cancelled_invoice(
    db: AsyncSession,
) -> None:
    """Defense-in-depth at the write-service layer itself (never trust the
    preview), independent of void_flow.py's own status filter above."""
    company = await _fresh_company(db)
    dealer = await _make_dealer(db, company.id)
    invoice = await _make_invoice(db, company.id, dealer.id, status=InvoiceStatus.Cancelled)

    from app.services.writes.void import void_order

    with pytest.raises(ValueError, match="already been voided"):
        await void_order(db, company, invoice_id=invoice.id, reason=None)


@pytest.mark.asyncio
async def test_void_order_ignores_csv_imported_invoices(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    dealer = await _make_dealer(db, company.id)
    await _make_invoice(db, company.id, dealer.id, source=InvoiceSource.csv_import)

    reply = await start_void_order_workflow(db, company)
    assert "no" in reply.lower()
