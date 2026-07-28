"""Guided create-order workflow — full webhook walk, Phase 2B.

Same conventions as tests/test_payment_flow.py: real HMAC-signed POSTs
against the actual webhook endpoint, send_text_message monkeypatched to
capture outbound replies instead of hitting Meta for real.

    uv run alembic upgrade head
    uv run pytest tests/test_order_flow.py -v
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
from app.models.company import Company
from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceDirection, InvoiceSource, InvoiceStatus
from app.models.invoice_item import InvoiceItem
from app.models.payment import Payment
from app.models.pending_operation import PendingOperation
from app.models.product import Product
from app.services.snapshot import business_now
from app.services.whatsapp_client import WhatsAppSendResult
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _unique_phone() -> str:
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


async def _make_company(
    db: AsyncSession, whatsapp_number: str, *, gst_rate: Decimal = Decimal("0")
) -> uuid.UUID:
    company = Company(
        business_name="Order Flow Test Co",
        owner_name="Owner",
        whatsapp_number=whatsapp_number,
        gst_rate=gst_rate,
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
    payment_terms_days: int | None = None,
    credit_limit: Decimal | None = None,
) -> uuid.UUID:
    dealer = Dealer(
        company_id=company_id,
        name=name,
        payment_terms_days=payment_terms_days,
        credit_limit=credit_limit,
    )
    db.add(dealer)
    await db.commit()
    await db.refresh(dealer)
    return dealer.id


async def _make_product(
    db: AsyncSession,
    company_id: uuid.UUID,
    name: str,
    *,
    selling_price: Decimal | None = None,
    stock_quantity: Decimal = Decimal("0"),
    unit: str | None = None,
) -> uuid.UUID:
    product = Product(
        company_id=company_id,
        name=name,
        unit=unit,
        selling_price=selling_price,
        stock_quantity=stock_quantity,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product.id


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


def _fake_sender(sent: list[str]):
    async def _fake_send(to: str, body: str) -> WhatsAppSendResult:
        sent.append(body)
        return WhatsAppSendResult(message_id=f"wamid.{uuid.uuid4().hex}")

    return _fake_send


@pytest.mark.asyncio
async def test_happy_path_existing_dealer_and_priced_product(
    db: AsyncSession, monkeypatch
) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    await _make_dealer(db, company_id, "Ram Traders")
    await _make_product(
        db, company_id, "Rice", selling_price=Decimal("55.00"), stock_quantity=Decimal("100")
    )

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))

    async with await _anon_client() as client:
        await _send(client, bare_sender, "new order")
        assert "who is this order for" in sent[-1].lower()

        await _send(client, bare_sender, "Ram Traders")
        assert "what product" in sent[-1].lower()

        await _send(client, bare_sender, "Rice")
        assert "how many" in sent[-1].lower()

        await _send(client, bare_sender, "10")
        assert "added" in sent[-1].lower()
        assert "done" in sent[-1].lower()

        await _send(client, bare_sender, "done")
        assert "confirm" in sent[-1].lower()
        assert "550" in sent[-1]  # 10 x 55.00

        await _send(client, bare_sender, "YES")
        assert "order" in sent[-1].lower()
        assert "created" in sent[-1].lower()

    invoice = await db.scalar(
        select(Invoice).where(Invoice.company_id == company_id, Invoice.dealer_id.isnot(None))
    )
    assert invoice is not None
    assert invoice.total_amount == Decimal("550.00")
    items = (
        (await db.execute(select(InvoiceItem).where(InvoiceItem.invoice_id == invoice.id)))
        .scalars()
        .all()
    )
    assert len(items) == 1
    assert items[0].quantity == Decimal("10.0000")

    product = await db.scalar(select(Product).where(Product.company_id == company_id))
    assert product.stock_quantity == Decimal("90.0000")

    company = await db.get(Company, company_id)
    assert company.active_workflow is None
    assert company.workflow_scratch is None
    remaining_op = await db.scalar(
        select(PendingOperation).where(PendingOperation.company_id == company_id)
    )
    assert remaining_op is None


@pytest.mark.asyncio
async def test_new_dealer_confirmed_and_created_on_execute(db: AsyncSession, monkeypatch) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    await _make_product(db, company_id, "Rice", selling_price=Decimal("55.00"))

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))

    async with await _anon_client() as client:
        await _send(client, bare_sender, "new order")
        await _send(client, bare_sender, "Brand New Dealer")
        assert "don't have" in sent[-1].lower()

        await _send(client, bare_sender, "yes")
        assert "phone number" in sent[-1].lower()

        await _send(client, bare_sender, "skip")
        assert "what product" in sent[-1].lower()

        await _send(client, bare_sender, "Rice")
        await _send(client, bare_sender, "5")
        await _send(client, bare_sender, "done")
        await _send(client, bare_sender, "YES")
        assert "created" in sent[-1].lower()

    dealer = await db.scalar(
        select(Dealer).where(Dealer.company_id == company_id, Dealer.name == "Brand New Dealer")
    )
    assert dealer is not None
    assert dealer.phone is None


@pytest.mark.asyncio
async def test_new_dealer_phone_is_collected_and_saved(db: AsyncSession, monkeypatch) -> None:
    """Providing a real number (instead of 'skip') at the new phone question
    (fix for the bug where a dealer added inline during order creation could
    never receive their invoice directly, since nothing ever asked for their
    phone) persists it on the created Dealer row.
    """
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    await _make_product(db, company_id, "Rice", selling_price=Decimal("55.00"))
    # A fixed valid Indian mobile prefix (6-9), not _unique_phone()'s fully
    # random 10 digits — that helper only sometimes lands on a valid prefix
    # and normalize_party_phone rejects the rest (same pre-existing flake
    # documented for tests/test_company_export.py's own _unique_phone()).
    dealer_phone = f"+919{uuid.uuid4().int % 1_000_000_000:09d}"

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))

    async with await _anon_client() as client:
        await _send(client, bare_sender, "new order")
        await _send(client, bare_sender, "Spandan")
        await _send(client, bare_sender, "yes")
        assert "phone number" in sent[-1].lower()

        await _send(client, bare_sender, dealer_phone)
        assert "what product" in sent[-1].lower()

        await _send(client, bare_sender, "Rice")
        await _send(client, bare_sender, "5")
        await _send(client, bare_sender, "done")
        await _send(client, bare_sender, "YES")
        assert "created" in sent[-1].lower()

    dealer = await db.scalar(
        select(Dealer).where(Dealer.company_id == company_id, Dealer.name == "Spandan")
    )
    assert dealer is not None
    assert dealer.phone == dealer_phone


@pytest.mark.asyncio
async def test_new_dealer_invalid_phone_reasked(db: AsyncSession, monkeypatch) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    await _make_product(db, company_id, "Rice", selling_price=Decimal("55.00"))

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))

    async with await _anon_client() as client:
        await _send(client, bare_sender, "new order")
        await _send(client, bare_sender, "Spandan")
        await _send(client, bare_sender, "yes")

        await _send(client, bare_sender, "not a phone number")
        assert "phone" in sent[-1].lower()
        assert "what product" not in sent[-1].lower()

        await _send(client, bare_sender, "skip")
        assert "what product" in sent[-1].lower()

    dealer = await db.scalar(
        select(Dealer).where(Dealer.company_id == company_id, Dealer.name == "Spandan")
    )
    assert dealer is None  # not created yet — only happens at YES/execute


@pytest.mark.asyncio
async def test_unpriced_existing_product_asks_for_price(db: AsyncSession, monkeypatch) -> None:
    """A product the guided onboarding conversation created has a name but no
    selling_price — the order flow must ask for a price just like a
    brand-new product, not silently fail.
    """
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    await _make_dealer(db, company_id, "Ram Traders")
    await _make_product(db, company_id, "Onboarded Product", selling_price=None)

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))

    async with await _anon_client() as client:
        await _send(client, bare_sender, "new order")
        await _send(client, bare_sender, "Ram Traders")
        await _send(client, bare_sender, "Onboarded Product")
        assert "selling price" in sent[-1].lower()

        await _send(client, bare_sender, "20")
        assert "how many" in sent[-1].lower()

        await _send(client, bare_sender, "3")
        await _send(client, bare_sender, "done")
        await _send(client, bare_sender, "YES")
        assert "created" in sent[-1].lower()

    product = await db.scalar(
        select(Product).where(
            Product.company_id == company_id, Product.name == "Onboarded Product"
        )
    )
    assert product.selling_price == Decimal("20.00")


@pytest.mark.asyncio
async def test_multi_item_order(db: AsyncSession, monkeypatch) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    await _make_dealer(db, company_id, "Ram Traders")
    await _make_product(db, company_id, "Rice", selling_price=Decimal("55.00"))
    await _make_product(db, company_id, "Wheat", selling_price=Decimal("40.00"))

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))

    async with await _anon_client() as client:
        await _send(client, bare_sender, "new order")
        await _send(client, bare_sender, "Ram Traders")
        await _send(client, bare_sender, "Rice")
        await _send(client, bare_sender, "10")
        await _send(client, bare_sender, "Wheat")
        await _send(client, bare_sender, "5")
        await _send(client, bare_sender, "done")
        assert "confirm" in sent[-1].lower()
        assert "750" in sent[-1]  # 10*55 + 5*40 = 750

        await _send(client, bare_sender, "YES")

    invoice = await db.scalar(select(Invoice).where(Invoice.company_id == company_id))
    assert invoice.total_amount == Decimal("750.00")
    items = (
        (await db.execute(select(InvoiceItem).where(InvoiceItem.invoice_id == invoice.id)))
        .scalars()
        .all()
    )
    assert len(items) == 2


@pytest.mark.asyncio
async def test_cancel_mid_flow(db: AsyncSession, monkeypatch) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))

    async with await _anon_client() as client:
        await _send(client, bare_sender, "new order")
        await _send(client, bare_sender, "Ram Traders")
        await _send(client, bare_sender, "cancel")
        assert "cancelled" in sent[-1].lower()

    company = await db.get(Company, company_id)
    assert company.active_workflow is None
    assert company.workflow_scratch is None


@pytest.mark.asyncio
async def test_zero_and_negative_quantity_rejected(db: AsyncSession, monkeypatch) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    await _make_dealer(db, company_id, "Ram Traders")
    await _make_product(db, company_id, "Rice", selling_price=Decimal("55.00"))

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))

    async with await _anon_client() as client:
        await _send(client, bare_sender, "new order")
        await _send(client, bare_sender, "Ram Traders")
        await _send(client, bare_sender, "Rice")

        await _send(client, bare_sender, "0")
        assert "greater than zero" in sent[-1].lower()

        await _send(client, bare_sender, "-5")
        assert "greater than zero" in sent[-1].lower()

        await _send(client, bare_sender, "10")
        assert "added" in sent[-1].lower()


@pytest.mark.asyncio
async def test_order_driving_stock_negative_still_succeeds_but_warns(
    db: AsyncSession, monkeypatch
) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    await _make_dealer(db, company_id, "Ram Traders")
    await _make_product(
        db, company_id, "Rice", selling_price=Decimal("55.00"), stock_quantity=Decimal("5")
    )

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))

    async with await _anon_client() as client:
        await _send(client, bare_sender, "new order")
        await _send(client, bare_sender, "Ram Traders")
        await _send(client, bare_sender, "Rice")
        await _send(client, bare_sender, "10")  # only 5 in stock
        await _send(client, bare_sender, "done")
        await _send(client, bare_sender, "YES")
        assert "created" in sent[-1].lower()
        assert "negative" in sent[-1].lower()

    product = await db.scalar(select(Product).where(Product.company_id == company_id))
    assert product.stock_quantity == Decimal("-5.0000")


@pytest.mark.asyncio
async def test_product_deleted_between_preview_and_confirm_recreates_from_cached_price(
    db: AsyncSession, monkeypatch
) -> None:
    """create_order re-derives against current DB state at confirm time (per
    the PendingOperation contract) — if the matched product is gone by then,
    it re-creates it using the price the flow already collected, rather than
    failing the whole order.
    """
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    await _make_dealer(db, company_id, "Ram Traders")
    product_id = await _make_product(db, company_id, "Rice", selling_price=Decimal("55.00"))

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))

    async with await _anon_client() as client:
        await _send(client, bare_sender, "new order")
        await _send(client, bare_sender, "Ram Traders")
        await _send(client, bare_sender, "Rice")
        await _send(client, bare_sender, "10")
        await _send(client, bare_sender, "done")

        # Product removed from the catalogue after the preview, before "YES".
        product = await db.get(Product, product_id)
        await db.delete(product)
        await db.commit()

        await _send(client, bare_sender, "YES")
        assert "created" in sent[-1].lower()

    recreated = await db.scalar(
        select(Product).where(Product.company_id == company_id, Product.name == "Rice")
    )
    assert recreated is not None
    assert recreated.selling_price == Decimal("55.00")


@pytest.mark.asyncio
async def test_no_discards_pending_operation(db: AsyncSession, monkeypatch) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    await _make_dealer(db, company_id, "Ram Traders")
    await _make_product(db, company_id, "Rice", selling_price=Decimal("55.00"))

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))

    async with await _anon_client() as client:
        await _send(client, bare_sender, "new order")
        await _send(client, bare_sender, "Ram Traders")
        await _send(client, bare_sender, "Rice")
        await _send(client, bare_sender, "10")
        await _send(client, bare_sender, "done")
        await _send(client, bare_sender, "NO")
        assert "cancelled" in sent[-1].lower()

    invoice_count = len(
        (await db.execute(select(Invoice).where(Invoice.company_id == company_id)))
        .scalars()
        .all()
    )
    assert invoice_count == 0
    remaining_op = await db.scalar(
        select(PendingOperation).where(PendingOperation.company_id == company_id)
    )
    assert remaining_op is None


@pytest.mark.asyncio
async def test_gst_applied_from_company_rate(db: AsyncSession, monkeypatch) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone, gst_rate=Decimal("5.00"))
    bare_sender = phone.removeprefix("+")
    await _make_dealer(db, company_id, "Ram Traders")
    await _make_product(db, company_id, "Rice", selling_price=Decimal("100.00"))

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))

    async with await _anon_client() as client:
        await _send(client, bare_sender, "new order")
        await _send(client, bare_sender, "Ram Traders")
        await _send(client, bare_sender, "Rice")
        await _send(client, bare_sender, "10")  # 10 x 100 = 1000 subtotal
        await _send(client, bare_sender, "done")
        # The pre-confirm preview must show the GST-inclusive total the user is
        # actually agreeing to — not the bare subtotal.
        preview = sent[-1]
        assert "1,050" in preview  # 1000 + 5% GST
        assert "GST" in preview
        await _send(client, bare_sender, "YES")
        assert "created" in sent[-1].lower()
        assert "1,050" in sent[-1]  # 1000 + 5% GST

    invoice = await db.scalar(select(Invoice).where(Invoice.company_id == company_id))
    assert invoice.subtotal == Decimal("1000.00")
    assert invoice.gst_amount == Decimal("50.00")
    assert invoice.total_amount == Decimal("1050.00")


@pytest.mark.asyncio
async def test_due_date_defaults_to_14_days_without_dealer_terms(
    db: AsyncSession, monkeypatch
) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    await _make_dealer(db, company_id, "Ram Traders", payment_terms_days=None)
    await _make_product(db, company_id, "Rice", selling_price=Decimal("55.00"))

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))

    async with await _anon_client() as client:
        await _send(client, bare_sender, "new order")
        await _send(client, bare_sender, "Ram Traders")
        await _send(client, bare_sender, "Rice")
        await _send(client, bare_sender, "10")
        await _send(client, bare_sender, "done")
        await _send(client, bare_sender, "YES")

    invoice = await db.scalar(select(Invoice).where(Invoice.company_id == company_id))
    company = await db.get(Company, company_id)
    today = business_now(company.timezone).date()
    assert invoice.due_date == today + timedelta(days=14)


@pytest.mark.asyncio
async def test_due_date_uses_dealer_payment_terms_when_set(db: AsyncSession, monkeypatch) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    await _make_dealer(db, company_id, "Ram Traders", payment_terms_days=30)
    await _make_product(db, company_id, "Rice", selling_price=Decimal("55.00"))

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))

    async with await _anon_client() as client:
        await _send(client, bare_sender, "new order")
        await _send(client, bare_sender, "Ram Traders")
        await _send(client, bare_sender, "Rice")
        await _send(client, bare_sender, "10")
        await _send(client, bare_sender, "done")
        await _send(client, bare_sender, "YES")

    invoice = await db.scalar(select(Invoice).where(Invoice.company_id == company_id))
    company = await db.get(Company, company_id)
    today = business_now(company.timezone).date()
    assert invoice.due_date == today + timedelta(days=30)


@pytest.mark.asyncio
async def test_create_invoice_alias_starts_same_flow(db: AsyncSession, monkeypatch) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    await _make_dealer(db, company_id, "Ram Traders")
    await _make_product(db, company_id, "Rice", selling_price=Decimal("55.00"))

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))

    async with await _anon_client() as client:
        await _send(client, bare_sender, "create invoice")
        assert "who is this order for" in sent[-1].lower()

        await _send(client, bare_sender, "Ram Traders")
        await _send(client, bare_sender, "Rice")
        await _send(client, bare_sender, "10")
        await _send(client, bare_sender, "done")
        await _send(client, bare_sender, "YES")
        assert "created" in sent[-1].lower()

    invoice = await db.scalar(select(Invoice).where(Invoice.company_id == company_id))
    assert invoice is not None
    assert invoice.total_amount == Decimal("550.00")


@pytest.mark.asyncio
async def test_pdf_not_sent_when_dealer_has_no_phone(db: AsyncSession, monkeypatch) -> None:
    """No dealer phone on file -> send_invoice_document skips gracefully and
    the reply says so, but invoice creation still succeeds.
    """
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    await _make_dealer(db, company_id, "Ram Traders")
    await _make_product(db, company_id, "Rice", selling_price=Decimal("55.00"))

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))

    async with await _anon_client() as client:
        await _send(client, bare_sender, "new order")
        await _send(client, bare_sender, "Ram Traders")
        await _send(client, bare_sender, "Rice")
        await _send(client, bare_sender, "10")
        await _send(client, bare_sender, "done")
        await _send(client, bare_sender, "YES")
        assert "created" in sent[-1].lower()
        assert "pdf not sent" in sent[-1].lower()

    invoice = await db.scalar(select(Invoice).where(Invoice.company_id == company_id))
    assert invoice is not None


@pytest.mark.asyncio
async def test_duplicate_order_same_day_same_total_warns_but_still_creates(
    db: AsyncSession, monkeypatch
) -> None:
    """A second order for the same dealer, same day, same total gets an
    advisory warning in the preview — but still creates on YES, since two
    separate orders can legitimately share a date and total.
    """
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    dealer_id = await _make_dealer(db, company_id, "Ram Traders")
    await _make_product(
        db, company_id, "Rice", selling_price=Decimal("55.00"), stock_quantity=Decimal("100")
    )
    company = await db.get(Company, company_id)
    today = business_now(company.timezone).date()

    db.add(
        Invoice(
            company_id=company_id,
            invoice_number="INV-EXISTING",
            direction=InvoiceDirection.receivable,
            dealer_id=dealer_id,
            invoice_date=today,
            due_date=today + timedelta(days=14),
            subtotal=Decimal("550.00"),
            gst_amount=Decimal("0.00"),
            total_amount=Decimal("550.00"),
            status=InvoiceStatus.Pending,
            source=InvoiceSource.csv_import,
        )
    )
    await db.commit()

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))

    async with await _anon_client() as client:
        await _send(client, bare_sender, "new order")
        await _send(client, bare_sender, "Ram Traders")
        await _send(client, bare_sender, "Rice")
        await _send(client, bare_sender, "10")  # 10 x 55.00 = 550.00, matches INV-EXISTING
        await _send(client, bare_sender, "done")
        assert "confirm" in sent[-1].lower()
        assert "similar to an existing invoice" in sent[-1].lower()
        assert "inv-existing" in sent[-1].lower()
        assert "reply yes to continue" in sent[-1].lower()

        await _send(client, bare_sender, "YES")
        assert "created" in sent[-1].lower()

    invoice_count = len(
        (await db.execute(select(Invoice).where(Invoice.company_id == company_id)))
        .scalars()
        .all()
    )
    assert invoice_count == 2  # the seeded one + the new one, both kept


@pytest.mark.asyncio
async def test_credit_limit_breach_warns_but_still_creates(db: AsyncSession, monkeypatch) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    dealer_id = await _make_dealer(db, company_id, "Ram Traders", credit_limit=Decimal("1000.00"))
    await _make_product(db, company_id, "Rice", selling_price=Decimal("55.00"))
    company = await db.get(Company, company_id)
    today = business_now(company.timezone).date()

    # Existing outstanding of 800 — a new order takes it well over the 1000 limit.
    db.add(
        Invoice(
            company_id=company_id,
            invoice_number="INV-OUTSTANDING",
            direction=InvoiceDirection.receivable,
            dealer_id=dealer_id,
            invoice_date=today - timedelta(days=5),
            due_date=today + timedelta(days=9),
            subtotal=Decimal("800.00"),
            gst_amount=Decimal("0.00"),
            total_amount=Decimal("800.00"),
            status=InvoiceStatus.Pending,
            source=InvoiceSource.csv_import,
        )
    )
    await db.commit()

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))

    async with await _anon_client() as client:
        await _send(client, bare_sender, "new order")
        await _send(client, bare_sender, "Ram Traders")
        await _send(client, bare_sender, "Rice")
        await _send(client, bare_sender, "5")  # 5 x 55.00 = 275.00 -> outstanding 1075 > 1000
        await _send(client, bare_sender, "done")
        assert "confirm" in sent[-1].lower()
        assert "over their credit" in sent[-1].lower()
        assert "1,000" in sent[-1]

        await _send(client, bare_sender, "YES")
        assert "created" in sent[-1].lower()

    invoice_count = len(
        (await db.execute(select(Invoice).where(Invoice.company_id == company_id)))
        .scalars()
        .all()
    )
    assert invoice_count == 2  # the breach didn't block the order


@pytest.mark.asyncio
async def test_credit_limit_none_skips_check_silently(db: AsyncSession, monkeypatch) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    await _make_dealer(db, company_id, "Ram Traders", credit_limit=None)
    await _make_product(db, company_id, "Rice", selling_price=Decimal("5500.00"))

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))

    async with await _anon_client() as client:
        await _send(client, bare_sender, "new order")
        await _send(client, bare_sender, "Ram Traders")
        await _send(client, bare_sender, "Rice")
        await _send(client, bare_sender, "100")  # a huge order — no limit on file to breach
        await _send(client, bare_sender, "done")
        assert "confirm" in sent[-1].lower()
        assert "credit" not in sent[-1].lower()


@pytest.mark.asyncio
async def test_new_dealer_skips_duplicate_and_credit_checks(
    db: AsyncSession, monkeypatch
) -> None:
    """A brand-new, not-yet-confirmed dealer has no DB row/credit_limit/order
    history yet, so both advisory checks must skip rather than error or
    (worse) silently treat it as some existing dealer.
    """
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    await _make_product(db, company_id, "Rice", selling_price=Decimal("55.00"))

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))

    async with await _anon_client() as client:
        await _send(client, bare_sender, "new order")
        await _send(client, bare_sender, "Brand New Dealer")
        await _send(client, bare_sender, "yes")
        await _send(client, bare_sender, "skip")
        await _send(client, bare_sender, "Rice")
        await _send(client, bare_sender, "10")
        await _send(client, bare_sender, "done")
        assert "confirm" in sent[-1].lower()
        assert "similar to an existing invoice" not in sent[-1].lower()
        assert "credit" not in sent[-1].lower()

        await _send(client, bare_sender, "YES")
        assert "created" in sent[-1].lower()


@pytest.mark.asyncio
async def test_preview_always_shows_payment_made_and_balance_due(
    db: AsyncSession, monkeypatch
) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    await _make_dealer(db, company_id, "Ram Traders")
    await _make_product(db, company_id, "Rice", selling_price=Decimal("55.00"))

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))

    async with await _anon_client() as client:
        await _send(client, bare_sender, "new order")
        await _send(client, bare_sender, "Ram Traders")
        await _send(client, bare_sender, "Rice")
        await _send(client, bare_sender, "10")  # 10 x 55.00 = 550.00
        await _send(client, bare_sender, "done")
        preview = sent[-1]
        assert "confirm" in preview.lower()
        assert "payment made" in preview.lower()
        assert "balance due" in preview.lower()
        assert "550" in preview
        assert "advance" in preview.lower()  # footer mentions the option


@pytest.mark.asyncio
async def test_advance_reply_asks_amount_then_updates_preview(
    db: AsyncSession, monkeypatch
) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    await _make_dealer(db, company_id, "Ram Traders")
    await _make_product(db, company_id, "Rice", selling_price=Decimal("55.00"))

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))

    async with await _anon_client() as client:
        await _send(client, bare_sender, "new order")
        await _send(client, bare_sender, "Ram Traders")
        await _send(client, bare_sender, "Rice")
        await _send(client, bare_sender, "10")  # total = 550.00
        await _send(client, bare_sender, "done")

        await _send(client, bare_sender, "advance")
        assert "how much" in sent[-1].lower()

        await _send(client, bare_sender, "200")
        assert "cash" in sent[-1].lower() and "online" in sent[-1].lower()

        await _send(client, bare_sender, "cash")
        preview = sent[-1]
        assert "confirm" in preview.lower()
        assert "200" in preview  # Payment Made
        assert "350" in preview  # Balance Due = 550 - 200

    # Nothing written to the DB yet — still just a pending confirmation.
    invoice_count = len(
        (await db.execute(select(Invoice).where(Invoice.company_id == company_id)))
        .scalars()
        .all()
    )
    assert invoice_count == 0


@pytest.mark.asyncio
async def test_advance_then_yes_creates_partially_paid_invoice_with_payment_row(
    db: AsyncSession, monkeypatch
) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    await _make_dealer(db, company_id, "Ram Traders")
    await _make_product(db, company_id, "Rice", selling_price=Decimal("55.00"))

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))

    async with await _anon_client() as client:
        await _send(client, bare_sender, "new order")
        await _send(client, bare_sender, "Ram Traders")
        await _send(client, bare_sender, "Rice")
        await _send(client, bare_sender, "10")  # total = 550.00
        await _send(client, bare_sender, "done")
        await _send(client, bare_sender, "advance")
        await _send(client, bare_sender, "200")
        await _send(client, bare_sender, "online")

        await _send(client, bare_sender, "YES")
        assert "created" in sent[-1].lower()
        assert "200" in sent[-1]  # Payment Made
        assert "350" in sent[-1]  # Balance Due

    invoice = await db.scalar(select(Invoice).where(Invoice.company_id == company_id))
    assert invoice is not None
    assert invoice.status == InvoiceStatus.Partially_Paid
    assert invoice.total_amount == Decimal("550.00")

    payment = await db.scalar(select(Payment).where(Payment.invoice_id == invoice.id))
    assert payment is not None
    assert payment.amount == Decimal("200.00")
    assert payment.method == "online"


@pytest.mark.asyncio
async def test_advance_covering_full_total_creates_paid_invoice(
    db: AsyncSession, monkeypatch
) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    await _make_dealer(db, company_id, "Ram Traders")
    await _make_product(db, company_id, "Rice", selling_price=Decimal("55.00"))

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))

    async with await _anon_client() as client:
        await _send(client, bare_sender, "new order")
        await _send(client, bare_sender, "Ram Traders")
        await _send(client, bare_sender, "Rice")
        await _send(client, bare_sender, "10")  # total = 550.00
        await _send(client, bare_sender, "done")
        await _send(client, bare_sender, "advance")
        await _send(client, bare_sender, "550")  # full amount paid upfront
        await _send(client, bare_sender, "cash")

        await _send(client, bare_sender, "YES")
        assert "created" in sent[-1].lower()

    invoice = await db.scalar(select(Invoice).where(Invoice.company_id == company_id))
    assert invoice.status == InvoiceStatus.Paid


@pytest.mark.asyncio
async def test_advance_exceeding_total_rejected_order_not_created(
    db: AsyncSession, monkeypatch
) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    await _make_dealer(db, company_id, "Ram Traders")
    await _make_product(db, company_id, "Rice", selling_price=Decimal("55.00"))

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))

    async with await _anon_client() as client:
        await _send(client, bare_sender, "new order")
        await _send(client, bare_sender, "Ram Traders")
        await _send(client, bare_sender, "Rice")
        await _send(client, bare_sender, "10")  # total = 550.00
        await _send(client, bare_sender, "done")
        await _send(client, bare_sender, "advance")

        await _send(client, bare_sender, "600")  # more than the 550 total
        assert "more than the order total" in sent[-1].lower()

        # The original PendingOperation is still intact and can still be confirmed.
        await _send(client, bare_sender, "YES")
        assert "created" in sent[-1].lower()

    invoice_count = len(
        (await db.execute(select(Invoice).where(Invoice.company_id == company_id)))
        .scalars()
        .all()
    )
    assert invoice_count == 1  # created without an advance, the 600 reply was simply rejected


@pytest.mark.asyncio
async def test_advance_non_numeric_reasked(db: AsyncSession, monkeypatch) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    await _make_dealer(db, company_id, "Ram Traders")
    await _make_product(db, company_id, "Rice", selling_price=Decimal("55.00"))

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))

    async with await _anon_client() as client:
        await _send(client, bare_sender, "new order")
        await _send(client, bare_sender, "Ram Traders")
        await _send(client, bare_sender, "Rice")
        await _send(client, bare_sender, "10")
        await _send(client, bare_sender, "done")
        await _send(client, bare_sender, "advance")

        await _send(client, bare_sender, "a lot")
        assert "greater than zero" in sent[-1].lower()

        await _send(client, bare_sender, "100")
        assert "cash" in sent[-1].lower() and "online" in sent[-1].lower()

        await _send(client, bare_sender, "cash")
        assert "confirm" in sent[-1].lower()
        assert "100" in sent[-1]


@pytest.mark.asyncio
async def test_advance_amount_of_one_or_two_not_swallowed_as_yes_no(
    db: AsyncSession, monkeypatch
) -> None:
    # Regression: "1"/"2" are also _YES_WORDS/_NO_WORDS shorthand elsewhere in
    # this same confirm gate, so a founder typing "1" meaning "₹1 advance" was
    # silently read as YES — executing the order with a ₹0 advance instead of
    # the amount they actually typed — and "2" silently cancelled the whole
    # order instead of erroring on/accepting it as ₹2.
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    await _make_dealer(db, company_id, "Ram Traders")
    await _make_product(db, company_id, "Rice", selling_price=Decimal("55.00"))

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))

    async with await _anon_client() as client:
        await _send(client, bare_sender, "new order")
        await _send(client, bare_sender, "Ram Traders")
        await _send(client, bare_sender, "Rice")
        await _send(client, bare_sender, "10")  # total = 550.00
        await _send(client, bare_sender, "done")
        await _send(client, bare_sender, "advance")

        await _send(client, bare_sender, "1")
        # Read as an advance amount (moves on to the method question), not as
        # YES (which would have created the order immediately).
        assert "cash" in sent[-1].lower() and "online" in sent[-1].lower()

    invoice = await db.scalar(select(Invoice).where(Invoice.company_id == company_id))
    assert invoice is None  # not created yet — still awaiting confirmation

    async with await _anon_client() as client:
        # "YES" here also escapes the still-pending method question (same
        # convention as the amount step) — confirms with the ₹1 advance
        # already recorded above, method left unset.
        await _send(client, bare_sender, "YES")

    invoice = await db.scalar(select(Invoice).where(Invoice.company_id == company_id))
    assert invoice is not None
    assert invoice.status == InvoiceStatus.Partially_Paid
    payment = await db.scalar(select(Payment).where(Payment.invoice_id == invoice.id))
    assert payment.amount == Decimal("1.00")


@pytest.mark.asyncio
async def test_order_asks_gst_rate_inline_for_existing_product_and_saves_it(
    db: AsyncSession, monkeypatch
) -> None:
    """When Company.gst_varies_by_product is True, a matched *existing*
    product with no per-product gst_rate set must never silently fall back
    to company.gst_rate (which is 0 in that mode) — but instead of refusing
    the order outright (the old behavior), it now asks for the rate inline,
    then offers to save it to the product for future orders.
    """
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    company = await db.get(Company, company_id)
    company.gst_varies_by_product = True
    await db.commit()
    await _make_dealer(db, company_id, "Ram Traders")
    product_id = await _make_product(
        db, company_id, "Rice", selling_price=Decimal("55.00")
    )  # gst_rate=None

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))

    async with await _anon_client() as client:
        await _send(client, bare_sender, "new order")
        await _send(client, bare_sender, "Ram Traders")
        await _send(client, bare_sender, "Rice")
        assert "gst" in sent[-1].lower()
        assert "rice" in sent[-1].lower()

        await _send(client, bare_sender, "not a number")
        assert "0 and 100" in sent[-1].lower()

        await _send(client, bare_sender, "5")
        assert "save" in sent[-1].lower()
        assert "5" in sent[-1]

        await _send(client, bare_sender, "YES")
        assert "quantity" in sent[-1].lower() or "how many" in sent[-1].lower()

        await _send(client, bare_sender, "10")
        await _send(client, bare_sender, "done")
        assert "confirm" in sent[-1].lower()
        await _send(client, bare_sender, "YES")
        assert "created" in sent[-1].lower()

    invoice = await db.scalar(select(Invoice).where(Invoice.company_id == company_id))
    assert invoice is not None
    assert invoice.gst_amount == Decimal("27.50")  # 550.00 * 5%

    product = await db.get(Product, product_id)
    assert product.gst_rate == Decimal("5")


@pytest.mark.asyncio
async def test_order_gst_rate_not_saved_when_declined(db: AsyncSession, monkeypatch) -> None:
    """Answering NO to the save-question must still use the entered rate for
    *this* order's line item, without persisting it to the product row.
    """
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    company = await db.get(Company, company_id)
    company.gst_varies_by_product = True
    await db.commit()
    await _make_dealer(db, company_id, "Ram Traders")
    product_id = await _make_product(db, company_id, "Rice", selling_price=Decimal("55.00"))

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))

    async with await _anon_client() as client:
        await _send(client, bare_sender, "new order")
        await _send(client, bare_sender, "Ram Traders")
        await _send(client, bare_sender, "Rice")
        await _send(client, bare_sender, "5")
        await _send(client, bare_sender, "NO")
        assert "quantity" in sent[-1].lower() or "how many" in sent[-1].lower()

        await _send(client, bare_sender, "10")
        await _send(client, bare_sender, "done")
        await _send(client, bare_sender, "YES")
        assert "created" in sent[-1].lower()

    invoice = await db.scalar(select(Invoice).where(Invoice.company_id == company_id))
    assert invoice is not None
    assert invoice.gst_amount == Decimal("27.50")  # this order still charged 5%

    product = await db.get(Product, product_id)
    assert product.gst_rate is None  # never persisted


@pytest.mark.asyncio
async def test_order_gst_rate_ask_can_still_be_cancelled(db: AsyncSession, monkeypatch) -> None:
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    company = await db.get(Company, company_id)
    company.gst_varies_by_product = True
    await db.commit()
    await _make_dealer(db, company_id, "Ram Traders")
    await _make_product(db, company_id, "Rice", selling_price=Decimal("55.00"))

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))

    async with await _anon_client() as client:
        await _send(client, bare_sender, "new order")
        await _send(client, bare_sender, "Ram Traders")
        await _send(client, bare_sender, "Rice")
        await _send(client, bare_sender, "cancel")
        assert "cancelled" in sent[-1].lower()

    pending_count = len(
        (
            await db.execute(
                select(PendingOperation).where(PendingOperation.company_id == company_id)
            )
        )
        .scalars()
        .all()
    )
    assert pending_count == 0


@pytest.mark.asyncio
async def test_order_asks_gst_rate_for_a_brand_new_product_when_company_varies_by_product(
    db: AsyncSession, monkeypatch
) -> None:
    """A product typed fresh mid-order (no catalogue match) never passed
    through the awaiting_product gate at all — it went straight to
    confirm -> price -> quantity with no gst_rate ever collected, so
    orders.py::create_order's own re-validation guard (never defaulted, see
    the sibling test above) then discarded the *entire* order at the very
    last step, unconditionally, for any gst_varies_by_product company
    introducing a new product through 'new order'. Must now ask for the new
    product's GST% right after the new-product confirm, and actually charge
    it.
    """
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    company = await db.get(Company, company_id)
    company.gst_varies_by_product = True
    await db.commit()
    await _make_dealer(db, company_id, "Ram Traders")

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))

    async with await _anon_client() as client:
        await _send(client, bare_sender, "new order")
        await _send(client, bare_sender, "Ram Traders")
        await _send(client, bare_sender, "Turmeric Powder")  # not in the catalogue
        assert "add" in sent[-1].lower() or "new product" in sent[-1].lower()

        await _send(client, bare_sender, "YES")
        assert "gst" in sent[-1].lower()
        assert "turmeric powder" in sent[-1].lower()

        await _send(client, bare_sender, "12")  # GST%
        assert "price" in sent[-1].lower()

        await _send(client, bare_sender, "80")  # price
        await _send(client, bare_sender, "10")  # quantity
        await _send(client, bare_sender, "done")
        assert "confirm" in sent[-1].lower()

        await _send(client, bare_sender, "YES")
        assert "created" in sent[-1].lower()

    invoice = await db.scalar(select(Invoice).where(Invoice.company_id == company_id))
    assert invoice is not None
    assert invoice.gst_amount == Decimal("96.00")  # 800.00 * 12%

    product = await db.scalar(
        select(Product).where(Product.company_id == company_id, Product.name == "Turmeric Powder")
    )
    assert product is not None
    assert product.gst_rate == Decimal("12")


@pytest.mark.asyncio
async def test_order_allows_product_with_gst_rate_when_company_varies_by_product(
    db: AsyncSession, monkeypatch
) -> None:
    """The same gate must not false-block a product that does have its own
    gst_rate on file — the order should complete normally.
    """
    phone = _unique_phone()
    company_id = await _make_company(db, phone)
    bare_sender = phone.removeprefix("+")
    company = await db.get(Company, company_id)
    company.gst_varies_by_product = True
    await db.commit()
    await _make_dealer(db, company_id, "Ram Traders")
    product_id = await _make_product(db, company_id, "Rice", selling_price=Decimal("55.00"))
    product = await db.get(Product, product_id)
    product.gst_rate = Decimal("5.00")
    await db.commit()

    sent: list[str] = []
    monkeypatch.setattr("app.api.webhooks.whatsapp.send_text_message", _fake_sender(sent))

    async with await _anon_client() as client:
        await _send(client, bare_sender, "new order")
        await _send(client, bare_sender, "Ram Traders")
        await _send(client, bare_sender, "Rice")
        assert "no gst rate" not in sent[-1].lower()
        await _send(client, bare_sender, "10")
        await _send(client, bare_sender, "done")
        assert "confirm" in sent[-1].lower()

        await _send(client, bare_sender, "YES")
        assert "created" in sent[-1].lower()

    invoice = await db.scalar(select(Invoice).where(Invoice.company_id == company_id))
    assert invoice is not None
    assert invoice.gst_amount == Decimal("27.50")  # 550.00 * 5%
