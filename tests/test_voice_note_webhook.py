"""Voice-note webhook handling — webhook-level walk through _handle_voice_note.

Same conventions as tests/test_order_flow_ocr.py: real HMAC-signed POSTs
against the actual webhook endpoint; send_text_message/download_media/
transcribe_voice_note are monkeypatched instead of hitting Meta or a real
audio-capable LLM provider.

Unlike the invoice-photo OCR path (scoped to one flow and gated on a "busy"
check first), a voice note is designed to be just another way to produce
`text` — it must resolve through the exact same onboarding/workflow/pending-
confirm/follow-up/menu/assistant priority ladder a typed message goes
through, not a separate simplified path. These tests prove that routing
directly, alongside the download/transcription failure fallbacks.

    uv run alembic upgrade head
    uv run pytest tests/test_voice_note_webhook.py -v
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from app.core.config import get_settings
from app.main import app
from app.models.company import Company, OnboardingState
from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceDirection, InvoiceSource, InvoiceStatus
from app.services.snapshot import business_now
from app.services.whatsapp_client import (
    WhatsAppMediaTooLargeError,
    WhatsAppSendError,
    WhatsAppSendResult,
)
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


def _unique_phone() -> str:
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


async def _make_company(db: AsyncSession, whatsapp_number: str) -> uuid.UUID:
    company = Company(
        business_name="Voice Note Test Co", owner_name="Owner", whatsapp_number=whatsapp_number
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company.id


def _sign(body: bytes) -> str:
    secret = get_settings().whatsapp_app_secret
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _audio_message(sender: str, media_id: str | None = "MEDIA1") -> dict:
    message: dict = {
        "from": sender,
        "id": f"wamid.{uuid.uuid4().hex}",
        "timestamp": "1735689600",
        "type": "audio",
    }
    if media_id is not None:
        message["audio"] = {"id": media_id, "mime_type": "audio/ogg; codecs=opus"}
    return message


def _text_message(sender: str, text: str) -> dict:
    return {
        "from": sender,
        "id": f"wamid.{uuid.uuid4().hex}",
        "timestamp": "1735689600",
        "type": "text",
        "text": {"body": text},
    }


def _payload(message: dict) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {"id": "waba-id", "changes": [{"value": {"messages": [message]}, "field": "messages"}]}
        ],
    }


async def _anon_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def _post(client: AsyncClient, message: dict) -> None:
    body = json.dumps(_payload(message)).encode()
    resp = await client.post(
        "/webhooks/whatsapp",
        content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(body)},
    )
    assert resp.status_code == 200


async def _send_text(client: AsyncClient, sender: str, text: str) -> None:
    await _post(client, _text_message(sender, text))


async def _send_voice_note(
    client: AsyncClient, sender: str, media_id: str | None = "MEDIA1"
) -> None:
    await _post(client, _audio_message(sender, media_id))


def _fake_sender(sent: list[str]):
    async def _fake_send(to: str, body: str) -> WhatsAppSendResult:
        sent.append(body)
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    return _fake_send


def _fake_downloader(calls: list[str] | None = None):
    async def _fake_download(media_id: str) -> tuple[bytes, str]:
        if calls is not None:
            calls.append(media_id)
        return b"fake-audio-bytes", "audio/ogg"

    return _fake_download


def _fake_transcriber(transcript: str | None):
    async def _fake_transcribe(audio_bytes: bytes, mime_type: str) -> str | None:
        return transcript

    return _fake_transcribe


@pytest.mark.asyncio
async def test_voice_note_happy_path_routes_through_the_same_ladder_as_typed_text(
    db: AsyncSession, monkeypatch
) -> None:
    """A voice note saying "record payment" must start the exact same guided
    workflow the typed keyword does — proving the transcript is fed through
    _handle_text_message, not some separate/simplified path.
    """
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")

    sent: list[str] = []
    download_calls: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))
    monkeypatch.setattr(
        "app.api.webhooks.whatsapp.download_media", _fake_downloader(download_calls)
    )
    monkeypatch.setattr(
        "app.api.webhooks.whatsapp.transcribe_voice_note",
        _fake_transcriber("record payment"),
    )

    async with await _anon_client() as client:
        await _send_voice_note(client, bare_sender)

    assert download_calls == ["MEDIA1"]
    assert len(sent) == 1
    # The transcript is echoed back ahead of the real reply, in one send.
    assert 'heard: "record payment"' in sent[0].lower()
    assert "who paid you" in sent[0].lower()  # payment.start prompt

    company = await db.get(Company, company_id)
    assert company.active_workflow is not None


@pytest.mark.asyncio
async def test_voice_note_resolves_onboarding_not_a_busy_gate(
    db: AsyncSession, monkeypatch
) -> None:
    """Unlike the invoice-photo OCR path, a voice note mid-onboarding must
    actually answer the onboarding question (via _handle_text_message)
    rather than get a canned "finish that first" reply — proving there is no
    separate busy-state gate for audio.
    """
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    company = await db.get(Company, company_id)
    company.onboarding_state = OnboardingState.not_started
    await db.commit()
    bare_sender = phone.removeprefix("+")

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))
    monkeypatch.setattr("app.api.webhooks.whatsapp.download_media", _fake_downloader())
    monkeypatch.setattr(
        "app.api.webhooks.whatsapp.transcribe_voice_note", _fake_transcriber("hello")
    )

    async with await _anon_client() as client:
        await _send_voice_note(client, bare_sender)

    assert 'heard: "hello"' in sent[-1].lower()
    assert "welcome to opsgenie" in sent[-1].lower()  # the real onboarding language prompt

    await db.refresh(company)  # this session's own `company` predates the webhook's commit
    assert company.onboarding_state == OnboardingState.awaiting_language


@pytest.mark.asyncio
async def test_voice_note_answers_a_yes_no_pending_confirmation(
    db: AsyncSession, monkeypatch
) -> None:
    """A spoken "yes" mid a pending money confirmation must confirm it
    exactly like typing YES would — the ladder, not a separate path, decides
    this. Ram Traders is pre-seeded with exactly one open invoice so
    "record payment" reaches the amount/date/YES-NO preview directly,
    without a detour through the new-party disambiguation questions.
    """
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    company = await db.get(Company, company_id)

    dealer = Dealer(company_id=company_id, name="Ram Traders")
    db.add(dealer)
    await db.flush()
    today = business_now(company.timezone).date()
    db.add(
        Invoice(
            company_id=company_id,
            invoice_number="INV-VOICE-1",
            direction=InvoiceDirection.receivable,
            dealer_id=dealer.id,
            invoice_date=today,
            due_date=today + timedelta(days=14),
            subtotal=Decimal("1500.00"),
            gst_amount=Decimal("0.00"),
            total_amount=Decimal("1500.00"),
            status=InvoiceStatus.Pending,
            source=InvoiceSource.csv_import,
        )
    )
    await db.commit()

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))
    monkeypatch.setattr("app.api.webhooks.whatsapp.download_media", _fake_downloader())

    async with await _anon_client() as client:
        await _send_text(client, bare_sender, "record payment")
        await _send_text(client, bare_sender, "Ram Traders")
        assert "how much did they pay you" in sent[-1].lower()

        await _send_text(client, bare_sender, "1500")
        assert "when was this paid" in sent[-1].lower()

        await _send_text(client, bare_sender, "today")
        # Reached the YES/NO confirmation preview at this point.
        assert "reply yes to record" in sent[-1].lower()

        monkeypatch.setattr(
            "app.api.webhooks.whatsapp.transcribe_voice_note", _fake_transcriber("yes")
        )
        await _send_voice_note(client, bare_sender)

    assert 'heard: "yes"' in sent[-1].lower()
    await db.refresh(company)
    assert company.active_pending_operation_id is None  # confirmed, not left dangling


@pytest.mark.asyncio
async def test_voice_note_download_failure_is_graceful(db: AsyncSession, monkeypatch) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))

    async def _fail_download(media_id: str) -> tuple[bytes, str]:
        raise WhatsAppSendError("simulated Graph API failure")

    monkeypatch.setattr("app.api.webhooks.whatsapp.download_media", _fail_download)

    async with await _anon_client() as client:
        await _send_voice_note(client, bare_sender)

    assert "couldn't download that voice note" in sent[-1].lower()
    company = await db.get(Company, company_id)
    assert company.active_workflow is None


@pytest.mark.asyncio
async def test_voice_note_too_large_is_graceful(db: AsyncSession, monkeypatch) -> None:
    phone = _unique_phone()
    await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))

    async def _too_large(media_id: str) -> tuple[bytes, str]:
        raise WhatsAppMediaTooLargeError("simulated oversize voice note")

    monkeypatch.setattr("app.api.webhooks.whatsapp.download_media", _too_large)

    async with await _anon_client() as client:
        await _send_voice_note(client, bare_sender)

    assert "couldn't download that voice note" in sent[-1].lower()


@pytest.mark.asyncio
async def test_voice_note_unreadable_transcription_is_graceful(
    db: AsyncSession, monkeypatch
) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")

    sent: list[str] = []
    download_calls: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))
    monkeypatch.setattr(
        "app.api.webhooks.whatsapp.download_media", _fake_downloader(download_calls)
    )
    monkeypatch.setattr(
        "app.api.webhooks.whatsapp.transcribe_voice_note", _fake_transcriber(None)
    )

    async with await _anon_client() as client:
        await _send_voice_note(client, bare_sender)

    assert download_calls == ["MEDIA1"]
    assert "couldn't understand that voice note" in sent[-1].lower()
    company = await db.get(Company, company_id)
    assert company.active_workflow is None


@pytest.mark.asyncio
async def test_voice_note_missing_media_id_is_graceful_and_skips_download(
    db: AsyncSession, monkeypatch
) -> None:
    phone = _unique_phone()
    await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")

    sent: list[str] = []
    download_calls: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))
    monkeypatch.setattr(
        "app.api.webhooks.whatsapp.download_media", _fake_downloader(download_calls)
    )

    async with await _anon_client() as client:
        await _send_voice_note(client, bare_sender, media_id=None)

    assert download_calls == []
    assert "couldn't understand that voice note" in sent[-1].lower()


@pytest.mark.asyncio
async def test_voice_note_menu_trigger_prepends_ack_to_first_list_message(
    db: AsyncSession, monkeypatch
) -> None:
    """The one case that produces an interactive batch instead of a single
    reply — the transcript acknowledgment must be folded into the first
    list message's body rather than sent as a separate message (see
    _handle_voice_note's own comment on why: a second _send_reply_and_log
    call would reintroduce a redelivery race).
    """
    phone = _unique_phone()
    await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")

    sent_interactive: list[dict] = []

    async def _fake_interactive_send(to: str, *, body: str, button_text: str, sections: list):
        sent_interactive.append({"body": body})
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    monkeypatch.setattr(
        "app.api.webhooks.whatsapp.send_interactive_list_message", _fake_interactive_send
    )
    monkeypatch.setattr("app.api.webhooks.whatsapp.download_media", _fake_downloader())
    monkeypatch.setattr(
        "app.api.webhooks.whatsapp.transcribe_voice_note", _fake_transcriber("menu")
    )

    async with await _anon_client() as client:
        await _send_voice_note(client, bare_sender)

    assert len(sent_interactive) >= 1
    assert 'heard: "menu"' in sent_interactive[0]["body"].lower()
