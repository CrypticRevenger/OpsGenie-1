"""PendingOperation confirm-gate tests — Phase 2A.

uv run alembic upgrade head
uv run pytest tests/test_pending_operation.py -v
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from app.models.company import Company
from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceDirection, InvoiceSource, InvoiceStatus
from app.models.payment import Payment
from app.models.pending_operation import PendingOperation, PendingOperationType
from app.services.whatsapp_client import WhatsAppSendResult
from app.services.writes.pending_operation import (
    create_pending_operation,
    execute_pending_operation,
    get_pending_operation,
    handle_pending_operation_reply,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _unique_phone() -> str:
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


async def _make_company(db: AsyncSession) -> Company:
    company = Company(
        business_name="Pending Op Test Co", owner_name="Owner", whatsapp_number=_unique_phone()
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company


async def _make_dealer(db: AsyncSession, company_id: uuid.UUID, name: str) -> Dealer:
    dealer = Dealer(company_id=company_id, name=name)
    db.add(dealer)
    await db.commit()
    await db.refresh(dealer)
    return dealer


async def _make_invoice(
    db: AsyncSession,
    company_id: uuid.UUID,
    dealer_id: uuid.UUID,
    invoice_number: str,
    total_amount: Decimal,
) -> Invoice:
    invoice = Invoice(
        company_id=company_id,
        invoice_number=invoice_number,
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        invoice_date=date(2026, 1, 5),
        due_date=date(2026, 1, 5),
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


def _payment_payload(party_name: str, amount: Decimal, payment_date: date) -> dict:
    return {
        "direction": "receivable",
        "party_name": party_name,
        "amount": str(amount),
        "payment_date": payment_date.isoformat(),
    }


@pytest.mark.asyncio
async def test_create_pending_operation_sets_expiry_and_payload(db: AsyncSession) -> None:
    company = await _make_company(db)
    payload = _payment_payload("Ram Traders", Decimal("5000.00"), date(2026, 1, 10))

    before = datetime.now(UTC)
    op = await create_pending_operation(db, company, PendingOperationType.record_payment, payload)
    await db.commit()

    assert op.operation_type == PendingOperationType.record_payment
    assert op.payload == payload
    expected_expiry = before + timedelta(minutes=30)
    assert abs((op.expires_at - expected_expiry).total_seconds()) < 5
    assert company.active_pending_operation_id == op.id


@pytest.mark.asyncio
async def test_create_pending_operation_replaces_stale_one(db: AsyncSession) -> None:
    company = await _make_company(db)
    first = await create_pending_operation(
        db,
        company,
        PendingOperationType.record_payment,
        _payment_payload("A", Decimal("1"), date(2026, 1, 1)),
    )
    await db.commit()

    second = await create_pending_operation(
        db,
        company,
        PendingOperationType.record_payment,
        _payment_payload("B", Decimal("2"), date(2026, 1, 1)),
    )
    await db.commit()

    remaining = (
        (
            await db.execute(
                select(PendingOperation).where(PendingOperation.company_id == company.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(remaining) == 1
    assert remaining[0].id == second.id
    assert first.id != second.id
    assert company.active_pending_operation_id == second.id


@pytest.mark.asyncio
async def test_execute_pending_operation_success_deletes_row(db: AsyncSession) -> None:
    company = await _make_company(db)
    dealer = await _make_dealer(db, company.id, "Ram Traders")
    await _make_invoice(db, company.id, dealer.id, "INV-PO1", Decimal("10000.00"))

    op = await create_pending_operation(
        db,
        company,
        PendingOperationType.record_payment,
        _payment_payload("Ram Traders", Decimal("10000.00"), date(2026, 1, 10)),
    )
    await db.commit()

    reply = await execute_pending_operation(db, company, op)
    await db.commit()

    assert "recorded" in reply.lower()
    assert "INV-PO1" in reply

    remaining = await db.scalar(select(PendingOperation).where(PendingOperation.id == op.id))
    assert remaining is None
    assert company.active_pending_operation_id is None

    payment = await db.scalar(select(Payment).where(Payment.company_id == company.id))
    assert payment is not None
    assert payment.amount == Decimal("10000.00")


@pytest.mark.asyncio
async def test_execute_pending_operation_stale_outstanding_reraises_and_deletes(
    db: AsyncSession,
) -> None:
    """Money-safety property: the payload only ever stores what the user
    typed. If the party's real outstanding moved between preview and confirm
    (e.g. paid off through a different channel in the meantime), execute
    re-derives fresh and surfaces a clear error instead of silently
    committing a payment that no longer makes sense.
    """
    company = await _make_company(db)
    dealer = await _make_dealer(db, company.id, "Ganesh Store")
    invoice = await _make_invoice(db, company.id, dealer.id, "INV-PO2", Decimal("5000.00"))

    op = await create_pending_operation(
        db,
        company,
        PendingOperationType.record_payment,
        _payment_payload("Ganesh Store", Decimal("5000.00"), date(2026, 1, 10)),
    )
    await db.commit()

    # Simulate the invoice being paid off through a different channel while
    # this confirmation was in flight.
    invoice.status = InvoiceStatus.Paid
    await db.commit()

    reply = await execute_pending_operation(db, company, op)
    await db.commit()

    assert "couldn't record" in reply.lower()
    remaining = await db.scalar(select(PendingOperation).where(PendingOperation.id == op.id))
    assert remaining is None  # never left around for a stray retry
    assert company.active_pending_operation_id is None


@pytest.mark.asyncio
async def test_handle_pending_operation_reply_no_cancels_without_executing(
    db: AsyncSession,
) -> None:
    company = await _make_company(db)
    dealer = await _make_dealer(db, company.id, "Ram Traders")
    await _make_invoice(db, company.id, dealer.id, "INV-PO3", Decimal("10000.00"))

    op = await create_pending_operation(
        db,
        company,
        PendingOperationType.record_payment,
        _payment_payload("Ram Traders", Decimal("10000.00"), date(2026, 1, 10)),
    )
    await db.commit()

    reply = await handle_pending_operation_reply(db, company, op, "no")
    await db.commit()

    assert "cancelled" in reply.lower()
    remaining = await db.scalar(select(PendingOperation).where(PendingOperation.id == op.id))
    assert remaining is None
    assert company.active_pending_operation_id is None
    payment_count = len(
        (await db.execute(select(Payment).where(Payment.company_id == company.id))).scalars().all()
    )
    assert payment_count == 0


@pytest.mark.asyncio
async def test_handle_pending_operation_reply_unrecognized_reasks_without_deleting(
    db: AsyncSession,
) -> None:
    company = await _make_company(db)
    op = await create_pending_operation(
        db,
        company,
        PendingOperationType.record_payment,
        _payment_payload("Ram Traders", Decimal("10000.00"), date(2026, 1, 10)),
    )
    await db.commit()

    reply = await handle_pending_operation_reply(db, company, op, "maybe later")
    await db.commit()

    assert "yes" in reply.lower() and "no" in reply.lower()
    remaining = await db.scalar(select(PendingOperation).where(PendingOperation.id == op.id))
    assert remaining is not None  # still awaiting a real answer


@pytest.mark.asyncio
async def test_get_pending_operation_returns_even_expired(db: AsyncSession) -> None:
    company = await _make_company(db)
    op = await create_pending_operation(
        db,
        company,
        PendingOperationType.record_payment,
        _payment_payload("Ram Traders", Decimal("1000.00"), date(2026, 1, 10)),
    )
    op.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await db.commit()

    found = await get_pending_operation(db, company.active_pending_operation_id)
    assert found is not None
    assert found.id == op.id
    assert found.expires_at < datetime.now(UTC)  # caller's job to check + reject


@pytest.mark.asyncio
async def test_get_pending_operation_none_when_absent(db: AsyncSession) -> None:
    found = await get_pending_operation(db, uuid.uuid4())
    assert found is None


@pytest.mark.asyncio
async def test_broadcast_dealers_re_derives_recipients_fresh(
    db: AsyncSession, monkeypatch
) -> None:
    """Money/consent-safety property, same shape as the record_payment stale-
    outstanding test above: payload stores only the segment/dealer_ids
    filter criteria, never a resolved recipient list. If a dealer opts back
    out between confirm-creation and execution, they must be excluded from
    the actual send, not just from a stale preview count.
    """
    company = await _make_company(db)
    dealer = await _make_dealer(db, company.id, "Opt Flip Dealer")
    dealer.phone = _unique_phone()
    dealer.marketing_opt_in = True
    await db.commit()

    sent_calls: list[str] = []

    async def _fake_send(to: str, body: str) -> WhatsAppSendResult:
        sent_calls.append(to)
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.services.writes.broadcast.send_text_message", _fake_send)

    op = await create_pending_operation(
        db,
        company,
        PendingOperationType.broadcast_dealers,
        {"segment": "specific", "dealer_ids": [str(dealer.id)], "message": "Hello"},
    )
    await db.commit()

    # Opts back out while the confirmation is in flight.
    dealer.marketing_opt_in = False
    await db.commit()

    reply = await execute_pending_operation(db, company, op)
    await db.commit()

    assert "0 of 0" in reply.lower()
    assert sent_calls == []


@pytest.mark.asyncio
async def test_bulk_opt_in_dealers_execute_success(db: AsyncSession) -> None:
    company = await _make_company(db)
    dealer = await _make_dealer(db, company.id, "Bulk Opt Dealer")
    assert dealer.marketing_opt_in is False

    op = await create_pending_operation(db, company, PendingOperationType.bulk_opt_in_dealers, {})
    await db.commit()

    reply = await execute_pending_operation(db, company, op)
    await db.commit()

    assert "1" in reply
    await db.refresh(dealer)
    assert dealer.marketing_opt_in is True
    remaining = await db.scalar(select(PendingOperation).where(PendingOperation.id == op.id))
    assert remaining is None
