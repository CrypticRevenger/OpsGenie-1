"""Guided marketing broadcast workflow — full webhook walk.

Same conventions as tests/test_order_flow.py: real HMAC-signed POSTs against
the actual webhook endpoint. Two monkeypatched send points: the webhook's
own founder-facing replies (app.api.webhooks.whatsapp.send_text_message) and
the broadcast module's actual dealer-facing sends
(app.services.writes.broadcast.send_text_message/send_template_message).

    uv run alembic upgrade head
    uv run pytest tests/test_broadcast_flow.py -v
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from app.core.config import get_settings
from app.main import app
from app.models.business_event import BusinessEvent, BusinessEventType
from app.models.company import Company
from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceDirection, InvoiceSource, InvoiceStatus
from app.models.notification_log import NotificationLog
from app.models.pending_operation import PendingOperation
from app.services.whatsapp_client import WhatsAppSendResult
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _unique_phone() -> str:
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


async def _make_company(db: AsyncSession, whatsapp_number: str) -> uuid.UUID:
    company = Company(
        business_name="Broadcast Flow Test Co", owner_name="Owner", whatsapp_number=whatsapp_number
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company.id


async def _make_dealer(
    db: AsyncSession,
    company_id: uuid.UUID,
    name: str,
    *,
    phone: str | None = None,
    marketing_opt_in: bool = False,
) -> Dealer:
    dealer = Dealer(
        company_id=company_id, name=name, phone=phone, marketing_opt_in=marketing_opt_in
    )
    db.add(dealer)
    await db.commit()
    await db.refresh(dealer)
    return dealer


def _sign(body: bytes) -> str:
    secret = get_settings().whatsapp_app_secret
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _messages_payload(*, sender: str, text: str) -> dict:
    message = {
        "from": sender,
        "id": f"wamid.{uuid.uuid4().hex}",
        "timestamp": "1735689600",
        "type": "text",
        "text": {"body": text},
    }
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {"id": "waba-id", "changes": [{"value": {"messages": [message]}, "field": "messages"}]}
        ],
    }


async def _anon_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def _send(client: AsyncClient, sender: str, text: str) -> None:
    body = json.dumps(_messages_payload(sender=sender, text=text)).encode()
    resp = await client.post(
        "/webhooks/whatsapp",
        content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(body)},
    )
    assert resp.status_code == 200


def _fake_founder_sender(sent: list[str]):
    async def _fake_send(to: str, body: str) -> WhatsAppSendResult:
        sent.append(body)
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    return _fake_send


def _fake_broadcast_text_sender(calls: list[tuple[str, str]]):
    async def _fake_send(to: str, body: str) -> WhatsAppSendResult:
        calls.append((to, body))
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    return _fake_send


def _fake_broadcast_template_sender(calls: list[tuple[str, str]]):
    async def _fake_send(to, template_name, language_code, body_params=None, **kw):
        calls.append((to, (body_params or [None])[0]))
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    return _fake_send


@pytest.mark.asyncio
async def test_all_segment_zero_opted_in_exits_without_pending_operation(
    db: AsyncSession, monkeypatch
) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    await _make_dealer(db, company_id, "Not Opted Dealer", phone=_unique_phone())

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_founder_sender(sent))

    async with await _anon_client() as client:
        await _send(client, bare_sender, "broadcast")
        assert "who should get this broadcast" in sent[-1].lower()
        await _send(client, bare_sender, "all")
        assert "haven't opted" in sent[-1].lower() or "opted in" in sent[-1].lower()

    op = await db.scalar(select(PendingOperation).where(PendingOperation.company_id == company_id))
    assert op is None
    company = await db.get(Company, company_id)
    assert company.active_workflow is None


@pytest.mark.asyncio
async def test_all_segment_happy_path_only_reaches_opted_in_dealers(
    db: AsyncSession, monkeypatch
) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    opted_in = await _make_dealer(
        db, company_id, "Opted Dealer", phone=_unique_phone(), marketing_opt_in=True
    )
    await _make_dealer(db, company_id, "Not Opted Dealer", phone=_unique_phone())

    sent: list[str] = []
    broadcast_texts: list[tuple[str, str]] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_founder_sender(sent))
    monkeypatch.setattr(
        "app.services.writes.broadcast.send_text_message",
        _fake_broadcast_text_sender(broadcast_texts),
    )
    # Opted-in dealer is inside their 24h session window (has messaged
    # recently) -> free-form send_text_message, no template needed.
    db.add(
        BusinessEvent(
            company_id=company_id,
            event_type=BusinessEventType.whatsapp_message_received,
            entity_type="company",
            entity_id=company_id,
            payload={"from": opted_in.phone},
            created_by="test",
            created_at=datetime.now(UTC) - timedelta(hours=1),
        )
    )
    await db.commit()

    async with await _anon_client() as client:
        await _send(client, bare_sender, "broadcast")
        await _send(client, bare_sender, "all")
        assert "1 dealer" in sent[-1].lower() or "reach 1" in sent[-1].lower() or "1" in sent[-1]
        await _send(client, bare_sender, "Big sale this week!")
        assert "confirm" in sent[-1].lower() or "reply yes" in sent[-1].lower()
        await _send(client, bare_sender, "YES")
        assert "sent to 1" in sent[-1].lower()

    assert len(broadcast_texts) == 1
    assert broadcast_texts[0][0] == opted_in.phone
    assert broadcast_texts[0][1] == "Big sale this week!"

    logs = (
        (
            await db.execute(
                select(NotificationLog).where(
                    NotificationLog.company_id == company_id,
                    NotificationLog.notification_type == "marketing_broadcast",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(logs) == 1
    assert logs[0].delivery_status == "sent"

    event = await db.scalar(
        select(BusinessEvent).where(
            BusinessEvent.company_id == company_id,
            BusinessEvent.event_type == BusinessEventType.marketing_broadcast_sent,
        )
    )
    assert event is not None
    assert event.payload["sent"] == 1
    assert event.payload["failed"] == 0

    company = await db.get(Company, company_id)
    assert company.active_pending_operation_id is None


@pytest.mark.asyncio
async def test_overdue_segment_targets_only_overdue_opted_in_dealer(
    db: AsyncSession, monkeypatch
) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    overdue_dealer = await _make_dealer(
        db, company_id, "Overdue Dealer", phone=_unique_phone(), marketing_opt_in=True
    )
    current_dealer = await _make_dealer(
        db, company_id, "Current Dealer", phone=_unique_phone(), marketing_opt_in=True
    )
    db.add(
        Invoice(
            company_id=company_id,
            invoice_number="INV-OVERDUE-1",
            direction=InvoiceDirection.receivable,
            dealer_id=overdue_dealer.id,
            invoice_date=datetime.now(UTC).date() - timedelta(days=40),
            due_date=datetime.now(UTC).date() - timedelta(days=25),
            subtotal=Decimal("5000.00"),
            gst_amount=Decimal("0.00"),
            total_amount=Decimal("5000.00"),
            status=InvoiceStatus.Pending,
            source=InvoiceSource.csv_import,
        )
    )
    await db.commit()
    assert current_dealer.id  # not overdue, no invoice — sanity anchor

    sent: list[str] = []
    broadcast_texts: list[tuple[str, str]] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_founder_sender(sent))
    monkeypatch.setattr(
        "app.services.writes.broadcast.send_text_message",
        _fake_broadcast_text_sender(broadcast_texts),
    )
    db.add(
        BusinessEvent(
            company_id=company_id,
            event_type=BusinessEventType.whatsapp_message_received,
            entity_type="company",
            entity_id=company_id,
            payload={"from": overdue_dealer.phone},
            created_by="test",
            created_at=datetime.now(UTC) - timedelta(hours=1),
        )
    )
    await db.commit()

    async with await _anon_client() as client:
        await _send(client, bare_sender, "broadcast")
        await _send(client, bare_sender, "overdue")
        await _send(client, bare_sender, "Please clear your balance")
        await _send(client, bare_sender, "YES")

    assert len(broadcast_texts) == 1
    assert broadcast_texts[0][0] == overdue_dealer.phone


@pytest.mark.asyncio
async def test_specific_segment_matches_by_name_and_reports_unmatched(
    db: AsyncSession, monkeypatch
) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    matched = await _make_dealer(
        db, company_id, "Named Dealer", phone=_unique_phone(), marketing_opt_in=True
    )

    sent: list[str] = []
    broadcast_texts: list[tuple[str, str]] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_founder_sender(sent))
    monkeypatch.setattr(
        "app.services.writes.broadcast.send_text_message",
        _fake_broadcast_text_sender(broadcast_texts),
    )
    db.add(
        BusinessEvent(
            company_id=company_id,
            event_type=BusinessEventType.whatsapp_message_received,
            entity_type="company",
            entity_id=company_id,
            payload={"from": matched.phone},
            created_by="test",
            created_at=datetime.now(UTC) - timedelta(hours=1),
        )
    )
    await db.commit()

    async with await _anon_client() as client:
        await _send(client, bare_sender, "broadcast")
        await _send(client, bare_sender, "specific")
        assert "dealer name" in sent[-1].lower()
        await _send(client, bare_sender, "Named Dealer\nNo Such Dealer")
        assert "couldn't match" in sent[-1].lower()
        await _send(client, bare_sender, "Hello there")
        await _send(client, bare_sender, "YES")

    assert len(broadcast_texts) == 1
    assert broadcast_texts[0][0] == matched.phone


@pytest.mark.asyncio
async def test_specific_segment_no_names_match_cancels_without_pending_operation(
    db: AsyncSession, monkeypatch
) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    await _make_dealer(db, company_id, "Real Dealer", phone=_unique_phone(), marketing_opt_in=True)

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_founder_sender(sent))

    async with await _anon_client() as client:
        await _send(client, bare_sender, "broadcast")
        await _send(client, bare_sender, "specific")
        await _send(client, bare_sender, "Nonexistent Dealer")
        assert "couldn't match any" in sent[-1].lower()

    op = await db.scalar(select(PendingOperation).where(PendingOperation.company_id == company_id))
    assert op is None


@pytest.mark.asyncio
async def test_outside_session_window_uses_template_send(db: AsyncSession, monkeypatch) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    dealer = await _make_dealer(
        db, company_id, "Template Dealer", phone=_unique_phone(), marketing_opt_in=True
    )
    monkeypatch.setattr(get_settings(), "broadcast_template_name", "broadcast_tmpl")

    sent: list[str] = []
    text_calls: list[tuple[str, str]] = []
    template_calls: list[tuple[str, str]] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_founder_sender(sent))
    monkeypatch.setattr(
        "app.services.writes.broadcast.send_text_message",
        _fake_broadcast_text_sender(text_calls),
    )
    monkeypatch.setattr(
        "app.services.writes.broadcast.send_template_message",
        _fake_broadcast_template_sender(template_calls),
    )
    # No recent inbound BusinessEvent seeded -> dealer is outside the 24h
    # session window, must use the template path.

    async with await _anon_client() as client:
        await _send(client, bare_sender, "broadcast")
        await _send(client, bare_sender, "all")
        await _send(client, bare_sender, "Outside-session message")
        await _send(client, bare_sender, "YES")

    assert text_calls == []
    assert len(template_calls) == 1
    assert template_calls[0] == (dealer.phone, "Outside-session message")


@pytest.mark.asyncio
async def test_send_failure_for_one_dealer_does_not_abort_the_rest(
    db: AsyncSession, monkeypatch
) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    failing = await _make_dealer(
        db, company_id, "Failing Dealer", phone=_unique_phone(), marketing_opt_in=True
    )
    working = await _make_dealer(
        db, company_id, "Working Dealer", phone=_unique_phone(), marketing_opt_in=True
    )
    for dealer in (failing, working):
        db.add(
            BusinessEvent(
                company_id=company_id,
                event_type=BusinessEventType.whatsapp_message_received,
                entity_type="company",
                entity_id=company_id,
                payload={"from": dealer.phone},
                created_by="test",
                created_at=datetime.now(UTC) - timedelta(hours=1),
            )
        )
    await db.commit()

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_founder_sender(sent))

    from app.services.whatsapp_client import WhatsAppSendError

    async def _flaky_send(to: str, body: str) -> WhatsAppSendResult:
        if to == failing.phone:
            raise WhatsAppSendError("simulated Meta failure")
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.services.writes.broadcast.send_text_message", _flaky_send)

    async with await _anon_client() as client:
        await _send(client, bare_sender, "broadcast")
        await _send(client, bare_sender, "all")
        await _send(client, bare_sender, "Broadcast to everyone")
        await _send(client, bare_sender, "YES")
        assert "sent to 1" in sent[-1].lower()
        assert "1 failed" in sent[-1].lower() or "failed" in sent[-1].lower()

    logs = (
        (
            await db.execute(
                select(NotificationLog).where(
                    NotificationLog.company_id == company_id,
                    NotificationLog.notification_type == "marketing_broadcast",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(logs) == 2
    statuses = {log.recipient_whatsapp: log.delivery_status for log in logs}
    assert statuses[failing.phone] == "failed_to_send"
    assert statuses[working.phone] == "sent"


@pytest.mark.asyncio
async def test_cancel_at_segment_step(db: AsyncSession, monkeypatch) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_founder_sender(sent))

    async with await _anon_client() as client:
        await _send(client, bare_sender, "broadcast")
        await _send(client, bare_sender, "cancel")
        assert "cancel" in sent[-1].lower()

    company = await db.get(Company, company_id)
    assert company.active_workflow is None


@pytest.mark.asyncio
async def test_opt_in_all_dealers_bulk_flow(db: AsyncSession, monkeypatch) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    d1 = await _make_dealer(db, company_id, "Dealer One")
    d2 = await _make_dealer(db, company_id, "Dealer Two", marketing_opt_in=True)

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_founder_sender(sent))

    async with await _anon_client() as client:
        await _send(client, bare_sender, "opt in all dealers")
        assert "opt" in sent[-1].lower()
        await _send(client, bare_sender, "YES")
        assert "1" in sent[-1]

    await db.refresh(d1)
    await db.refresh(d2)
    assert d1.marketing_opt_in is True
    assert d2.marketing_opt_in is True
