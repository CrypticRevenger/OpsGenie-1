"""Invoice PDF delivery to a dealer's WhatsApp — V0.2.

    uv run alembic upgrade head
    uv run pytest tests/test_invoice_delivery.py -v
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from app.core.config import get_settings
from app.models.business_event import BusinessEvent, BusinessEventType
from app.models.company import Company
from app.models.notification_log import NotificationLog
from app.services.invoice_delivery import send_invoice_document
from app.services.whatsapp_client import WhatsAppSendResult
from app.services.writes.orders import CreateOrderResult, OrderLine
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _unique_phone() -> str:
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


async def _make_company(db: AsyncSession) -> Company:
    company = Company(
        business_name="Invoice Delivery Test Co",
        owner_name="Owner",
        whatsapp_number=_unique_phone(),
    )
    db.add(company)
    await db.flush()
    return company


def _make_result(*, dealer_phone: str | None) -> CreateOrderResult:
    return CreateOrderResult(
        invoice_id=uuid.uuid4(),
        invoice_number="WA-test123",
        invoice_date=date(2026, 7, 12),
        due_date=date(2026, 7, 26),
        dealer_id=uuid.uuid4(),
        dealer_name="Ram Traders",
        dealer_phone=dealer_phone,
        lines=[
            OrderLine(
                product_id=uuid.uuid4(),
                product_name="Rice",
                quantity=Decimal("10"),
                unit_price=Decimal("55.00"),
                line_total=Decimal("550.00"),
                gst_rate=Decimal("0.00"),
                gst_amount=Decimal("0.00"),
            )
        ],
        subtotal=Decimal("550.00"),
        gst_amount=Decimal("0.00"),
        total_amount=Decimal("550.00"),
        negative_stock_warnings=[],
    )


@pytest.mark.asyncio
async def test_skips_when_dealer_has_no_phone(db: AsyncSession) -> None:
    company = await _make_company(db)
    result = _make_result(dealer_phone=None)

    sent = await send_invoice_document(db, company, result, b"%PDF-fake")
    assert sent is False

    log = await db.scalar(
        select(NotificationLog).where(NotificationLog.company_id == company.id)
    )
    assert log is None


@pytest.mark.asyncio
async def test_skips_when_template_not_configured(db: AsyncSession, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "invoice_document_template_name", None)
    company = await _make_company(db)
    result = _make_result(dealer_phone=_unique_phone())

    sent = await send_invoice_document(db, company, result, b"%PDF-fake")
    assert sent is False

    log = await db.scalar(
        select(NotificationLog).where(NotificationLog.company_id == company.id)
    )
    assert log is None


@pytest.mark.asyncio
async def test_sends_via_template_and_logs_when_configured(
    db: AsyncSession, monkeypatch
) -> None:
    monkeypatch.setattr(get_settings(), "invoice_document_template_name", "invoice_doc")

    uploaded: dict = {}

    async def _fake_upload(file_bytes: bytes, filename: str, mime_type: str) -> str:
        uploaded["filename"] = filename
        uploaded["mime_type"] = mime_type
        return "media-id-123"

    sent_calls: list[dict] = []

    async def _fake_send_template(
        to: str,
        template_name: str,
        language_code: str,
        body_params=None,
        header_media_id=None,
        header_filename=None,
    ) -> WhatsAppSendResult:
        sent_calls.append(
            {
                "to": to,
                "template_name": template_name,
                "header_media_id": header_media_id,
                "header_filename": header_filename,
                "body_params": body_params,
            }
        )
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.services.invoice_delivery.upload_media", _fake_upload)
    monkeypatch.setattr("app.services.invoice_delivery.send_template_message", _fake_send_template)

    company = await _make_company(db)
    dealer_phone = _unique_phone()
    result = _make_result(dealer_phone=dealer_phone)

    sent = await send_invoice_document(db, company, result, b"%PDF-fake")
    assert sent is True
    assert sent_calls[0]["to"] == dealer_phone
    assert sent_calls[0]["template_name"] == "invoice_doc"
    assert sent_calls[0]["header_media_id"] == "media-id-123"
    assert uploaded["mime_type"] == "application/pdf"

    log = await db.scalar(
        select(NotificationLog).where(NotificationLog.company_id == company.id)
    )
    assert log is not None
    assert log.delivery_status == "sent"
    assert log.recipient_whatsapp == dealer_phone

    event = await db.scalar(
        select(BusinessEvent).where(
            BusinessEvent.company_id == company.id,
            BusinessEvent.event_type == BusinessEventType.invoice_document_sent,
        )
    )
    assert event is not None
    assert event.entity_id == result.invoice_id
