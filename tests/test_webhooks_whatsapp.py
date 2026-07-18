"""WhatsApp inbound webhook tests — Phase 7.

No X-API-Key involved — this endpoint has its own two security mechanisms
(hub.verify_token for GET, X-Hub-Signature-256 for POST), tested directly
against a plain (unauthenticated-by-admin-standards) client.

    uv run alembic upgrade head
    uv run pytest tests/test_webhooks_whatsapp.py -v
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import uuid
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from app.core.config import get_settings
from app.main import app
from app.models.business_event import BusinessEvent, BusinessEventType
from app.models.company import Company, FollowUpState, OnboardingState
from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceDirection, InvoiceSource, InvoiceStatus
from app.models.notification_log import NotificationLog
from app.services.whatsapp_client import WhatsAppNotConfiguredError, WhatsAppSendResult
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _unique_phone() -> str:
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


async def _make_company(
    db: AsyncSession, whatsapp_number: str, *, preferred_language: str = "en"
) -> uuid.UUID:
    company = Company(
        business_name="Webhook Test Co",
        owner_name="Owner",
        whatsapp_number=whatsapp_number,
        preferred_language=preferred_language,
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company.id


def _sign(body: bytes) -> str:
    secret = get_settings().whatsapp_app_secret
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _messages_payload(*, sender: str, message_type: str = "text", text: str = "hello") -> dict:
    message: dict = {
        "from": sender,
        "id": f"wamid.{uuid.uuid4().hex}",
        "timestamp": "1735689600",
        "type": message_type,
    }
    if message_type == "text":
        message["text"] = {"body": text}
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "waba-id",
                "changes": [{"value": {"messages": [message]}, "field": "messages"}],
            }
        ],
    }


def _interactive_reply_payload(
    *, sender: str, kind: str, reply_id: str, title: str = "Option"
) -> dict:
    """A tapped list row (kind="list_reply") or reply button (kind="button_reply")
    — matches Meta's inbound shape for an interactive tap, distinct from
    _messages_payload's plain-text shape.
    """
    message = {
        "from": sender,
        "id": f"wamid.{uuid.uuid4().hex}",
        "timestamp": "1735689600",
        "type": "interactive",
        "interactive": {"type": kind, kind: {"id": reply_id, "title": title}},
    }
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "waba-id",
                "changes": [{"value": {"messages": [message]}, "field": "messages"}],
            }
        ],
    }


def _statuses_payload(*, recipient: str, message_id: str, status: str = "delivered") -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "waba-id",
                "changes": [
                    {
                        "value": {
                            "statuses": [
                                {
                                    "id": message_id,
                                    "status": status,
                                    "timestamp": "1735689600",
                                    "recipient_id": recipient,
                                }
                            ]
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }


async def _anon_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ── GET verification ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_verification_succeeds_with_correct_token() -> None:
    settings = get_settings()
    async with await _anon_client() as client:
        resp = await client.get(
            "/webhooks/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": settings.whatsapp_verify_token,
                "hub.challenge": "challenge-123",
            },
        )
    assert resp.status_code == 200
    assert resp.text == "challenge-123"


@pytest.mark.asyncio
async def test_get_verification_rejects_wrong_token() -> None:
    async with await _anon_client() as client:
        resp = await client.get(
            "/webhooks/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "not-the-real-token",
                "hub.challenge": "challenge-123",
            },
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_verification_rejects_wrong_mode() -> None:
    settings = get_settings()
    async with await _anon_client() as client:
        resp = await client.get(
            "/webhooks/whatsapp",
            params={
                "hub.mode": "unsubscribe",
                "hub.verify_token": settings.whatsapp_verify_token,
                "hub.challenge": "challenge-123",
            },
        )
    assert resp.status_code == 403


# ── POST signature verification ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_post_missing_signature_returns_403() -> None:
    body = json.dumps(_messages_payload(sender="919999999999")).encode()
    async with await _anon_client() as client:
        resp = await client.post(
            "/webhooks/whatsapp", content=body, headers={"Content-Type": "application/json"}
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_post_invalid_signature_returns_403() -> None:
    body = json.dumps(_messages_payload(sender="919999999999")).encode()
    async with await _anon_client() as client:
        resp = await client.post(
            "/webhooks/whatsapp",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": "sha256=deadbeef"},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_post_valid_signature_unknown_sender_returns_200_and_writes_nothing(
    db: AsyncSession,
) -> None:
    # Use a freshly generated number, not a fixed literal — the dev DB this
    # test runs against has real pre-existing companies (e.g. a placeholder
    # number from the AP BIOCARE pilot data) that a hardcoded "obviously
    # fake" number could collide with.
    unknown_sender = _unique_phone().removeprefix("+")
    body = json.dumps(_messages_payload(sender=unknown_sender)).encode()
    async with await _anon_client() as client:
        resp = await client.post(
            "/webhooks/whatsapp",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(body)},
        )
    assert resp.status_code == 200

    event = await db.scalar(
        select(BusinessEvent).where(
            BusinessEvent.event_type == BusinessEventType.whatsapp_message_received,
            BusinessEvent.payload["from"].astext == f"+{unknown_sender}",
        )
    )
    assert event is None


# ── Message routing ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_text_message_from_known_company_writes_business_event(db: AsyncSession) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")  # Meta sends numbers without '+'

    body = json.dumps(
        _messages_payload(sender=bare_sender, message_type="text", text="Hello OpsGenie")
    ).encode()
    async with await _anon_client() as client:
        resp = await client.post(
            "/webhooks/whatsapp",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(body)},
        )
    assert resp.status_code == 200

    event = await db.scalar(
        select(BusinessEvent).where(
            BusinessEvent.company_id == company_id,
            BusinessEvent.event_type == BusinessEventType.whatsapp_message_received,
        )
    )
    assert event is not None
    assert event.payload["from"] == phone
    assert event.payload["type"] == "text"
    assert event.payload["text"] == "Hello OpsGenie"
    assert event.entity_type == "company"
    assert event.entity_id == company_id


@pytest.mark.asyncio
async def test_non_text_message_logs_type_with_empty_body(db: AsyncSession) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")

    body = json.dumps(_messages_payload(sender=bare_sender, message_type="image")).encode()
    async with await _anon_client() as client:
        resp = await client.post(
            "/webhooks/whatsapp",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(body)},
        )
    assert resp.status_code == 200

    event = await db.scalar(
        select(BusinessEvent).where(
            BusinessEvent.company_id == company_id,
            BusinessEvent.event_type == BusinessEventType.whatsapp_message_received,
        )
    )
    assert event is not None
    assert event.payload["type"] == "image"
    assert event.payload["text"] == ""


# ── Status routing ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_status_update_from_known_recipient_writes_business_event(
    db: AsyncSession,
) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_recipient = phone.removeprefix("+")
    message_id = f"wamid.{uuid.uuid4().hex}"

    body = json.dumps(
        _statuses_payload(recipient=bare_recipient, message_id=message_id, status="read")
    ).encode()
    async with await _anon_client() as client:
        resp = await client.post(
            "/webhooks/whatsapp",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(body)},
        )
    assert resp.status_code == 200

    event = await db.scalar(
        select(BusinessEvent).where(
            BusinessEvent.company_id == company_id,
            BusinessEvent.event_type == BusinessEventType.whatsapp_status_received,
        )
    )
    assert event is not None
    assert event.payload["message_id"] == message_id
    assert event.payload["status"] == "read"
    assert event.payload["recipient"] == phone


@pytest.mark.asyncio
async def test_status_update_unknown_recipient_returns_200_and_writes_nothing(
    db: AsyncSession,
) -> None:
    unknown_recipient = _unique_phone().removeprefix("+")
    body = json.dumps(
        _statuses_payload(recipient=unknown_recipient, message_id="wamid.unknown")
    ).encode()
    async with await _anon_client() as client:
        resp = await client.post(
            "/webhooks/whatsapp",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(body)},
        )
    assert resp.status_code == 200

    event = await db.scalar(
        select(BusinessEvent).where(
            BusinessEvent.event_type == BusinessEventType.whatsapp_status_received,
            BusinessEvent.payload["message_id"].astext == "wamid.unknown",
        )
    )
    assert event is None


# ── Numbered query menu (Phase 8) ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_menu_command_sends_reply_and_logs_traceable_notification(
    db: AsyncSession, monkeypatch
) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    # Not a fixed literal — the dev DB accumulates real rows across runs (see
    # the Phase 7 lesson above), and whatsapp_message_id is unique.
    fake_message_id = f"wamid.{uuid.uuid4().hex}"

    async def _fake_send(to: str, body: str) -> WhatsAppSendResult:
        assert to == phone
        return WhatsAppSendResult(message_id=fake_message_id)

    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_send)

    body = json.dumps(_messages_payload(sender=bare_sender, message_type="text", text="1")).encode()
    async with await _anon_client() as client:
        resp = await client.post(
            "/webhooks/whatsapp",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(body)},
        )
    assert resp.status_code == 200

    inbound_event = await db.scalar(
        select(BusinessEvent).where(
            BusinessEvent.company_id == company_id,
            BusinessEvent.event_type == BusinessEventType.whatsapp_message_received,
        )
    )
    assert inbound_event is not None

    log = await db.scalar(select(NotificationLog).where(NotificationLog.company_id == company_id))
    assert log is not None
    assert log.notification_type == "query_menu_cash"
    assert log.recipient_whatsapp == phone
    assert log.whatsapp_message_id == fake_message_id
    assert log.delivery_status == "sent"
    assert "Cash Position" in log.message_text

    reply_event = await db.scalar(
        select(BusinessEvent).where(
            BusinessEvent.company_id == company_id,
            BusinessEvent.event_type == BusinessEventType.whatsapp_reply_sent,
        )
    )
    assert reply_event is not None
    assert reply_event.payload["correlation_id"] == str(inbound_event.id)
    assert reply_event.payload["notification_log_id"] == str(log.id)
    assert reply_event.payload["whatsapp_message_id"] == fake_message_id
    assert reply_event.payload["command"] == "1"


# ── Instant command: on-demand morning briefing ────────────────────────────────


@pytest.mark.asyncio
async def test_morning_briefing_command_generates_when_none_exists_today(
    db: AsyncSession, monkeypatch
) -> None:
    """"give me my morning briefing" with no briefing generated yet today must
    generate one on the spot (same generate_briefing() the scheduler uses)
    and deliver it — not fall through to the LLM assistant, which has no
    matching tool and would just refuse.
    """
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")

    async def _fake_generate(db, company_id):
        from app.models.morning_briefing import MorningBriefing

        briefing = MorningBriefing(
            company_id=company_id,
            generated_text="Your fresh briefing text",
            snapshot_json={"cash_position": {}},
            confidence_score=Decimal("80.00"),
            data_freshness_hours=2,
        )
        db.add(briefing)
        await db.flush()
        return briefing

    sent: list[str] = []

    async def _fake_send(to: str, body: str) -> WhatsAppSendResult:
        sent.append(body)
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.api.webhooks.whatsapp.generate_briefing", _fake_generate)
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_send)

    body = json.dumps(
        _messages_payload(sender=bare_sender, text="give me my morning briefing")
    ).encode()
    async with await _anon_client() as client:
        resp = await client.post(
            "/webhooks/whatsapp",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(body)},
        )
    assert resp.status_code == 200
    assert sent == ["Your fresh briefing text"]

    from app.models.morning_briefing import MorningBriefing

    briefing = await db.scalar(
        select(MorningBriefing).where(MorningBriefing.company_id == company_id)
    )
    assert briefing is not None
    assert briefing.delivery_status == "sent"
    assert briefing.sent_at is not None


@pytest.mark.asyncio
async def test_morning_briefing_command_reuses_todays_briefing_without_regenerating(
    db: AsyncSession, monkeypatch
) -> None:
    """If the scheduler already generated (but hasn't necessarily delivered)
    today's briefing, asking for it must reuse that exact row — no second LLM
    call — and the reply marks it delivered so the scheduler doesn't skip a
    real send later thinking it already went out.
    """
    from app.models.morning_briefing import MorningBriefing

    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")

    existing = MorningBriefing(
        company_id=company_id,
        generated_text="Already generated by the scheduler",
        snapshot_json={"cash_position": {}},
        confidence_score=Decimal("90.00"),
        data_freshness_hours=1,
        delivery_status="failed_to_send",
    )
    db.add(existing)
    await db.commit()

    generate_calls: list[uuid.UUID] = []

    async def _fake_generate(db, company_id):
        generate_calls.append(company_id)
        raise AssertionError("generate_briefing must not be called when today's row exists")

    sent: list[str] = []

    async def _fake_send(to: str, body: str) -> WhatsAppSendResult:
        sent.append(body)
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.api.webhooks.whatsapp.generate_briefing", _fake_generate)
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_send)

    body = json.dumps(_messages_payload(sender=bare_sender, text="brief me")).encode()
    async with await _anon_client() as client:
        resp = await client.post(
            "/webhooks/whatsapp",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(body)},
        )
    assert resp.status_code == 200
    assert generate_calls == []
    assert sent == ["Already generated by the scheduler"]

    await db.refresh(existing)
    assert existing.delivery_status == "sent"
    assert existing.sent_at is not None


# ── Instant command: invoices ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_invoices_command_lists_all_deterministically(
    db: AsyncSession, monkeypatch
) -> None:
    """"invoices"/"recent invoices" must be an instant deterministic reply —
    never the LLM assistant — so it can't fail from a rate-limited provider
    or the money-safety guard rejecting a reply, and shows every real
    invoice on file rather than whatever the LLM chose to summarize.
    """
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    dealer = Dealer(company_id=company_id, name="Matru")
    db.add(dealer)
    await db.flush()
    db.add(
        Invoice(
            company_id=company_id,
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
            company_id=company_id,
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

    sent: list[str] = []

    async def _fake_send(to: str, body: str) -> WhatsAppSendResult:
        sent.append(body)
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_send)
    # If this ever fell through to the LLM assistant, this would raise —
    # proving the instant-command path is what actually answered.
    monkeypatch.setattr(
        "app.api.webhooks.whatsapp.answer_question",
        AsyncMock(side_effect=AssertionError("should not reach the LLM assistant")),
    )

    body = json.dumps(_messages_payload(sender=bare_sender, text="invoices")).encode()
    async with await _anon_client() as client:
        resp = await client.post(
            "/webhooks/whatsapp",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(body)},
        )
    assert resp.status_code == 200
    assert len(sent) == 1
    assert "INV-NEW" in sent[0]
    assert "INV-OLD" in sent[0]
    assert "Matru" in sent[0]
    assert "30,000" in sent[0]
    assert "50,000" in sent[0]


@pytest.mark.asyncio
async def test_invoices_command_no_invoices_yet(db: AsyncSession, monkeypatch) -> None:
    phone = _unique_phone()
    await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")

    sent: list[str] = []

    async def _fake_send(to: str, body: str) -> WhatsAppSendResult:
        sent.append(body)
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_send)

    body = json.dumps(_messages_payload(sender=bare_sender, text="recent invoices")).encode()
    async with await _anon_client() as client:
        resp = await client.post(
            "/webhooks/whatsapp",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(body)},
        )
    assert resp.status_code == 200
    assert "don't have any invoices" in sent[0].lower()


@pytest.mark.asyncio
async def test_report_menu_keywords_never_reach_the_llm_assistant(
    db: AsyncSession, monkeypatch
) -> None:
    """Every fixed, tappable menu-report keyword (Reports & Overview /
    Dealers & Suppliers / Inventory & Transactions rows) must resolve via
    _INSTANT_COMMANDS, never fall through to the LLM assistant — that's the
    whole point of making them deterministic (menu row ids match these
    keywords exactly, see app/api/webhooks/whatsapp.py's _MENU_MESSAGES).
    """
    phone = _unique_phone()
    await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")

    sent: list[str] = []

    async def _fake_send(to: str, body: str) -> WhatsAppSendResult:
        sent.append(body)
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_send)
    monkeypatch.setattr(
        "app.api.webhooks.whatsapp.answer_question",
        AsyncMock(side_effect=AssertionError("should not reach the LLM assistant")),
    )

    keywords = [
        "cash",
        "summary",
        "priorities",
        "overdue",
        "upcoming collections",
        "upcoming payments",
        "all dealers",
        "all suppliers",
        "top debtors",
        "top creditors",
        "inventory",
        "all inventory",
        "faq",
        "recent payments",
        "all payments",
        "all invoices",
    ]
    async with await _anon_client() as client:
        for keyword in keywords:
            body = json.dumps(_messages_payload(sender=bare_sender, text=keyword)).encode()
            resp = await client.post(
                "/webhooks/whatsapp",
                content=body,
                headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(body)},
            )
            assert resp.status_code == 200, keyword

    assert len(sent) == len(keywords)


# ── Deterministic prefix lookups: balance <name> / stock <item> / sell N of X ──


@pytest.mark.asyncio
async def test_balance_prefix_command_never_reaches_llm(db: AsyncSession, monkeypatch) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    dealer = Dealer(company_id=company_id, name="Ram Traders")
    db.add(dealer)
    await db.flush()
    db.add(
        Invoice(
            company_id=company_id,
            invoice_number="INV-BAL",
            direction=InvoiceDirection.receivable,
            dealer_id=dealer.id,
            invoice_date=date(2026, 1, 1),
            due_date=date(2026, 1, 1),
            subtotal=Decimal("25000.00"),
            gst_amount=Decimal("0.00"),
            total_amount=Decimal("25000.00"),
            status=InvoiceStatus.Pending,
            source=InvoiceSource.csv_import,
        )
    )
    await db.commit()

    sent: list[str] = []

    async def _fake_send(to: str, body: str) -> WhatsAppSendResult:
        sent.append(body)
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_send)
    monkeypatch.setattr(
        "app.api.webhooks.whatsapp.answer_question",
        AsyncMock(side_effect=AssertionError("should not reach the LLM assistant")),
    )

    body = json.dumps(_messages_payload(sender=bare_sender, text="balance Ram Traders")).encode()
    async with await _anon_client() as client:
        resp = await client.post(
            "/webhooks/whatsapp",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(body)},
        )
    assert resp.status_code == 200
    assert "Ram Traders" in sent[0]
    assert "25,000" in sent[0]


@pytest.mark.asyncio
async def test_stock_prefix_command_never_reaches_llm(db: AsyncSession, monkeypatch) -> None:
    from app.models.product import Product

    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    db.add(
        Product(
            company_id=company_id,
            name="Rice",
            unit="kg",
            selling_price=Decimal("400.00"),
            stock_quantity=Decimal("200"),
        )
    )
    await db.commit()

    sent: list[str] = []

    async def _fake_send(to: str, body: str) -> WhatsAppSendResult:
        sent.append(body)
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_send)
    monkeypatch.setattr(
        "app.api.webhooks.whatsapp.answer_question",
        AsyncMock(side_effect=AssertionError("should not reach the LLM assistant")),
    )

    body = json.dumps(_messages_payload(sender=bare_sender, text="stock rice")).encode()
    async with await _anon_client() as client:
        resp = await client.post(
            "/webhooks/whatsapp",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(body)},
        )
    assert resp.status_code == 200
    assert "Rice" in sent[0]
    assert "200 kg" in sent[0]


@pytest.mark.asyncio
async def test_sales_impact_fast_path_never_reaches_llm(db: AsyncSession, monkeypatch) -> None:
    from app.models.product import Product

    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    db.add(
        Product(
            company_id=company_id,
            name="Rice",
            unit="kg",
            selling_price=Decimal("400.00"),
            purchase_price=Decimal("300.00"),
            stock_quantity=Decimal("200"),
        )
    )
    await db.commit()

    sent: list[str] = []

    async def _fake_send(to: str, body: str) -> WhatsAppSendResult:
        sent.append(body)
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_send)
    monkeypatch.setattr(
        "app.api.webhooks.whatsapp.answer_question",
        AsyncMock(side_effect=AssertionError("should not reach the LLM assistant")),
    )

    body = json.dumps(
        _messages_payload(sender=bare_sender, text="if I sell 50 kg of rice")
    ).encode()
    async with await _anon_client() as client:
        resp = await client.post(
            "/webhooks/whatsapp",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(body)},
        )
    assert resp.status_code == 200
    assert "50 Rice" in sent[0]
    assert "150 left in stock" in sent[0]


@pytest.mark.asyncio
async def test_unresolvable_sales_impact_falls_back_to_llm(
    db: AsyncSession, monkeypatch
) -> None:
    """A parsed product name with no catalogue match must still reach the
    LLM assistant (the deterministic fast-path returns None, not a guess).
    """
    phone = _unique_phone()
    await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")

    async def _fake_send(to: str, body: str) -> WhatsAppSendResult:
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_send)
    fake_answer = AsyncMock(return_value="I don't have that product on file.")
    monkeypatch.setattr("app.api.webhooks.whatsapp.answer_question", fake_answer)

    body = json.dumps(
        _messages_payload(sender=bare_sender, text="if I sell 50 kg of quinoa")
    ).encode()
    async with await _anon_client() as client:
        resp = await client.post(
            "/webhooks/whatsapp",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(body)},
        )
    assert resp.status_code == 200
    fake_answer.assert_awaited_once()


# ── Instant command: /help ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_help_command_replies_with_command_guide(db: AsyncSession, monkeypatch) -> None:
    """"/help" (and its aliases) must be an instant deterministic reply — not
    routed to the LLM assistant, which has no fixed answer for "what can this
    bot do" and would risk inventing commands that don't exist.

    Every /slash_command mentioned in the reply is checked against the real
    registries (_WORKFLOW_START_TRIGGERS, _INSTANT_COMMANDS, menu_router) so
    the help text can't silently drift out of sync with what actually works.
    """
    import re

    from app.api.webhooks import whatsapp as webhook_module
    from app.services.query_menu import menu_router

    phone = _unique_phone()
    await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")

    sent: list[str] = []

    async def _fake_send(to: str, body: str) -> WhatsAppSendResult:
        sent.append(body)
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_send)

    body = json.dumps(_messages_payload(sender=bare_sender, text="/help")).encode()
    async with await _anon_client() as client:
        resp = await client.post(
            "/webhooks/whatsapp",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(body)},
        )
    assert resp.status_code == 200
    assert len(sent) == 1
    reply = sent[0]

    # (?<![\w]) so "in/out" doesn't false-positive-match "/out" as a command —
    # a real /slash_command is always preceded by whitespace, "(", or start.
    slash_commands = set(re.findall(r"(?<![\w])/[a-z_]+", reply))
    assert slash_commands, "expected at least one /slash_command in the help text"
    for command in slash_commands:
        assert (
            command in webhook_module._WORKFLOW_START_TRIGGERS
            or command in webhook_module._INSTANT_COMMANDS
            or menu_router.match(command) == command
        ), f"{command} is advertised in /help but isn't a registered command"


@pytest.mark.asyncio
async def test_help_command_aliases_all_reach_the_same_reply(
    db: AsyncSession, monkeypatch
) -> None:
    sent: list[str] = []

    async def _fake_send(to: str, body: str) -> WhatsAppSendResult:
        sent.append(body)
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_send)

    # "menu" is deliberately excluded — it sends a tappable interactive list
    # instead of this plain-text reply (see the "menu" tests below).
    for alias in ["help", "Help", "commands", "what can you do"]:
        phone = _unique_phone()
        await _make_company(db, phone)
        bare_sender = phone.removeprefix("+")
        body = json.dumps(_messages_payload(sender=bare_sender, text=alias)).encode()
        async with await _anon_client() as client:
            resp = await client.post(
                "/webhooks/whatsapp",
                content=body,
                headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(body)},
            )
        assert resp.status_code == 200

    assert len(sent) == 4
    assert len(set(sent)) == 1  # every alias produces the identical help text


# ── Slash-command aliases ────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "slash_command,phrase",
    [
        ("/add_product", "add product"),
        ("/delete_product", "delete product"),
        ("/update_product", "update product"),
        ("/update_price", "update price"),
        ("/update_purchase_price", "update purchase price"),
        ("/update_stock", "update stock"),
        ("/record_payment", "record payment"),
        ("/create_order", "create order"),
    ],
)
async def test_slash_workflow_trigger_matches_its_phrase_equivalent(
    db: AsyncSession, monkeypatch, slash_command: str, phrase: str
) -> None:
    """Each /slash_command in _WORKFLOW_START_TRIGGERS must start the exact
    same workflow (same opening question) as its natural-language phrase —
    it's a registry alias, not a separate code path.
    """
    sent: list[str] = []

    async def _fake_send(to: str, body: str) -> WhatsAppSendResult:
        sent.append(body)
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_send)

    async def _reply_for(text: str) -> str:
        phone = _unique_phone()
        await _make_company(db, phone)
        bare_sender = phone.removeprefix("+")
        body = json.dumps(_messages_payload(sender=bare_sender, text=text)).encode()
        async with await _anon_client() as client:
            resp = await client.post(
                "/webhooks/whatsapp",
                content=body,
                headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(body)},
            )
        assert resp.status_code == 200
        return sent[-1]

    slash_reply = await _reply_for(slash_command)
    phrase_reply = await _reply_for(phrase)
    assert slash_reply == phrase_reply


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "slash_command,digit",
    [("/cash", "1"), ("/collections", "2"), ("/suppliers", "3"), ("/dealer_risk", "4")],
)
async def test_slash_report_alias_matches_its_digit_equivalent(
    db: AsyncSession, monkeypatch, slash_command: str, digit: str
) -> None:
    """Each /slash_command registered on menu_router must return the exact
    same report as its digit shortcut."""
    sent: list[str] = []

    async def _fake_send(to: str, body: str) -> WhatsAppSendResult:
        sent.append(body)
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_send)

    async def _reply_for(text: str) -> str:
        phone = _unique_phone()
        await _make_company(db, phone)
        bare_sender = phone.removeprefix("+")
        body = json.dumps(_messages_payload(sender=bare_sender, text=text)).encode()
        async with await _anon_client() as client:
            resp = await client.post(
                "/webhooks/whatsapp",
                content=body,
                headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(body)},
            )
        assert resp.status_code == 200
        return sent[-1]

    slash_reply = await _reply_for(slash_command)
    digit_reply = await _reply_for(digit)
    assert slash_reply == digit_reply


# ── Tappable "menu" (WhatsApp interactive list) ──────────────────────────────


def test_menu_messages_stay_within_whatsapp_row_cap() -> None:
    """Meta caps a single interactive list message at 10 rows total across
    all sections — "menu" is split into multiple messages (_MENU_MESSAGES)
    specifically to cover everything without any one message overflowing.
    """
    from app.api.webhooks.whatsapp import _MENU_MESSAGES

    assert len(_MENU_MESSAGES) > 0
    for message in _MENU_MESSAGES:
        assert len(message["sections"]) <= 10
        total_rows = sum(len(section["rows"]) for section in message["sections"])
        assert total_rows <= 10


def test_menu_list_text_stays_within_whatsapp_character_limits() -> None:
    """Meta silently truncates (rather than errors) row titles/descriptions
    over its limits, so a violation here would ship a broken-looking menu
    instead of a loud failure — worth catching in CI.
    """
    from app.api.webhooks.whatsapp import _MENU_MESSAGES

    for message in _MENU_MESSAGES:
        for section in message["sections"]:
            assert len(section["title"]) <= 24
            for row in section["rows"]:
                assert len(row["id"]) <= 200
                assert len(row["title"]) <= 24
                assert len(row.get("description", "")) <= 72


def test_menu_row_ids_are_understood_by_the_dispatch_chain() -> None:
    """Every row's `id` is read back exactly like typed text (_extract_text_body),
    so it must either be a real registered /slash_command, or a bare keyword
    deliberately left for the free-form LLM assistant to interpret — never an
    id that collides with nothing and would confuse a tap into "just a
    question" the LLM has to guess at.
    """
    from app.api.webhooks import whatsapp as webhook_module
    from app.services.query_menu import menu_router

    for message in webhook_module._MENU_MESSAGES:
        for section in message["sections"]:
            for row in section["rows"]:
                row_id = row["id"]
                if row_id.startswith("/"):
                    assert (
                        row_id in webhook_module._WORKFLOW_START_TRIGGERS
                        or row_id in webhook_module._INSTANT_COMMANDS
                        or menu_router.match(row_id) == row_id
                    ), f"{row_id} is offered on the menu but isn't a registered command"


def test_menu_messages_localized_within_limits_all_locales() -> None:
    """The English-only limit checks above must hold for every localized menu
    too — Meta silently truncates over-limit titles/buttons, so a too-long
    Hindi/Odia label would ship a broken-looking menu. Guards the localized
    builder against overflow in any supported locale.
    """
    from app.api.webhooks.whatsapp import menu_messages
    from app.i18n import SUPPORTED_LOCALES

    for code in SUPPORTED_LOCALES:
        for message in menu_messages(code):
            assert len(message["button_text"]) <= 20, (code, message["button_text"])
            assert len(message["body"]) <= 1024, code
            assert len(message["sections"]) <= 10, code
            total_rows = sum(len(section["rows"]) for section in message["sections"])
            assert total_rows <= 10, code
            for section in message["sections"]:
                assert len(section["title"]) <= 24, (code, section["title"])
                for row in section["rows"]:
                    assert len(row["title"]) <= 24, (code, row["title"])
                    assert len(row.get("description", "")) <= 72, (code, row["description"])


def test_menu_row_ids_identical_across_locales() -> None:
    """Localizing the menu changes only the human-readable labels: the row
    `id`s (read back as commands) stay byte-identical in every locale, so a tap
    dispatches the same command regardless of the operator's language.
    """
    from app.api.webhooks.whatsapp import menu_messages
    from app.i18n import SUPPORTED_LOCALES

    def ids(code: str) -> list[str]:
        return [r["id"] for m in menu_messages(code) for s in m["sections"] for r in s["rows"]]

    en_ids = ids("en")
    assert en_ids
    for code in SUPPORTED_LOCALES:
        assert ids(code) == en_ids, f"{code} row ids diverged from English"


@pytest.mark.asyncio
@pytest.mark.parametrize("locale_code", ["hi-Deva", "hi-Latn", "or-Orya", "or-Latn"])
async def test_menu_trigger_localized_for_non_english_company(
    db: AsyncSession, monkeypatch, locale_code: str
) -> None:
    """A company in a non-English locale gets the interactive menu with its
    labels localized end-to-end (the webhook renders menu_messages() in the
    company's locale), while the delivered menu differs from the English one.
    """
    from app.api.webhooks.whatsapp import menu_messages

    phone = _unique_phone()
    await _make_company(db, phone, preferred_language=locale_code)
    bare_sender = phone.removeprefix("+")

    interactive_calls: list[dict] = []

    async def _fake_text_send(to: str, body: str) -> WhatsAppSendResult:
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    async def _fake_interactive_send(to: str, **kwargs) -> WhatsAppSendResult:
        interactive_calls.append(kwargs)
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_text_send)
    monkeypatch.setattr(
        "app.api.webhooks.whatsapp.send_interactive_list_message", _fake_interactive_send
    )

    body = json.dumps(_messages_payload(sender=bare_sender, text="menu")).encode()
    async with await _anon_client() as client:
        resp = await client.post(
            "/webhooks/whatsapp",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(body)},
        )
    assert resp.status_code == 200

    sent_sections = [call["sections"] for call in interactive_calls]
    # Exactly the localized menu for this company's locale went out …
    assert sent_sections == [m["sections"] for m in menu_messages(locale_code)]
    # … and it's genuinely localized (differs from the English menu).
    assert sent_sections != [m["sections"] for m in menu_messages("en")]


@pytest.mark.asyncio
@pytest.mark.parametrize("trigger", ["menu", "/menu", "Menu"])
async def test_menu_trigger_sends_interactive_list_not_plain_text(
    db: AsyncSession, monkeypatch, trigger: str
) -> None:
    from app.api.webhooks.whatsapp import _MENU_MESSAGES

    phone = _unique_phone()
    await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")

    text_sent: list[str] = []
    interactive_calls: list[dict] = []

    async def _fake_text_send(to: str, body: str) -> WhatsAppSendResult:
        text_sent.append(body)
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    async def _fake_interactive_send(to: str, **kwargs) -> WhatsAppSendResult:
        interactive_calls.append(kwargs)
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_text_send)
    monkeypatch.setattr(
        "app.api.webhooks.whatsapp.send_interactive_list_message", _fake_interactive_send
    )

    body = json.dumps(_messages_payload(sender=bare_sender, text=trigger)).encode()
    async with await _anon_client() as client:
        resp = await client.post(
            "/webhooks/whatsapp",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(body)},
        )
    assert resp.status_code == 200
    assert text_sent == []  # never fell back to plain text
    # One send per _MENU_MESSAGES entry — everything must actually go out.
    assert len(interactive_calls) == len(_MENU_MESSAGES)
    assert [call["sections"] for call in interactive_calls] == [
        m["sections"] for m in _MENU_MESSAGES
    ]


@pytest.mark.asyncio
async def test_tapped_list_reply_starts_the_same_workflow_as_typing_it(
    db: AsyncSession, monkeypatch
) -> None:
    """Tapping a list row must behave exactly like typing its `id` — proves
    the interactive-reply extraction wires into the real dispatch chain, not
    just a special-cased "menu" branch.
    """
    sent: list[str] = []

    async def _fake_send(to: str, body: str) -> WhatsAppSendResult:
        sent.append(body)
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_send)

    # Typed baseline.
    phone_a = _unique_phone()
    await _make_company(db, phone_a)
    body_a = json.dumps(
        _messages_payload(sender=phone_a.removeprefix("+"), text="/add_product")
    ).encode()
    async with await _anon_client() as client:
        resp = await client.post(
            "/webhooks/whatsapp",
            content=body_a,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(body_a)},
        )
    assert resp.status_code == 200
    typed_reply = sent[-1]

    # Tapped list row with the same id.
    phone_b = _unique_phone()
    await _make_company(db, phone_b)
    body_b = json.dumps(
        _interactive_reply_payload(
            sender=phone_b.removeprefix("+"),
            kind="list_reply",
            reply_id="/add_product",
            title="Add Product",
        )
    ).encode()
    async with await _anon_client() as client:
        resp = await client.post(
            "/webhooks/whatsapp",
            content=body_b,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(body_b)},
        )
    assert resp.status_code == 200
    tapped_reply = sent[-1]

    assert tapped_reply == typed_reply


@pytest.mark.asyncio
async def test_tapped_button_reply_routes_like_typed_text(db: AsyncSession, monkeypatch) -> None:
    sent: list[str] = []

    async def _fake_send(to: str, body: str) -> WhatsAppSendResult:
        sent.append(body)
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_send)

    phone = _unique_phone()
    await _make_company(db, phone)
    body = json.dumps(
        _interactive_reply_payload(
            sender=phone.removeprefix("+"), kind="button_reply", reply_id="/help", title="Help"
        )
    ).encode()
    async with await _anon_client() as client:
        resp = await client.post(
            "/webhooks/whatsapp",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(body)},
        )
    assert resp.status_code == 200

    from app.i18n import t

    # Help text is now catalog-driven; an English (default-locale) company gets
    # the English help block.
    assert sent == [t("menu.help_text", "en")]


@pytest.mark.asyncio
async def test_unmatched_text_routes_to_llm_assistant(db: AsyncSession, monkeypatch) -> None:
    # Free-form text (not 1-4, no active follow-up, onboarding completed) now
    # goes to the grounded LLM assistant. answer_question is stubbed so the test
    # never touches the network.
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")

    async def _fake_send(to: str, body: str) -> WhatsAppSendResult:
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    async def _fake_answer(db_, company, text) -> str:
        return f"Ram Traders owes you ₹42,000. (you asked: {text})"

    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_send)
    monkeypatch.setattr("app.api.webhooks.whatsapp.answer_question", _fake_answer)

    body = json.dumps(
        _messages_payload(sender=bare_sender, message_type="text", text="how much does ram owe")
    ).encode()
    async with await _anon_client() as client:
        resp = await client.post(
            "/webhooks/whatsapp",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(body)},
        )
    assert resp.status_code == 200

    log = await db.scalar(select(NotificationLog).where(NotificationLog.company_id == company_id))
    assert log is not None
    assert log.notification_type == "assistant"
    assert "Ram Traders owes you" in log.message_text

    inbound_event = await db.scalar(
        select(BusinessEvent).where(
            BusinessEvent.company_id == company_id,
            BusinessEvent.event_type == BusinessEventType.whatsapp_message_received,
        )
    )
    assert inbound_event is not None

    reply_event = await db.scalar(
        select(BusinessEvent).where(
            BusinessEvent.company_id == company_id,
            BusinessEvent.event_type == BusinessEventType.whatsapp_reply_sent,
        )
    )
    assert reply_event is not None
    assert reply_event.payload["command"] is None
    # This branch never calls build_snapshot (no incidental autoflush before
    # send), so it's the one that would silently write a null correlation_id
    # if the inbound event's id weren't explicitly flushed first.
    assert reply_event.payload["correlation_id"] == str(inbound_event.id)
    assert reply_event.payload["notification_log_id"] == str(log.id)


@pytest.mark.asyncio
async def test_send_failure_does_not_crash_webhook_and_records_failed_to_send(
    db: AsyncSession, monkeypatch
) -> None:
    """Whatever the reason send_text_message fails (unconfigured, network
    error, non-2xx from Meta), the webhook must swallow it — logged, never
    raised — so Meta still gets a 200. Forced via monkeypatch rather than
    relying on .env being unconfigured (real Meta credentials exist as of
    Phase 9).
    """

    async def _fake_send(to: str, body: str):
        raise WhatsAppNotConfiguredError("forced for this test")

    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_send)

    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")

    body = json.dumps(_messages_payload(sender=bare_sender, message_type="text", text="2")).encode()
    async with await _anon_client() as client:
        resp = await client.post(
            "/webhooks/whatsapp",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(body)},
        )
    assert resp.status_code == 200

    log = await db.scalar(select(NotificationLog).where(NotificationLog.company_id == company_id))
    assert log is not None
    assert log.delivery_status == "failed_to_send"
    assert log.whatsapp_message_id is None


@pytest.mark.asyncio
async def test_redelivered_message_is_not_reprocessed(db: AsyncSession, monkeypatch) -> None:
    """Meta's webhook delivery is at-least-once and retries aggressively on
    slow/non-2xx responses — posting the exact same Meta message id twice
    must not send (or log) a second reply.
    """
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")

    send_calls = []

    async def _fake_send(to: str, body: str) -> WhatsAppSendResult:
        send_calls.append(to)
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_send)

    body = json.dumps(_messages_payload(sender=bare_sender, message_type="text", text="1")).encode()
    headers = {"Content-Type": "application/json", "X-Hub-Signature-256": _sign(body)}
    async with await _anon_client() as client:
        first = await client.post("/webhooks/whatsapp", content=body, headers=headers)
        second = await client.post("/webhooks/whatsapp", content=body, headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert len(send_calls) == 1

    inbound_events = (
        await db.scalars(
            select(BusinessEvent).where(
                BusinessEvent.company_id == company_id,
                BusinessEvent.event_type == BusinessEventType.whatsapp_message_received,
            )
        )
    ).all()
    assert len(inbound_events) == 1

    logs = (
        await db.scalars(select(NotificationLog).where(NotificationLog.company_id == company_id))
    ).all()
    assert len(logs) == 1


@pytest.mark.asyncio
async def test_concurrent_redelivery_of_slow_reply_sends_only_one(
    db: AsyncSession, monkeypatch
) -> None:
    """test_redelivered_message_is_not_reprocessed above covers sequential
    redelivery (first request fully finishes before the second arrives).
    Meta's retries aren't guaranteed sequential — a reply slow enough (an LLM
    call, or "menu"'s 3 sends) can still be in flight when the retry lands,
    at which point the existing dedup check (looking for an already-*sent*
    reply) can't see anything yet and would let both process, sending two
    replies. The advisory lock in the webhook must make the second delivery
    block until the first actually finishes, then correctly see it as done.
    """
    phone = _unique_phone()
    await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")

    sent: list[str] = []
    call_count = 0

    async def _slow_then_fast_assistant(db, company, text) -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            await asyncio.sleep(0.3)  # simulate a slow LLM round-trip
        return "the answer"

    async def _fake_send(to: str, body: str) -> WhatsAppSendResult:
        sent.append(body)
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.api.webhooks.whatsapp.answer_question", _slow_then_fast_assistant)
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_send)

    payload = _messages_payload(sender=bare_sender, text="some free-form question")
    fixed_message_id = payload["entry"][0]["changes"][0]["value"]["messages"][0]["id"]
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json", "X-Hub-Signature-256": _sign(body)}

    async def _post():
        async with await _anon_client() as client:
            return await client.post("/webhooks/whatsapp", content=body, headers=headers)

    resp1, resp2 = await asyncio.gather(_post(), _post())
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert len(sent) == 1, f"expected exactly one reply for message {fixed_message_id}, got {sent}"


@pytest.mark.asyncio
async def test_crashed_reply_is_resumed_not_dropped(db: AsyncSession, monkeypatch) -> None:
    """The dedup claim (whatsapp_message_received row) is committed before
    the reply is generated/sent, so a redelivery arriving seconds later
    doesn't duplicate it. But if the *first* delivery then crashes before
    finishing — an uncaught error, or the process dying mid-request during a
    cold Render/Neon wake — the claim is committed with no reply yet. A
    later redelivery of that same message id must resume and actually send
    the reply, not skip it forever just because it was already claimed.
    """
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")

    call_count = 0

    async def _flaky_send(to: str, body: str) -> WhatsAppSendResult:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("simulated crash mid-send")
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _flaky_send)

    body = json.dumps(_messages_payload(sender=bare_sender, message_type="text", text="1")).encode()
    headers = {"Content-Type": "application/json", "X-Hub-Signature-256": _sign(body)}

    async with await _anon_client() as client:
        with pytest.raises(RuntimeError):
            await client.post("/webhooks/whatsapp", content=body, headers=headers)

        # Claim committed, no reply yet — exactly one inbound event, zero logs.
        inbound_events = (
            await db.scalars(
                select(BusinessEvent).where(
                    BusinessEvent.company_id == company_id,
                    BusinessEvent.event_type == BusinessEventType.whatsapp_message_received,
                )
            )
        ).all()
        assert len(inbound_events) == 1
        assert (
            await db.scalar(
                select(NotificationLog).where(NotificationLog.company_id == company_id)
            )
        ) is None

        second = await client.post("/webhooks/whatsapp", content=body, headers=headers)

    assert second.status_code == 200
    assert call_count == 2

    inbound_events = (
        await db.scalars(
            select(BusinessEvent).where(
                BusinessEvent.company_id == company_id,
                BusinessEvent.event_type == BusinessEventType.whatsapp_message_received,
            )
        )
    ).all()
    assert len(inbound_events) == 1  # still exactly one — resumed, not re-inserted

    logs = (
        await db.scalars(select(NotificationLog).where(NotificationLog.company_id == company_id))
    ).all()
    assert len(logs) == 1
    assert logs[0].delivery_status == "sent"


@pytest.mark.asyncio
async def test_status_webhook_updates_matching_notification_log_delivery_status(
    db: AsyncSession,
) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_recipient = phone.removeprefix("+")
    message_id = f"wamid.{uuid.uuid4().hex}"

    log = NotificationLog(
        company_id=company_id,
        notification_type="query_menu_cash",
        recipient_whatsapp=phone,
        message_text="some earlier reply",
        whatsapp_message_id=message_id,
        delivery_status="sent",
    )
    db.add(log)
    await db.commit()

    body = json.dumps(
        _statuses_payload(recipient=bare_recipient, message_id=message_id, status="delivered")
    ).encode()
    async with await _anon_client() as client:
        resp = await client.post(
            "/webhooks/whatsapp",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(body)},
        )
    assert resp.status_code == 200

    # The webhook updates this row through a *different* AsyncSession — this
    # test's own `db` session still has the old value cached in its identity
    # map for the same primary key, so a plain re-query wouldn't see the
    # change. Explicitly refresh from the database instead.
    await db.refresh(log)
    assert log.delivery_status == "delivered"


# ── Follow-up conversation takes priority over the numbered menu (Phase 9) ──


@pytest.mark.asyncio
async def test_reply_1_routes_to_pending_follow_up_not_the_menu(
    db: AsyncSession, monkeypatch
) -> None:
    """A bare "1" means something completely different mid-follow-up ("yes,
    paid in full") than as a menu command ("Cash Position") — this is the
    exact ambiguity Phase 9 introduced, and the follow-up check must win.
    """
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")

    dealer = Dealer(company_id=company_id, name="Ram Traders")
    db.add(dealer)
    await db.commit()
    await db.refresh(dealer)

    invoice = Invoice(
        company_id=company_id,
        invoice_number=f"INV-{uuid.uuid4().hex[:8]}",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer.id,
        invoice_date=date.today() - timedelta(days=30),
        due_date=date.today(),
        subtotal=Decimal("49350.00"),
        gst_amount=Decimal("0.00"),
        total_amount=Decimal("49350.00"),
        status=InvoiceStatus.Pending,
        source=InvoiceSource.csv_import,
    )
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)

    company = await db.get(Company, company_id)
    company.pending_follow_up_invoice_id = invoice.id
    company.pending_follow_up_state = FollowUpState.awaiting_confirmation
    await db.commit()

    async def _fake_send(to: str, body: str) -> WhatsAppSendResult:
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_send)

    body = json.dumps(_messages_payload(sender=bare_sender, message_type="text", text="1")).encode()
    async with await _anon_client() as client:
        resp = await client.post(
            "/webhooks/whatsapp",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(body)},
        )
    assert resp.status_code == 200

    log = await db.scalar(select(NotificationLog).where(NotificationLog.company_id == company_id))
    assert log is not None
    assert log.notification_type == "follow_up_reply"
    assert "closed" in log.message_text
    assert "Cash Position" not in log.message_text

    await db.refresh(invoice)
    assert invoice.status == InvoiceStatus.Paid
    await db.refresh(company)
    assert company.pending_follow_up_invoice_id is None


# ── Subscription gate (agent only replies to active subscribers) ──────────────


@pytest.mark.asyncio
async def test_inactive_subscription_logs_but_does_not_reply(db: AsyncSession, monkeypatch) -> None:
    phone = _unique_phone()
    company = Company(
        business_name="Pending Co",
        owner_name="Owner",
        whatsapp_number=phone,
        subscription_active=False,
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    company_id = company.id
    bare_sender = phone.removeprefix("+")

    sent = []

    async def _fake_send(to, body):
        sent.append(to)
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_send)

    body = json.dumps(_messages_payload(sender=bare_sender, message_type="text", text="1")).encode()
    async with await _anon_client() as client:
        resp = await client.post(
            "/webhooks/whatsapp",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(body)},
        )
    assert resp.status_code == 200

    # Inbound message IS logged...
    inbound = await db.scalar(
        select(BusinessEvent).where(
            BusinessEvent.company_id == company_id,
            BusinessEvent.event_type == BusinessEventType.whatsapp_message_received,
        )
    )
    assert inbound is not None
    # ...but NO reply was sent or logged.
    assert sent == []
    reply = await db.scalar(
        select(BusinessEvent).where(
            BusinessEvent.company_id == company_id,
            BusinessEvent.event_type == BusinessEventType.whatsapp_reply_sent,
        )
    )
    assert reply is None
    log = await db.scalar(select(NotificationLog).where(NotificationLog.company_id == company_id))
    assert log is None


# ── Onboarding routing (guided setup outranks menu + follow-up) ───────────────


@pytest.mark.asyncio
async def test_active_not_started_company_routes_to_onboarding(
    db: AsyncSession, monkeypatch
) -> None:
    phone = _unique_phone()
    company = Company(
        business_name="Ob Co",
        owner_name="Owner",
        whatsapp_number=phone,
        onboarding_state=OnboardingState.not_started,
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    company_id = company.id
    bare_sender = phone.removeprefix("+")

    async def _fake_send(to: str, body: str) -> WhatsAppSendResult:
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_send)

    # "1" would be the Cash Position menu command for a set-up company — here it
    # must instead kick off onboarding (menu never runs).
    body = json.dumps(_messages_payload(sender=bare_sender, text="1")).encode()
    async with await _anon_client() as client:
        resp = await client.post(
            "/webhooks/whatsapp",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(body)},
        )
    assert resp.status_code == 200

    log = await db.scalar(select(NotificationLog).where(NotificationLog.company_id == company_id))
    assert log is not None
    assert log.notification_type == "onboarding"
    await db.refresh(company)
    # Kickoff now asks language first (awaiting_language) before business setup.
    assert company.onboarding_state == OnboardingState.awaiting_language


@pytest.mark.asyncio
async def test_onboarding_outranks_pending_follow_up(db: AsyncSession, monkeypatch) -> None:
    phone = _unique_phone()
    company = Company(
        business_name="Ob Co",
        owner_name="Owner",
        whatsapp_number=phone,
        onboarding_state=OnboardingState.awaiting_business_type,
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    company_id = company.id
    bare_sender = phone.removeprefix("+")

    dealer = Dealer(company_id=company_id, name="Ram Traders")
    db.add(dealer)
    await db.commit()
    await db.refresh(dealer)
    invoice = Invoice(
        company_id=company_id,
        invoice_number=f"INV-{uuid.uuid4().hex[:8]}",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer.id,
        invoice_date=date.today() - timedelta(days=30),
        due_date=date.today(),
        subtotal=Decimal("49350.00"),
        gst_amount=Decimal("0.00"),
        total_amount=Decimal("49350.00"),
        status=InvoiceStatus.Pending,
        source=InvoiceSource.csv_import,
    )
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)
    company.pending_follow_up_invoice_id = invoice.id
    company.pending_follow_up_state = FollowUpState.awaiting_confirmation
    await db.commit()

    async def _fake_send(to: str, body: str) -> WhatsAppSendResult:
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_send)

    body = json.dumps(_messages_payload(sender=bare_sender, text="1")).encode()
    async with await _anon_client() as client:
        resp = await client.post(
            "/webhooks/whatsapp",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(body)},
        )
    assert resp.status_code == 200

    log = await db.scalar(select(NotificationLog).where(NotificationLog.company_id == company_id))
    assert log.notification_type == "onboarding"  # not "follow_up_reply"
    await db.refresh(invoice)
    assert invoice.status == InvoiceStatus.Pending  # follow-up did NOT run
    await db.refresh(company)
    assert company.pending_follow_up_invoice_id is not None  # follow-up untouched
