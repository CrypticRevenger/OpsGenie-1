"""Guided record-payment workflow — full webhook walk, Phase 2A.

Same conventions as tests/test_webhooks_whatsapp.py: real HMAC-signed POSTs
against the actual webhook endpoint, send_text_message monkeypatched to
capture outbound replies instead of hitting Meta for real.

    uv run alembic upgrade head
    uv run pytest tests/test_payment_flow.py -v
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import date
from decimal import Decimal

import pytest
from app.core.config import get_settings
from app.main import app
from app.models.business_event import BusinessEvent, BusinessEventType
from app.models.company import Company
from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceDirection, InvoiceSource, InvoiceStatus
from app.models.payment import Payment
from app.models.pending_operation import PendingOperation
from app.services.whatsapp_client import WhatsAppSendResult
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _unique_phone() -> str:
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


async def _make_company(db: AsyncSession, whatsapp_number: str) -> uuid.UUID:
    company = Company(
        business_name="Payment Flow Test Co", owner_name="Owner", whatsapp_number=whatsapp_number
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company.id


async def _make_dealer_with_invoice(
    db: AsyncSession, company_id: uuid.UUID, name: str, invoice_number: str, amount: Decimal
) -> None:
    dealer = Dealer(company_id=company_id, name=name)
    db.add(dealer)
    await db.flush()
    db.add(
        Invoice(
            company_id=company_id,
            invoice_number=invoice_number,
            direction=InvoiceDirection.receivable,
            dealer_id=dealer.id,
            invoice_date=date(2026, 1, 5),
            due_date=date(2026, 1, 5),
            subtotal=amount,
            gst_amount=Decimal("0.00"),
            total_amount=amount,
            status=InvoiceStatus.Pending,
            source=InvoiceSource.csv_import,
        )
    )
    await db.commit()


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
            {
                "id": "waba-id",
                "changes": [{"value": {"messages": [message]}, "field": "messages"}],
            }
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


@pytest.mark.asyncio
async def test_full_walk_existing_dealer_yes_commits(db: AsyncSession, monkeypatch) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    await _make_dealer_with_invoice(db, company_id, "Ram Traders", "INV-PF1", Decimal("10000.00"))

    sent: list[str] = []

    async def _fake_send(to: str, body: str) -> WhatsAppSendResult:
        sent.append(body)
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_send)

    async with await _anon_client() as client:
        await _send(client, bare_sender, "record payment")
        assert "who paid" in sent[-1].lower()

        # Known dealer -> direction inferred, no add-confirmation step.
        await _send(client, bare_sender, "Ram Traders")
        assert "how much" in sent[-1].lower()

        await _send(client, bare_sender, "not a number")
        assert "amount" in sent[-1].lower()
        assert len(sent) == 3  # re-asked, didn't advance

        await _send(client, bare_sender, "10000")
        assert "when was this paid" in sent[-1].lower()

        await _send(client, bare_sender, "today")
        assert "confirm" in sent[-1].lower()
        assert "10,000" in sent[-1]

        await _send(client, bare_sender, "YES")
        assert "recorded" in sent[-1].lower()
        assert "INV-PF1" in sent[-1]

    payment = await db.scalar(select(Payment).where(Payment.company_id == company_id))
    assert payment is not None
    assert payment.amount == Decimal("10000.00")
    remaining_op = await db.scalar(
        select(PendingOperation).where(PendingOperation.company_id == company_id)
    )
    assert remaining_op is None

    company = await db.get(Company, company_id)
    assert company.active_workflow is None
    assert company.workflow_scratch is None


@pytest.mark.asyncio
async def test_no_discards_pending_operation(db: AsyncSession, monkeypatch) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    await _make_dealer_with_invoice(db, company_id, "Ram Traders", "INV-PF2", Decimal("5000.00"))

    sent: list[str] = []

    async def _fake_send(to: str, body: str) -> WhatsAppSendResult:
        sent.append(body)
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_send)

    async with await _anon_client() as client:
        await _send(client, bare_sender, "record payment")
        await _send(client, bare_sender, "Ram Traders")
        await _send(client, bare_sender, "5000")
        await _send(client, bare_sender, "today")
        assert "confirm" in sent[-1].lower()

        await _send(client, bare_sender, "NO")
        assert "cancelled" in sent[-1].lower()

    payment_count = len(
        (await db.execute(select(Payment).where(Payment.company_id == company_id))).scalars().all()
    )
    assert payment_count == 0
    remaining_op = await db.scalar(
        select(PendingOperation).where(PendingOperation.company_id == company_id)
    )
    assert remaining_op is None


@pytest.mark.asyncio
async def test_unknown_party_explains_upfront_instead_of_guaranteed_fail(
    db: AsyncSession, monkeypatch
) -> None:
    """A party with no existing Dealer/Supplier row walks the "not on file"
    branch (dealer/supplier choice, then add-confirmation). A brand-new
    party has no invoice, so a payment against them can never actually be
    recorded — the flow says so immediately after the add-confirmation
    rather than asking amount/date toward a guaranteed failure, and doesn't
    create the party record for a payment that will never happen.
    """
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")

    sent: list[str] = []

    async def _fake_send(to: str, body: str) -> WhatsAppSendResult:
        sent.append(body)
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_send)

    async with await _anon_client() as client:
        await _send(client, bare_sender, "record payment")
        assert "who paid" in sent[-1].lower()

        await _send(client, bare_sender, "Brand New Traders")
        assert "don't have" in sent[-1].lower()
        assert "dealer" in sent[-1].lower() and "supplier" in sent[-1].lower()

        # Mid-flow "1" must be the dealer/supplier choice, never the Cash
        # Position menu command.
        await _send(client, bare_sender, "1")
        assert "add" in sent[-1].lower()
        assert "brand new traders" in sent[-1].lower()

        await _send(client, bare_sender, "yes")
        assert "existing invoice" in sent[-1].lower()

    remaining_op = await db.scalar(
        select(PendingOperation).where(PendingOperation.company_id == company_id)
    )
    assert remaining_op is None
    company = await db.get(Company, company_id)
    assert company.active_workflow is None  # not left stuck
    dealer = await db.scalar(
        select(Dealer).where(Dealer.company_id == company_id, Dealer.name == "Brand New Traders")
    )
    assert dealer is None  # no ghost record for a payment that can't happen


@pytest.mark.asyncio
async def test_cancel_works_at_every_step(db: AsyncSession, monkeypatch) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")

    sent: list[str] = []

    async def _fake_send(to: str, body: str) -> WhatsAppSendResult:
        sent.append(body)
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_send)

    async with await _anon_client() as client:
        await _send(client, bare_sender, "record payment")
        await _send(client, bare_sender, "Someone New")
        await _send(client, bare_sender, "cancel")
        assert "cancelled" in sent[-1].lower()

    company = await db.get(Company, company_id)
    assert company.active_workflow is None
    assert company.workflow_scratch is None


@pytest.mark.asyncio
async def test_keyword_trigger_is_traceable(db: AsyncSession, monkeypatch) -> None:
    """The keyword-triggered workflow start logs `command` on the outbound
    whatsapp_reply_sent event, same as a numbered-menu command — so it can
    be distinguished from an LLM-assistant fallback reply.
    """
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")

    async def _fake_send(to: str, body: str) -> WhatsAppSendResult:
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_send)

    async with await _anon_client() as client:
        await _send(client, bare_sender, "record payment")

    reply_event = await db.scalar(
        select(BusinessEvent).where(
            BusinessEvent.company_id == company_id,
            BusinessEvent.event_type == BusinessEventType.whatsapp_reply_sent,
        )
    )
    assert reply_event is not None
    assert reply_event.payload["command"] == "record payment"


@pytest.mark.asyncio
async def test_garbage_days_ago_reasked_not_crashed(db: AsyncSession, monkeypatch) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    await _make_dealer_with_invoice(db, company_id, "Ram Traders", "INV-PF3", Decimal("5000.00"))

    sent: list[str] = []

    async def _fake_send(to: str, body: str) -> WhatsAppSendResult:
        sent.append(body)
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_send)

    async with await _anon_client() as client:
        await _send(client, bare_sender, "record payment")
        await _send(client, bare_sender, "Ram Traders")
        await _send(client, bare_sender, "5000")
        # Garbage input at the date step must be re-asked, never a 500 (_send
        # already asserts status_code == 200).
        await _send(client, bare_sender, "800000 days ago")
        assert "didn't get that date" in sent[-1].lower()

        await _send(client, bare_sender, "today")
        assert "confirm" in sent[-1].lower()


@pytest.mark.asyncio
async def test_mid_flow_numeric_reply_not_swallowed_by_menu(db: AsyncSession, monkeypatch) -> None:
    """While a workflow is active, a bare "1" answers the current question
    (dealer/supplier choice here) — never the numbered-menu "Cash Position"
    command, same precedence guarantee the follow-up flow already has.
    """
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")

    sent: list[str] = []

    async def _fake_send(to: str, body: str) -> WhatsAppSendResult:
        sent.append(body)
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_send)

    async with await _anon_client() as client:
        await _send(client, bare_sender, "record payment")
        await _send(client, bare_sender, "Someone New")
        await _send(client, bare_sender, "1")

    assert "cash" not in sent[-1].lower()
    assert "add" in sent[-1].lower()

    company = await db.get(Company, company_id)
    assert company.active_workflow == "record_payment"
