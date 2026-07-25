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


def _patch_upload(monkeypatch, media_id: str = "media-id-123") -> dict:
    uploaded: dict = {}

    async def _fake_upload(file_bytes: bytes, filename: str, mime_type: str) -> str:
        uploaded["filename"] = filename
        uploaded["mime_type"] = mime_type
        return media_id

    monkeypatch.setattr("app.services.invoice_delivery.upload_media", _fake_upload)
    return uploaded


def _patch_send_document(monkeypatch) -> list[dict]:
    calls: list[dict] = []

    async def _fake_send_document(to, media_id, filename, *, caption=None) -> WhatsAppSendResult:
        calls.append(
            {"to": to, "media_id": media_id, "filename": filename, "caption": caption}
        )
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.services.invoice_delivery.send_document_message", _fake_send_document)
    return calls


@pytest.mark.asyncio
async def test_no_phone_falls_back_to_founder_chat(db: AsyncSession, monkeypatch) -> None:
    """No dealer phone on file must not mean the PDF goes nowhere — it should
    land in the founder's own chat (company.whatsapp_number) so they can
    forward it manually.
    """
    _patch_upload(monkeypatch)
    document_calls = _patch_send_document(monkeypatch)

    company = await _make_company(db)
    result = _make_result(dealer_phone=None)

    delivery = await send_invoice_document(db, company, result, b"%PDF-fake")
    assert delivery.sent_to_dealer is False
    assert delivery.sent_to_founder is True
    assert document_calls[0]["to"] == company.whatsapp_number
    assert document_calls[0]["media_id"] == "media-id-123"

    # No phone on file means no recipient identity to log a dealer-attempt
    # against (recipient_whatsapp is NOT NULL) — only the founder-fallback
    # delivery is logged.
    dealer_log = await db.scalar(
        select(NotificationLog).where(
            NotificationLog.company_id == company.id,
            NotificationLog.notification_type == "invoice_document",
        )
    )
    assert dealer_log is None

    founder_log = await db.scalar(
        select(NotificationLog).where(
            NotificationLog.company_id == company.id,
            NotificationLog.notification_type == "invoice_document_founder_fallback",
        )
    )
    assert founder_log is not None
    assert founder_log.delivery_status == "sent"
    assert founder_log.recipient_whatsapp == company.whatsapp_number


@pytest.mark.asyncio
async def test_template_not_configured_falls_back_to_founder_chat(
    db: AsyncSession, monkeypatch
) -> None:
    monkeypatch.setattr(get_settings(), "invoice_document_template_name", None)
    _patch_upload(monkeypatch)
    document_calls = _patch_send_document(monkeypatch)

    company = await _make_company(db)
    result = _make_result(dealer_phone=_unique_phone())

    delivery = await send_invoice_document(db, company, result, b"%PDF-fake")
    assert delivery.sent_to_dealer is False
    assert delivery.sent_to_founder is True
    assert document_calls[0]["to"] == company.whatsapp_number


@pytest.mark.asyncio
async def test_upload_failure_leaves_nobody_with_the_pdf(db: AsyncSession) -> None:
    """No mocking at all here — upload_media hits the (test-env-blanked)
    WhatsApp credentials and raises WhatsAppNotConfiguredError immediately.
    Neither the dealer nor the founder-fallback can be attempted, and (unlike
    a real attempted-and-failed send) nothing is logged — no attempt was
    actually made.
    """
    company = await _make_company(db)
    result = _make_result(dealer_phone=None)

    delivery = await send_invoice_document(db, company, result, b"%PDF-fake")
    assert delivery.sent_to_dealer is False
    assert delivery.sent_to_founder is False

    log = await db.scalar(
        select(NotificationLog).where(NotificationLog.company_id == company.id)
    )
    assert log is None


@pytest.mark.asyncio
async def test_sends_via_template_and_logs_when_configured(
    db: AsyncSession, monkeypatch
) -> None:
    """A reachable dealer (phone on file + template configured) now gets the
    PDF *in addition to* the founder, not instead of them — the founder
    always gets their own copy of every invoice (see invoice_delivery.py's
    module docstring for why this changed from a founder-fallback-only
    design).
    """
    monkeypatch.setattr(get_settings(), "invoice_document_template_name", "invoice_doc")

    uploaded = _patch_upload(monkeypatch)
    document_calls = _patch_send_document(monkeypatch)

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

    monkeypatch.setattr("app.services.invoice_delivery.send_template_message", _fake_send_template)

    company = await _make_company(db)
    dealer_phone = _unique_phone()
    result = _make_result(dealer_phone=dealer_phone)

    delivery = await send_invoice_document(db, company, result, b"%PDF-fake")
    assert delivery.sent_to_dealer is True
    assert delivery.sent_to_founder is True
    assert sent_calls[0]["to"] == dealer_phone
    assert sent_calls[0]["template_name"] == "invoice_doc"
    assert sent_calls[0]["header_media_id"] == "media-id-123"
    assert uploaded["mime_type"] == "application/pdf"
    assert document_calls[0]["to"] == company.whatsapp_number

    dealer_log = await db.scalar(
        select(NotificationLog).where(
            NotificationLog.company_id == company.id,
            NotificationLog.notification_type == "invoice_document",
        )
    )
    assert dealer_log is not None
    assert dealer_log.delivery_status == "sent"
    assert dealer_log.recipient_whatsapp == dealer_phone

    founder_log = await db.scalar(
        select(NotificationLog).where(
            NotificationLog.company_id == company.id,
            NotificationLog.notification_type == "invoice_document_founder_fallback",
        )
    )
    assert founder_log is not None
    assert founder_log.delivery_status == "sent"
    assert founder_log.recipient_whatsapp == company.whatsapp_number

    event = await db.scalar(
        select(BusinessEvent).where(
            BusinessEvent.company_id == company.id,
            BusinessEvent.event_type == BusinessEventType.invoice_document_sent,
        )
    )
    assert event is not None
    assert event.entity_id == result.invoice_id
