"""Invoice-photo OCR pre-fill — webhook-level walk through the create_order
flow when it's triggered by a photo instead of "new order". Same conventions
as tests/test_order_flow.py: real HMAC-signed POSTs against the actual
webhook endpoint; send_text_message/download_media/extract_invoice_from_image
are monkeypatched instead of hitting Meta or a real vision provider.

    uv run alembic upgrade head
    uv run pytest tests/test_order_flow_ocr.py -v
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
from app.models.pending_operation import PendingOperationType
from app.models.product import Product
from app.services.invoice_ocr import ExtractedInvoice, ExtractedItem, FieldGuess
from app.services.snapshot import business_now
from app.services.whatsapp_client import WhatsAppSendError, WhatsAppSendResult
from app.services.writes.pending_operation import create_pending_operation
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _unique_phone() -> str:
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


async def _make_company(db: AsyncSession, whatsapp_number: str) -> uuid.UUID:
    company = Company(
        business_name="Order Flow OCR Test Co",
        owner_name="Owner",
        whatsapp_number=whatsapp_number,
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company.id


async def _make_dealer(db: AsyncSession, company_id: uuid.UUID, name: str) -> uuid.UUID:
    dealer = Dealer(company_id=company_id, name=name)
    db.add(dealer)
    await db.commit()
    await db.refresh(dealer)
    return dealer.id


async def _make_product(
    db: AsyncSession, company_id: uuid.UUID, name: str, *, selling_price: Decimal | None = None
) -> uuid.UUID:
    product = Product(
        company_id=company_id, name=name, selling_price=selling_price, stock_quantity=Decimal("0")
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product.id


def _sign(body: bytes) -> str:
    secret = get_settings().whatsapp_app_secret
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _text_message(sender: str, text: str) -> dict:
    return {
        "from": sender,
        "id": f"wamid.{uuid.uuid4().hex}",
        "timestamp": "1735689600",
        "type": "text",
        "text": {"body": text},
    }


def _image_message(sender: str, media_id: str) -> dict:
    return {
        "from": sender,
        "id": f"wamid.{uuid.uuid4().hex}",
        "timestamp": "1735689600",
        "type": "image",
        "image": {"id": media_id, "mime_type": "image/jpeg"},
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


async def _send_photo(client: AsyncClient, sender: str, media_id: str = "MEDIA1") -> None:
    await _post(client, _image_message(sender, media_id))


def _fake_sender(sent: list[str]):
    async def _fake_send(to: str, body: str) -> WhatsAppSendResult:
        sent.append(body)
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    return _fake_send


def _guess(value: str | None, confidence: float = 0.9) -> FieldGuess:
    return FieldGuess(value=value, confidence=confidence)


def _fake_downloader(calls: list[str] | None = None):
    async def _fake_download(media_id: str) -> tuple[bytes, str]:
        if calls is not None:
            calls.append(media_id)
        return b"fake-image-bytes", "image/jpeg"

    return _fake_download


def _fake_extractor(extraction: ExtractedInvoice | None):
    async def _fake_extract(image_bytes: bytes, mime_type: str) -> ExtractedInvoice | None:
        return extraction

    return _fake_extract


@pytest.mark.asyncio
async def test_ocr_happy_path_full_flow(db: AsyncSession, monkeypatch) -> None:
    """Dealer + a brand-new product, every field above the confidence
    threshold — exercises the dealer suggestion, the product-name suggestion
    (via the new-product-confirm step), the price suggestion, and the
    quantity suggestion, ending in a real Invoice matching the manually-typed
    equivalent (tests/test_order_flow.py's own happy path).
    """
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    await _make_dealer(db, company_id, "Ram Traders")

    extraction = ExtractedInvoice(
        is_invoice=True,
        invoice_number=_guess("INV-1047", 0.8),
        dealer_name=_guess("Ram Traders", 0.95),
        items=[
            ExtractedItem(
                product_name=_guess("Sugar", 0.9),
                quantity=_guess("10", 0.85),
                unit=_guess("kg", 0.7),
                price=_guess("55", 0.9),
            )
        ],
    )

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))
    monkeypatch.setattr("app.api.webhooks.whatsapp.download_media", _fake_downloader())
    monkeypatch.setattr(
        "app.api.webhooks.whatsapp.extract_invoice_from_image", _fake_extractor(extraction)
    )

    async with await _anon_client() as client:
        await _send_photo(client, bare_sender)
        assert "i read this invoice as being for" in sent[-1].lower()
        assert "ram traders" in sent[-1].lower()

        await _send_text(client, bare_sender, "YES")  # accept dealer suggestion
        assert "i read the next item as" in sent[-1].lower()
        assert "sugar" in sent[-1].lower()

        await _send_text(client, bare_sender, "YES")  # accept product-name suggestion
        assert "don't have" in sent[-1].lower()  # Sugar isn't in the catalogue yet

        await _send_text(client, bare_sender, "yes")  # confirm adding it as a new product
        assert "i read the price for sugar as" in sent[-1].lower()

        await _send_text(client, bare_sender, "YES")  # accept price suggestion
        assert "i read the quantity of sugar as" in sent[-1].lower()
        assert "10" in sent[-1]

        await _send_text(client, bare_sender, "YES")  # accept quantity suggestion
        assert "added" in sent[-1].lower()
        assert "done" in sent[-1].lower()

        await _send_text(client, bare_sender, "done")
        assert "confirm" in sent[-1].lower()
        assert "550" in sent[-1]  # 10 x 55.00

        await _send_text(client, bare_sender, "YES")
        assert "created" in sent[-1].lower()

    invoice = await db.scalar(
        select(Invoice).where(Invoice.company_id == company_id, Invoice.dealer_id.isnot(None))
    )
    assert invoice is not None
    assert invoice.total_amount == Decimal("550.00")

    company = await db.get(Company, company_id)
    assert company.active_workflow is None
    assert company.workflow_scratch is None


@pytest.mark.asyncio
async def test_ocr_typed_correction_overrides_suggestion(db: AsyncSession, monkeypatch) -> None:
    """Typing something other than a bare YES at a suggested step must be
    honored exactly like manual entry — the (wrong) OCR guess is discarded.
    """
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    await _make_dealer(db, company_id, "Ram Traders")

    extraction = ExtractedInvoice(
        is_invoice=True,
        invoice_number=_guess(None, 0.0),
        dealer_name=_guess("Wrong Traders", 0.9),
        items=[],
    )
    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))
    monkeypatch.setattr("app.api.webhooks.whatsapp.download_media", _fake_downloader())
    monkeypatch.setattr(
        "app.api.webhooks.whatsapp.extract_invoice_from_image", _fake_extractor(extraction)
    )

    async with await _anon_client() as client:
        await _send_photo(client, bare_sender)
        assert "wrong traders" in sent[-1].lower()

        await _send_text(client, bare_sender, "Ram Traders")
        # Matched an existing dealer directly — no "add new dealer?" prompt.
        assert "what product" in sent[-1].lower()

    company = await db.get(Company, company_id)
    assert company.workflow_scratch["dealer_name"] == "Ram Traders"


@pytest.mark.asyncio
async def test_ocr_low_confidence_field_gets_plain_question(db: AsyncSession, monkeypatch) -> None:
    """A field below the confidence threshold (or with no value at all) never
    offers a YES-shortcut, even when a sibling field on the same item does.
    """
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    await _make_dealer(db, company_id, "Ram Traders")

    extraction = ExtractedInvoice(
        is_invoice=True,
        invoice_number=_guess(None, 0.0),
        dealer_name=_guess("Ram Traders", 0.95),
        items=[
            ExtractedItem(
                product_name=_guess("Sugar", 0.9),
                quantity=_guess("10", 0.3),  # below threshold
                unit=_guess("kg", 0.9),
                price=_guess(None, 0.0),  # no legible value at all
            )
        ],
    )
    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))
    monkeypatch.setattr("app.api.webhooks.whatsapp.download_media", _fake_downloader())
    monkeypatch.setattr(
        "app.api.webhooks.whatsapp.extract_invoice_from_image", _fake_extractor(extraction)
    )

    async with await _anon_client() as client:
        await _send_photo(client, bare_sender)
        await _send_text(client, bare_sender, "YES")  # accept dealer
        assert "sugar" in sent[-1].lower()  # product suggestion still offered (0.9 confidence)

        await _send_text(client, bare_sender, "YES")  # accept product name -> new-product-confirm
        assert "don't have" in sent[-1].lower()

        await _send_text(client, bare_sender, "yes")  # confirm new product -> awaiting_price
        assert "i read the price" not in sent[-1].lower()
        assert "selling price" in sent[-1].lower()

        await _send_text(client, bare_sender, "45")  # -> awaiting_quantity
        assert "i read the quantity" not in sent[-1].lower()
        assert "how many" in sent[-1].lower()


@pytest.mark.asyncio
async def test_ocr_no_dealer_extracted_still_reaches_working_flow(
    db: AsyncSession, monkeypatch
) -> None:
    """A partial extraction (dealer illegible, items present) degrades to the
    plain dealer question — and still offers the queued item's suggestions
    once the dealer is resolved manually.
    """
    phone = _unique_phone()
    await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")

    extraction = ExtractedInvoice(
        is_invoice=True,
        invoice_number=_guess(None, 0.0),
        dealer_name=_guess(None, 0.0),
        items=[
            ExtractedItem(
                product_name=_guess("Sugar", 0.9),
                quantity=_guess("5", 0.9),
                unit=_guess("kg", 0.9),
                price=_guess("40", 0.9),
            )
        ],
    )
    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))
    monkeypatch.setattr("app.api.webhooks.whatsapp.download_media", _fake_downloader())
    monkeypatch.setattr(
        "app.api.webhooks.whatsapp.extract_invoice_from_image", _fake_extractor(extraction)
    )

    async with await _anon_client() as client:
        await _send_photo(client, bare_sender)
        assert "couldn't make out the dealer" in sent[-1].lower()

        await _send_text(client, bare_sender, "New Dealer Co")
        assert "don't have" in sent[-1].lower()  # new-dealer confirm

        await _send_text(client, bare_sender, "yes")
        assert "sugar" in sent[-1].lower()  # queued item suggestion still offered


@pytest.mark.asyncio
async def test_ocr_not_an_invoice_starts_no_workflow(db: AsyncSession, monkeypatch) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))
    monkeypatch.setattr("app.api.webhooks.whatsapp.download_media", _fake_downloader())
    monkeypatch.setattr(
        "app.api.webhooks.whatsapp.extract_invoice_from_image", _fake_extractor(None)
    )

    async with await _anon_client() as client:
        await _send_photo(client, bare_sender)

    assert "couldn't read that as an invoice" in sent[-1].lower()
    company = await db.get(Company, company_id)
    assert company.active_workflow is None


@pytest.mark.asyncio
async def test_ocr_download_failure_is_graceful(db: AsyncSession, monkeypatch) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")

    async def _failing_download(media_id: str):
        raise WhatsAppSendError("Meta returned 500")

    async def _unreachable_extract(image_bytes: bytes, mime_type: str):
        raise AssertionError("extract_invoice_from_image must not run when download fails")

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))
    monkeypatch.setattr("app.api.webhooks.whatsapp.download_media", _failing_download)
    monkeypatch.setattr(
        "app.api.webhooks.whatsapp.extract_invoice_from_image", _unreachable_extract
    )

    async with await _anon_client() as client:
        await _send_photo(client, bare_sender)

    assert "couldn't download that photo" in sent[-1].lower()
    company = await db.get(Company, company_id)
    assert company.active_workflow is None


@pytest.mark.asyncio
async def test_ocr_busy_mid_onboarding_gets_canned_reply_and_skips_download(
    db: AsyncSession, monkeypatch
) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    company = await db.get(Company, company_id)
    company.onboarding_state = OnboardingState.not_started
    await db.commit()
    bare_sender = phone.removeprefix("+")

    sent: list[str] = []
    download_calls: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))
    monkeypatch.setattr(
        "app.api.webhooks.whatsapp.download_media", _fake_downloader(download_calls)
    )

    async with await _anon_client() as client:
        await _send_photo(client, bare_sender)

    assert "in the middle of something" in sent[-1].lower()
    assert download_calls == []


@pytest.mark.asyncio
async def test_ocr_busy_mid_active_workflow_gets_canned_reply_and_skips_download(
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
        await _send_text(client, bare_sender, "record payment")  # starts a real active_workflow
        await _send_photo(client, bare_sender)

    assert "in the middle of something" in sent[-1].lower()
    assert download_calls == []


@pytest.mark.asyncio
async def test_ocr_busy_mid_pending_operation_gets_canned_reply_and_skips_download(
    db: AsyncSession, monkeypatch
) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    company = await db.get(Company, company_id)

    op = await create_pending_operation(db, company, PendingOperationType.create_order, {})
    company.active_pending_operation_id = op.id
    await db.commit()

    sent: list[str] = []
    download_calls: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))
    monkeypatch.setattr(
        "app.api.webhooks.whatsapp.download_media", _fake_downloader(download_calls)
    )

    async with await _anon_client() as client:
        await _send_photo(client, bare_sender)

    assert "in the middle of something" in sent[-1].lower()
    assert download_calls == []


@pytest.mark.asyncio
async def test_ocr_busy_mid_follow_up_gets_canned_reply_and_skips_download(
    db: AsyncSession, monkeypatch
) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    dealer_id = await _make_dealer(db, company_id, "Ram Traders")
    company = await db.get(Company, company_id)
    today = business_now(company.timezone).date()

    invoice = Invoice(
        company_id=company_id,
        invoice_number="INV-FOLLOWUP",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        invoice_date=today,
        due_date=today + timedelta(days=14),
        subtotal=Decimal("100.00"),
        gst_amount=Decimal("0.00"),
        total_amount=Decimal("100.00"),
        status=InvoiceStatus.Pending,
        source=InvoiceSource.csv_import,
    )
    db.add(invoice)
    await db.flush()
    company.pending_follow_up_invoice_id = invoice.id
    await db.commit()

    sent: list[str] = []
    download_calls: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))
    monkeypatch.setattr(
        "app.api.webhooks.whatsapp.download_media", _fake_downloader(download_calls)
    )

    async with await _anon_client() as client:
        await _send_photo(client, bare_sender)

    assert "in the middle of something" in sent[-1].lower()
    assert download_calls == []
