"""WhatsApp inbound webhook tests — Phase 7.

No X-API-Key involved — this endpoint has its own two security mechanisms
(hub.verify_token for GET, X-Hub-Signature-256 for POST), tested directly
against a plain (unauthenticated-by-admin-standards) client.

    uv run alembic upgrade head
    uv run pytest tests/test_webhooks_whatsapp.py -v
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from app.core.config import get_settings
from app.main import app
from app.models.business_event import BusinessEvent, BusinessEventType
from app.models.company import Company, FollowUpState
from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceDirection, InvoiceSource, InvoiceStatus
from app.models.notification_log import NotificationLog
from app.services.whatsapp_client import WhatsAppNotConfiguredError, WhatsAppSendResult
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _unique_phone() -> str:
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


async def _make_company(db: AsyncSession, whatsapp_number: str) -> uuid.UUID:
    company = Company(
        business_name="Webhook Test Co", owner_name="Owner", whatsapp_number=whatsapp_number
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


@pytest.mark.asyncio
async def test_unmatched_text_triggers_unknown_input_fallback(
    db: AsyncSession, monkeypatch
) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")

    async def _fake_send(to: str, body: str) -> WhatsAppSendResult:
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_send)

    body = json.dumps(
        _messages_payload(sender=bare_sender, message_type="text", text="what is my balance")
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
    assert log.notification_type == "whatsapp_unknown_input"
    assert "I didn't understand that." in log.message_text

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
