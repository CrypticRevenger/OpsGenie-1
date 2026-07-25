"""Dealer self-service over WhatsApp — read-only Phase 1
(app/services/dealer_self_service.py). Unit-level: exercises the reply
builders and the phone lookup directly against real seeded rows, without
going through the HTTP webhook (that's covered separately in
tests/test_webhooks_whatsapp.py, which also proves the founder path is never
misrouted here).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from app.core.config import get_settings
from app.models.company import Company
from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceDirection, InvoiceSource, InvoiceStatus
from app.models.payment import Payment, PaymentSource
from app.services.dealer_self_service import (
    Ambiguous,
    DealerMatch,
    dealer_balance_reply,
    dealer_help_reply,
    dealer_statement_reply,
    find_dealer_company,
    handle_dealer_message,
)
from sqlalchemy.ext.asyncio import AsyncSession


def _phone() -> str:
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


async def _make_company(
    db: AsyncSession, *, dealer_self_service_enabled: bool = True, subscription_active: bool = True
) -> Company:
    company = Company(
        business_name="Dealer Self-Service Co",
        owner_name="Owner",
        whatsapp_number=_phone(),
        dealer_self_service_enabled=dealer_self_service_enabled,
        subscription_active=subscription_active,
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company


async def _make_dealer(
    db: AsyncSession, company: Company, *, name: str = "Ram Traders", phone: str | None = None
) -> Dealer:
    dealer = Dealer(company_id=company.id, name=name, phone=phone or _phone())
    db.add(dealer)
    await db.commit()
    await db.refresh(dealer)
    return dealer


async def _add_invoice(
    db: AsyncSession,
    company: Company,
    dealer: Dealer,
    *,
    due_date: date,
    total_amount: Decimal,
    status: InvoiceStatus,
) -> Invoice:
    invoice = Invoice(
        company_id=company.id,
        invoice_number=f"INV-{uuid.uuid4().hex[:8]}",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer.id,
        invoice_date=date(2026, 1, 1),
        due_date=due_date,
        subtotal=total_amount,
        gst_amount=Decimal("0.00"),
        total_amount=total_amount,
        status=status,
        source=InvoiceSource.whatsapp,
    )
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)
    return invoice


async def _add_payment(
    db: AsyncSession, company: Company, invoice: Invoice, *, amount: Decimal, payment_date: date
) -> Payment:
    payment = Payment(
        company_id=company.id,
        invoice_id=invoice.id,
        amount=amount,
        payment_date=payment_date,
        source=PaymentSource.whatsapp,
    )
    db.add(payment)
    await db.commit()
    return payment


# ── find_dealer_company ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_find_dealer_company_matches_when_enabled(db: AsyncSession) -> None:
    company = await _make_company(db)
    dealer = await _make_dealer(db, company)

    result = await find_dealer_company(db, dealer.phone)

    assert isinstance(result, DealerMatch)
    assert result.company.id == company.id
    assert result.dealer.id == dealer.id


@pytest.mark.asyncio
async def test_find_dealer_company_none_when_not_opted_in(db: AsyncSession) -> None:
    company = await _make_company(db, dealer_self_service_enabled=False)
    dealer = await _make_dealer(db, company)

    assert await find_dealer_company(db, dealer.phone) is None


@pytest.mark.asyncio
async def test_find_dealer_company_none_when_subscription_inactive(db: AsyncSession) -> None:
    company = await _make_company(db, subscription_active=False)
    dealer = await _make_dealer(db, company)

    assert await find_dealer_company(db, dealer.phone) is None


@pytest.mark.asyncio
async def test_find_dealer_company_none_for_unknown_phone(db: AsyncSession) -> None:
    await _make_company(db)
    assert await find_dealer_company(db, _phone()) is None


@pytest.mark.asyncio
async def test_find_dealer_company_ambiguous_across_two_companies(db: AsyncSession) -> None:
    """The real (if pilot-scale-rare) cross-company leak risk this whole
    lookup exists to refuse rather than silently resolve — see
    find_dealer_company's own docstring.
    """
    shared_phone = _phone()
    company_a = await _make_company(db)
    await _make_dealer(db, company_a, phone=shared_phone)
    company_b = await _make_company(db)
    await _make_dealer(db, company_b, phone=shared_phone)

    assert isinstance(await find_dealer_company(db, shared_phone), Ambiguous)


@pytest.mark.asyncio
async def test_find_dealer_company_ambiguous_within_same_company(db: AsyncSession) -> None:
    """Two dealer rows under the same company sharing a phone is also
    refused, not just the cross-company case — there's no safe way to pick
    which dealer's data to send.
    """
    shared_phone = _phone()
    company = await _make_company(db)
    await _make_dealer(db, company, phone=shared_phone)
    await _make_dealer(db, company, phone=shared_phone)

    assert isinstance(await find_dealer_company(db, shared_phone), Ambiguous)


# ── dealer_balance_reply ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dealer_balance_reply_includes_outstanding_next_due_and_last_payment(
    db: AsyncSession,
) -> None:
    company = await _make_company(db)
    dealer = await _make_dealer(db, company)
    await _add_invoice(
        db,
        company,
        dealer,
        due_date=date(2026, 8, 15),
        total_amount=Decimal("24560.00"),
        status=InvoiceStatus.Pending,
    )
    paid_invoice = await _add_invoice(
        db,
        company,
        dealer,
        due_date=date(2026, 7, 1),
        total_amount=Decimal("5000.00"),
        status=InvoiceStatus.Paid,
    )
    await _add_payment(
        db, company, paid_invoice, amount=Decimal("5000.00"), payment_date=date(2026, 7, 18)
    )

    reply = await dealer_balance_reply(db, company, dealer)

    assert dealer.name in reply
    assert company.business_name in reply
    assert "24,560" in reply
    assert "15 Aug 2026" in reply
    assert "5,000" in reply
    assert "18 Jul 2026" in reply


@pytest.mark.asyncio
async def test_dealer_balance_reply_omits_optional_lines_when_nothing_to_show(
    db: AsyncSession,
) -> None:
    company = await _make_company(db)
    dealer = await _make_dealer(db, company)

    reply = await dealer_balance_reply(db, company, dealer)

    assert "No outstanding balance" in reply
    assert "Next due" not in reply
    assert "Last payment" not in reply


@pytest.mark.asyncio
async def test_dealer_balance_reply_scoped_to_one_dealer_only(db: AsyncSession) -> None:
    """Structurally can't leak another dealer's outstanding — proven, not
    just asserted by code review.
    """
    company = await _make_company(db)
    dealer = await _make_dealer(db, company)
    other_dealer = await _make_dealer(db, company, name="Shyam Distributors")
    await _add_invoice(
        db,
        company,
        other_dealer,
        due_date=date(2026, 8, 1),
        total_amount=Decimal("99999.00"),
        status=InvoiceStatus.Pending,
    )

    reply = await dealer_balance_reply(db, company, dealer)

    assert "No outstanding balance" in reply
    assert "99,999" not in reply
    assert other_dealer.name not in reply


# ── dealer_statement_reply ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dealer_statement_reply_returns_excel_and_pdf_links(db: AsyncSession) -> None:
    company = await _make_company(db)
    dealer = await _make_dealer(db, company)

    reply = await dealer_statement_reply(db, company, dealer)

    assert company.business_name in reply
    assert "Excel:" in reply
    assert "PDF:" in reply
    assert f"party={dealer.id}" in reply


@pytest.mark.asyncio
async def test_dealer_statement_reply_scoped_to_one_dealer_only(db: AsyncSession) -> None:
    """The link's party matches this dealer, not any other dealer on the same
    company — proven by checking the actual returned URL, not just that a
    link was returned. See test_signed_link_party_id_is_part_of_the_signature
    in tests/test_company_export.py for proof the link is also tamper-proof.
    """
    company = await _make_company(db)
    dealer = await _make_dealer(db, company)
    other_dealer = await _make_dealer(db, company, name="Shyam Distributors")

    reply = await dealer_statement_reply(db, company, dealer)

    assert f"party={dealer.id}" in reply
    assert str(other_dealer.id) not in reply


@pytest.mark.asyncio
async def test_dealer_statement_reply_not_configured(db: AsyncSession, monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "export_link_secret", None)
    company = await _make_company(db)
    dealer = await _make_dealer(db, company)

    reply = await dealer_statement_reply(db, company, dealer)

    assert "Excel:" not in reply
    assert company.business_name in reply


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["statement", "STATEMENT", "my statement", "ledger", "my ledger"])
async def test_handle_dealer_message_statement_synonyms(db: AsyncSession, text: str) -> None:
    company = await _make_company(db)
    dealer = await _make_dealer(db, company)

    reply = await handle_dealer_message(db, company, dealer, text)

    assert "Excel:" in reply
    assert f"party={dealer.id}" in reply


# ── dealer_help_reply / handle_dealer_message ─────────────────────────────────


@pytest.mark.asyncio
async def test_dealer_help_reply_is_minimal(db: AsyncSession) -> None:
    company = await _make_company(db)
    reply = dealer_help_reply(company)
    assert "BALANCE" in reply
    assert "STATEMENT" in reply
    assert "HELP" in reply


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text", ["balance", "BALANCE", "my balance", "outstanding", "dues", "how much do i owe"]
)
async def test_handle_dealer_message_balance_synonyms(db: AsyncSession, text: str) -> None:
    company = await _make_company(db)
    dealer = await _make_dealer(db, company)

    reply = await handle_dealer_message(db, company, dealer, text)

    assert "No outstanding balance" in reply


@pytest.mark.asyncio
async def test_handle_dealer_message_help(db: AsyncSession) -> None:
    company = await _make_company(db)
    dealer = await _make_dealer(db, company)

    reply = await handle_dealer_message(db, company, dealer, "help")

    assert "BALANCE" in reply


@pytest.mark.asyncio
async def test_handle_dealer_message_unrecognized_falls_back(db: AsyncSession) -> None:
    company = await _make_company(db)
    dealer = await _make_dealer(db, company)

    reply = await handle_dealer_message(db, company, dealer, "asdkjfh")

    assert "BALANCE" in reply.upper()
