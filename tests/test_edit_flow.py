"""Guided "edit invoice" / "edit payment" workflows — safe cases only.

Drives app/services/workflows/edit_flow.py + the generic PendingOperation
confirm gate end-to-end, same lightweight convention as
tests/test_void_flow.py. Covers specifically the deliberate scope
boundaries: an invoice with any payment recorded is refused outright, and a
payment amount edit is bounds-checked against its own invoice only (never
spills to another invoice).

    uv run alembic upgrade head
    uv run pytest tests/test_edit_flow.py -v
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
from app.models.payment import Payment
from app.services.workflows.edit_flow import (
    handle_edit_invoice_workflow_message,
    handle_edit_payment_workflow_message,
    start_edit_invoice_workflow,
    start_edit_payment_workflow,
)
from app.services.writes.pending_operation import (
    get_pending_operation,
    handle_pending_operation_reply,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _unique_number() -> str:
    return f"+919{uuid.uuid4().int % 1_000_000_000:09d}"


async def _fresh_company(db: AsyncSession) -> Company:
    company = Company(
        business_name="Edit Flow Co",
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
        source=InvoiceSource.whatsapp,
    )
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)
    return invoice


async def _make_payment(
    db: AsyncSession, company_id: uuid.UUID, invoice_id: uuid.UUID, amount: Decimal
) -> Payment:
    payment = Payment(
        company_id=company_id, invoice_id=invoice_id, amount=amount, payment_date=date(2026, 1, 10)
    )
    db.add(payment)
    await db.commit()
    await db.refresh(payment)
    return payment


async def _confirm(db: AsyncSession, company: Company) -> str:
    op = await get_pending_operation(db, company.active_pending_operation_id)
    reply = await handle_pending_operation_reply(db, company, op, "YES")
    await db.commit()
    return reply


# ── Edit invoice ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_edit_invoice_not_found_reprompts(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    start_edit_invoice_workflow(company)
    reply = await handle_edit_invoice_workflow_message(db, company, "NOPE-123")
    assert "couldn't find" in reply.lower()
    assert company.active_workflow == "edit_invoice"


@pytest.mark.asyncio
async def test_edit_invoice_blocked_immediately_when_payment_exists(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    dealer = await _make_dealer(db, company.id)
    invoice = await _make_invoice(db, company.id, dealer.id, status=InvoiceStatus.Partially_Paid)
    await _make_payment(db, company.id, invoice.id, Decimal("100.00"))

    start_edit_invoice_workflow(company)
    reply = await handle_edit_invoice_workflow_message(db, company, invoice.invoice_number)

    assert "void" in reply.lower()
    assert company.active_workflow is None


@pytest.mark.asyncio
async def test_edit_invoice_amount_full_round_trip(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    dealer = await _make_dealer(db, company.id)
    invoice = await _make_invoice(db, company.id, dealer.id, total_amount=Decimal("1000.00"))

    start_edit_invoice_workflow(company)
    await handle_edit_invoice_workflow_message(db, company, invoice.invoice_number)
    await handle_edit_invoice_workflow_message(db, company, "amount")
    reply = await handle_edit_invoice_workflow_message(db, company, "1200")
    assert "1200" in reply or "1,200" in reply
    await handle_edit_invoice_workflow_message(db, company, "typo, was short")
    await db.commit()

    reply = await _confirm(db, company)
    assert "✅" in reply or "updated" in reply.lower()
    await db.refresh(invoice)
    assert invoice.total_amount == Decimal("1200.00")
    assert invoice.subtotal == Decimal("1200.00")

    event = await db.scalar(
        select(BusinessEvent).where(BusinessEvent.event_type == BusinessEventType.invoice_edited)
    )
    assert event is not None
    assert event.payload["field"] == "amount"
    assert event.payload["reason"] == "typo, was short"


@pytest.mark.asyncio
async def test_edit_invoice_amount_rejects_zero_or_negative(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    dealer = await _make_dealer(db, company.id)
    invoice = await _make_invoice(db, company.id, dealer.id)

    start_edit_invoice_workflow(company)
    await handle_edit_invoice_workflow_message(db, company, invoice.invoice_number)
    await handle_edit_invoice_workflow_message(db, company, "amount")
    reply = await handle_edit_invoice_workflow_message(db, company, "0")
    assert "greater than zero" in reply.lower()


@pytest.mark.asyncio
async def test_edit_invoice_date_full_round_trip(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    dealer = await _make_dealer(db, company.id)
    invoice = await _make_invoice(db, company.id, dealer.id)

    start_edit_invoice_workflow(company)
    await handle_edit_invoice_workflow_message(db, company, invoice.invoice_number)
    await handle_edit_invoice_workflow_message(db, company, "date")
    await handle_edit_invoice_workflow_message(db, company, "2026-02-01")
    await handle_edit_invoice_workflow_message(db, company, "skip")
    await db.commit()

    await _confirm(db, company)
    await db.refresh(invoice)
    assert invoice.invoice_date == date(2026, 2, 1)

    event = await db.scalar(
        select(BusinessEvent).where(BusinessEvent.event_type == BusinessEventType.invoice_edited)
    )
    assert event.payload["reason"] is None


@pytest.mark.asyncio
async def test_edit_invoice_party_reassignment_when_no_payments(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    old_dealer = await _make_dealer(db, company.id, name="Old Dealer")
    new_dealer = await _make_dealer(db, company.id, name="New Dealer")
    invoice = await _make_invoice(db, company.id, old_dealer.id)

    start_edit_invoice_workflow(company)
    await handle_edit_invoice_workflow_message(db, company, invoice.invoice_number)
    await handle_edit_invoice_workflow_message(db, company, "party")
    await handle_edit_invoice_workflow_message(db, company, "New Dealer")
    await handle_edit_invoice_workflow_message(db, company, "skip")
    await db.commit()

    await _confirm(db, company)
    await db.refresh(invoice)
    assert invoice.dealer_id == new_dealer.id


@pytest.mark.asyncio
async def test_edit_invoice_cancel_mid_flow(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    dealer = await _make_dealer(db, company.id)
    invoice = await _make_invoice(db, company.id, dealer.id)

    start_edit_invoice_workflow(company)
    await handle_edit_invoice_workflow_message(db, company, invoice.invoice_number)
    reply = await handle_edit_invoice_workflow_message(db, company, "cancel")
    assert "cancel" in reply.lower()
    assert company.active_workflow is None


# ── Edit payment ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_edit_payment_no_party_match(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    start_edit_payment_workflow(company)
    reply = await handle_edit_payment_workflow_message(db, company, "Nobody Inc")
    assert "couldn't find" in reply.lower()


@pytest.mark.asyncio
async def test_edit_payment_no_payments_for_party(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    await _make_dealer(db, company.id, name="Empty Traders")
    start_edit_payment_workflow(company)
    reply = await handle_edit_payment_workflow_message(db, company, "Empty Traders")
    assert "no payments" in reply.lower()
    assert company.active_workflow is None


@pytest.mark.asyncio
async def test_edit_payment_amount_full_round_trip(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    dealer = await _make_dealer(db, company.id)
    invoice = await _make_invoice(
        db, company.id, dealer.id, total_amount=Decimal("1000.00"), status=InvoiceStatus.Paid
    )
    payment = await _make_payment(db, company.id, invoice.id, Decimal("1000.00"))

    start_edit_payment_workflow(company)
    await handle_edit_payment_workflow_message(db, company, "Ram Traders")
    await handle_edit_payment_workflow_message(db, company, "1")
    await handle_edit_payment_workflow_message(db, company, "amount")
    await handle_edit_payment_workflow_message(db, company, "800")
    await handle_edit_payment_workflow_message(db, company, "skip")
    await db.commit()

    reply = await _confirm(db, company)
    assert "✅" in reply or "updated" in reply.lower()
    await db.refresh(payment)
    assert payment.amount == Decimal("800.00")
    await db.refresh(invoice)
    assert invoice.status == InvoiceStatus.Partially_Paid


@pytest.mark.asyncio
async def test_edit_payment_amount_blocked_when_it_would_overpay_invoice(
    db: AsyncSession,
) -> None:
    company = await _fresh_company(db)
    dealer = await _make_dealer(db, company.id)
    invoice = await _make_invoice(
        db, company.id, dealer.id, total_amount=Decimal("1000.00"), status=InvoiceStatus.Paid
    )
    await _make_payment(db, company.id, invoice.id, Decimal("400.00"))
    target = await _make_payment(db, company.id, invoice.id, Decimal("600.00"))

    start_edit_payment_workflow(company)
    await handle_edit_payment_workflow_message(db, company, "Ram Traders")
    # Two payments exist; pick whichever is listed first and try to raise it
    # past what the invoice can absorb (400 + 600 = 1000 already fully paid).
    await handle_edit_payment_workflow_message(db, company, "1")
    await handle_edit_payment_workflow_message(db, company, "amount")
    await handle_edit_payment_workflow_message(db, company, "900")
    await handle_edit_payment_workflow_message(db, company, "skip")
    await db.commit()

    reply = await _confirm(db, company)
    assert "overpay" in reply.lower()
    # Neither payment amount actually changed.
    await db.refresh(target)
    total_paid = (
        await db.execute(select(Payment.amount).where(Payment.invoice_id == invoice.id))
    ).scalars().all()
    assert sum(total_paid, Decimal("0.00")) == Decimal("1000.00")


@pytest.mark.asyncio
async def test_edit_payment_date_full_round_trip(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    dealer = await _make_dealer(db, company.id)
    invoice = await _make_invoice(db, company.id, dealer.id, status=InvoiceStatus.Partially_Paid)
    payment = await _make_payment(db, company.id, invoice.id, Decimal("100.00"))

    start_edit_payment_workflow(company)
    await handle_edit_payment_workflow_message(db, company, "Ram Traders")
    await handle_edit_payment_workflow_message(db, company, "1")
    await handle_edit_payment_workflow_message(db, company, "date")
    await handle_edit_payment_workflow_message(db, company, "2026-01-20")
    await handle_edit_payment_workflow_message(db, company, "skip")
    await db.commit()

    await _confirm(db, company)
    await db.refresh(payment)
    assert payment.payment_date == date(2026, 1, 20)
