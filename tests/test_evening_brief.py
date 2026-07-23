"""Evening Business Summary send tests.

Same convention as tests/test_daily_snapshot.py: live DB, unique company per
test. send_text_message is monkeypatched to capture the outbound text
instead of hitting Meta for real (same pattern as tests/test_scheduler.py).

    uv run alembic upgrade head
    uv run pytest tests/test_evening_brief.py -v
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from app.models.business_event import BusinessEvent, BusinessEventType
from app.models.company import Company
from app.models.daily_business_snapshot import DailyBusinessSnapshot
from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceDirection, InvoiceSource, InvoiceStatus
from app.models.invoice_item import InvoiceItem
from app.models.notification_log import NotificationLog
from app.models.product import Product
from app.services.evening_brief import evening_brief_delivered_today, send_evening_brief
from app.services.whatsapp_client import WhatsAppSendError, WhatsAppSendResult
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _unique_phone() -> str:
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


async def _make_company(db: AsyncSession) -> Company:
    company = Company(
        business_name="Evening Brief Test Co", owner_name="Owner", whatsapp_number=_unique_phone()
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company


def _fake_sender(sent: list[str]):
    async def _fake_send(to: str, body: str) -> WhatsAppSendResult:
        sent.append(body)
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    return _fake_send


@pytest.mark.asyncio
async def test_sends_and_finalizes_snapshot(db: AsyncSession, monkeypatch) -> None:
    company = await _make_company(db)
    sent: list[str] = []
    monkeypatch.setattr("app.services.evening_brief.send_text_message", _fake_sender(sent))

    result = await send_evening_brief(db, company)
    await db.commit()

    assert result is True
    assert len(sent) == 1
    text = sent[0]
    assert "Evening Business Summary" in text
    assert "Sales Today" in text
    assert "Sales Margin" in text
    assert "Collections" in text
    assert "Supplier Payments" in text
    assert "Net Cash Movement" in text
    assert "Outstanding Receivables" in text

    row = await db.scalar(
        select(DailyBusinessSnapshot).where(DailyBusinessSnapshot.company_id == company.id)
    )
    assert row is not None
    assert row.business_date == date.today()

    log = await db.scalar(
        select(NotificationLog).where(NotificationLog.company_id == company.id)
    )
    assert log is not None
    assert log.delivery_status == "sent"

    event = await db.scalar(
        select(BusinessEvent).where(
            BusinessEvent.company_id == company.id,
            BusinessEvent.event_type == BusinessEventType.evening_brief_sent,
        )
    )
    assert event is not None


@pytest.mark.asyncio
async def test_dedup_skips_second_send_same_day(db: AsyncSession, monkeypatch) -> None:
    company = await _make_company(db)
    sent: list[str] = []
    monkeypatch.setattr("app.services.evening_brief.send_text_message", _fake_sender(sent))

    first = await send_evening_brief(db, company)
    await db.commit()
    second = await send_evening_brief(db, company)
    await db.commit()

    assert first is True
    assert second is False
    assert len(sent) == 1  # only one real send


@pytest.mark.asyncio
async def test_priority_actions_included_when_present(db: AsyncSession, monkeypatch) -> None:
    """Cash deficit -> RecommendationEngine's cash_deficit_warning always
    fires -> "Priority Actions" section must appear (reusing the exact same
    engine the morning briefing/dashboard use, not new logic).
    """
    company = await _make_company(db)
    company.opening_balance = Decimal("-50000.00")  # forces a cash deficit
    await db.commit()

    sent: list[str] = []
    monkeypatch.setattr("app.services.evening_brief.send_text_message", _fake_sender(sent))

    await send_evening_brief(db, company)
    await db.commit()

    assert "Priority Actions" in sent[0]


@pytest.mark.asyncio
async def test_send_failure_still_finalizes_and_logs_failed_to_send(
    db: AsyncSession, monkeypatch
) -> None:
    async def _failing_send(to: str, body: str) -> WhatsAppSendResult:
        raise WhatsAppSendError("network error")

    monkeypatch.setattr("app.services.evening_brief.send_text_message", _failing_send)

    company = await _make_company(db)
    result = await send_evening_brief(db, company)
    await db.commit()

    assert result is False
    row = await db.scalar(
        select(DailyBusinessSnapshot).where(DailyBusinessSnapshot.company_id == company.id)
    )
    assert row is not None  # snapshot still finalized even though the send failed

    log = await db.scalar(
        select(NotificationLog).where(NotificationLog.company_id == company.id)
    )
    assert log.delivery_status == "failed_to_send"
    assert await evening_brief_delivered_today(db, company, date.today()) is False


@pytest.mark.asyncio
async def test_failed_send_retries_on_next_call(db: AsyncSession, monkeypatch) -> None:
    # Regression: the old dedup gate ("does a DailyBusinessSnapshot row exist
    # for today") tripped the moment finalize_daily_snapshot ran — before the
    # send was even attempted — so a failed send permanently blocked every
    # later retry for the rest of the day. The real gate now checks actual
    # delivery, so a subsequent call retries instead of silently no-op'ing.
    async def _failing_send(to: str, body: str) -> WhatsAppSendResult:
        raise WhatsAppSendError("network error")

    monkeypatch.setattr("app.services.evening_brief.send_text_message", _failing_send)
    company = await _make_company(db)
    first = await send_evening_brief(db, company)
    await db.commit()
    assert first is False

    sent: list[str] = []
    monkeypatch.setattr(
        "app.services.evening_brief.send_text_message", _fake_sender(sent)
    )
    second = await send_evening_brief(db, company)
    await db.commit()
    assert second is True
    assert len(sent) == 1
    assert await evening_brief_delivered_today(db, company, date.today()) is True


@pytest.mark.asyncio
async def test_margin_note_appears_when_items_missing_cost_data(
    db: AsyncSession, monkeypatch
) -> None:
    company = await _make_company(db)
    dealer = Dealer(company_id=company.id, name="Ram Traders")
    db.add(dealer)
    await db.flush()
    product = Product(company_id=company.id, name="Oil", selling_price=Decimal("50.00"))
    db.add(product)
    await db.flush()
    today = date.today()
    invoice = Invoice(
        company_id=company.id,
        invoice_number=f"WA-{uuid.uuid4().hex[:10]}",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer.id,
        invoice_date=today,
        due_date=today,
        subtotal=Decimal("500.00"),
        gst_amount=Decimal("0.00"),
        total_amount=Decimal("500.00"),
        status=InvoiceStatus.Pending,
        source=InvoiceSource.whatsapp,
    )
    db.add(invoice)
    await db.flush()
    db.add(
        InvoiceItem(
            invoice_id=invoice.id,
            product_id=product.id,
            description="Oil",
            quantity=Decimal("10"),
            unit_price=Decimal("50.00"),
            line_total=Decimal("500.00"),
        )
    )
    await db.commit()

    sent: list[str] = []
    monkeypatch.setattr("app.services.evening_brief.send_text_message", _fake_sender(sent))

    await send_evening_brief(db, company)
    await db.commit()

    assert "no cost price on file" in sent[0]
