"""Deterministic WhatsApp report formatters — no LLM involved.

Direct function-level tests against app/services/instant_reports.py (fast,
no HTTP/webhook overhead) — the webhook-wiring itself (menu-row tap /
keyword -> _INSTANT_COMMANDS -> these functions, bypassing the LLM
assistant entirely) is covered by a few smoke tests in
tests/test_webhooks_whatsapp.py instead of repeating per command here.

    uv run alembic upgrade head
    uv run pytest tests/test_instant_reports.py -v
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from app.models.company import Company
from app.models.dealer import Dealer
from app.models.faq import FAQ
from app.models.invoice import Invoice, InvoiceDirection, InvoiceSource, InvoiceStatus
from app.models.notification_log import NotificationLog
from app.models.payment import Payment, PaymentSource
from app.models.product import Product
from app.models.supplier import Supplier
from app.services import instant_reports
from app.services.snapshot import business_now
from sqlalchemy.ext.asyncio import AsyncSession


def _unique_number() -> str:
    return f"+919{uuid.uuid4().int % 1_000_000_000:09d}"


async def _fresh_company(db: AsyncSession) -> Company:
    company = Company(
        business_name="Instant Reports Co", owner_name="Owner", whatsapp_number=_unique_number()
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company


@pytest.mark.asyncio
async def test_empty_states_never_crash(db: AsyncSession) -> None:
    """A brand-new company with no data at all — every formatter must
    degrade to a friendly "nothing yet" message, never raise.
    """
    company = await _fresh_company(db)

    expectations = [
        (instant_reports.cash_position_reply, "cash"),
        (instant_reports.business_summary_reply, "summary"),
        # A brand-new company always gets a "no data imported yet" priority
        # action (build_recommendations' own rule) — never truly empty.
        (instant_reports.priorities_reply, "priorities"),
        (instant_reports.overdue_dealers_reply, "no overdue"),
        (instant_reports.upcoming_collections_reply, "no collections"),
        (instant_reports.upcoming_payments_reply, "no supplier payments"),
        (instant_reports.all_dealers_reply, "don't have any dealers"),
        (instant_reports.all_suppliers_reply, "don't have any suppliers"),
        (instant_reports.top_debtors_reply, "no dealer"),
        (instant_reports.top_creditors_reply, "don't currently owe"),
        (instant_reports.recent_inventory_reply, "don't have any products"),
        (instant_reports.all_inventory_reply, "don't have any products"),
        (instant_reports.faqs_reply, "don't have any saved policy"),
        (instant_reports.recent_invoices_reply, "don't have any invoices"),
        (instant_reports.all_invoices_reply, "don't have any invoices"),
        (instant_reports.recent_payments_reply, "don't have any payments"),
        (instant_reports.all_payments_reply, "don't have any payments"),
        (instant_reports.trend_report_reply, "not enough dealer order activity"),
    ]
    for fn, expected_substring in expectations:
        reply = await fn(db, company)
        assert expected_substring in reply.lower(), f"{fn.__name__}: {reply!r}"


@pytest.mark.asyncio
async def test_all_dealers_and_top_debtors_show_real_outstanding(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    dealer = Dealer(company_id=company.id, name="Ram Traders", phone="9876543210")
    db.add(dealer)
    await db.flush()
    db.add(
        Invoice(
            company_id=company.id,
            invoice_number="INV-1",
            direction=InvoiceDirection.receivable,
            dealer_id=dealer.id,
            invoice_date=date(2026, 1, 1),
            due_date=date(2026, 1, 1),
            subtotal=Decimal("20000.00"),
            gst_amount=Decimal("0.00"),
            total_amount=Decimal("20000.00"),
            status=InvoiceStatus.Pending,
            source=InvoiceSource.csv_import,
        )
    )
    await db.commit()

    dealers_reply = await instant_reports.all_dealers_reply(db, company)
    assert "Ram Traders" in dealers_reply
    assert "9876543210" in dealers_reply
    assert "20,000" in dealers_reply

    debtors_reply = await instant_reports.top_debtors_reply(db, company)
    assert "Ram Traders" in debtors_reply
    assert "20,000" in debtors_reply


@pytest.mark.asyncio
async def test_all_suppliers_and_top_creditors_show_real_outstanding(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    supplier = Supplier(company_id=company.id, name="ABC Pharma", phone="9123456789")
    db.add(supplier)
    await db.flush()
    db.add(
        Invoice(
            company_id=company.id,
            invoice_number="INV-P1",
            direction=InvoiceDirection.payable,
            supplier_id=supplier.id,
            invoice_date=date(2026, 1, 1),
            due_date=date(2026, 1, 1),
            subtotal=Decimal("15000.00"),
            gst_amount=Decimal("0.00"),
            total_amount=Decimal("15000.00"),
            status=InvoiceStatus.Pending,
            source=InvoiceSource.csv_import,
        )
    )
    await db.commit()

    suppliers_reply = await instant_reports.all_suppliers_reply(db, company)
    assert "ABC Pharma" in suppliers_reply
    assert "9123456789" in suppliers_reply
    assert "15,000" in suppliers_reply

    creditors_reply = await instant_reports.top_creditors_reply(db, company)
    assert "ABC Pharma" in creditors_reply
    assert "15,000" in creditors_reply


@pytest.mark.asyncio
async def test_inventory_shows_real_products(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    db.add(
        Product(
            company_id=company.id,
            name="Rice",
            unit="kg",
            selling_price=Decimal("400.00"),
            purchase_price=Decimal("300.00"),
            stock_quantity=Decimal("100"),
        )
    )
    db.add(
        Product(
            company_id=company.id,
            name="Dal",
            unit=None,
            selling_price=None,
            stock_quantity=Decimal("0"),
        )
    )
    await db.commit()

    recent_reply = await instant_reports.recent_inventory_reply(db, company)
    assert "Rice" in recent_reply
    assert "kg" in recent_reply
    assert "400" in recent_reply
    assert "Dal" in recent_reply
    assert "price not set" in recent_reply

    all_reply = await instant_reports.all_inventory_reply(db, company)
    assert "Rice" in all_reply
    assert "Dal" in all_reply


@pytest.mark.asyncio
async def test_recent_inventory_sorts_newest_first_and_caps(
    db: AsyncSession, monkeypatch
) -> None:
    """"Recent Inventory" must sort by recency (most recently added product
    first) and cap at _RECENT_LIST_CAP, reporting the true total — "All
    Inventory" then shows every product, same sort order, higher cap.
    """
    monkeypatch.setattr(instant_reports, "_RECENT_LIST_CAP", 2)
    company = await _fresh_company(db)
    # Postgres's now() (created_at's server_default) returns one value per
    # transaction — a separate commit per product is what actually gives
    # each row a distinct, later created_at (a single flush() per row within
    # one transaction would tie them all, same as a real bulk-add message).
    for name in ["Oldest", "Middle", "Newest"]:
        db.add(Product(company_id=company.id, name=name, stock_quantity=Decimal("10")))
        await db.commit()

    recent_reply = await instant_reports.recent_inventory_reply(db, company)
    assert "Recent Inventory (2 of 3):" in recent_reply
    assert "Newest" in recent_reply
    assert "Middle" in recent_reply
    assert "Oldest" not in recent_reply  # capped out — older than the top 2
    # Newest must be listed before Middle (sorted newest-first).
    assert recent_reply.index("Newest") < recent_reply.index("Middle")

    all_reply = await instant_reports.all_inventory_reply(db, company)
    assert "All Inventory (3):" in all_reply
    assert "Oldest" in all_reply
    assert all_reply.index("Newest") < all_reply.index("Middle") < all_reply.index("Oldest")


@pytest.mark.asyncio
async def test_faqs_shows_real_qa_pairs(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    db.add(FAQ(company_id=company.id, question="What are delivery days?", answer="Mon-Sat"))
    await db.commit()

    reply = await instant_reports.faqs_reply(db, company)
    assert "What are delivery days?" in reply
    assert "Mon-Sat" in reply


@pytest.mark.asyncio
async def test_invoices_reply_lists_all_and_targets_right_ones(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    dealer = Dealer(company_id=company.id, name="Matru")
    db.add(dealer)
    await db.flush()
    db.add(
        Invoice(
            company_id=company.id,
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
            company_id=company.id,
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

    reply = await instant_reports.all_invoices_reply(db, company)
    assert "INV-OLD" in reply
    assert "INV-NEW" in reply
    assert "All Invoices (2):" in reply
    assert "…and" not in reply  # under the cap, no truncation note


@pytest.mark.asyncio
async def test_recent_invoices_reply_caps_and_all_invoices_shows_everything(
    db: AsyncSession, monkeypatch
) -> None:
    """A party with more invoices than the "recent" cap must still report
    the true total (not the capped batch size) in the "…and N more" note —
    "all invoices" (a higher cap) then shows the rest.
    """
    monkeypatch.setattr(instant_reports, "_RECENT_LIST_CAP", 2)
    company = await _fresh_company(db)
    dealer = Dealer(company_id=company.id, name="Matru")
    db.add(dealer)
    await db.flush()
    for i in range(5):
        db.add(
            Invoice(
                company_id=company.id,
                invoice_number=f"INV-{i}",
                direction=InvoiceDirection.receivable,
                dealer_id=dealer.id,
                invoice_date=date(2026, 1, 1) + timedelta(days=i),
                due_date=date(2026, 1, 1) + timedelta(days=i),
                subtotal=Decimal("1000.00"),
                gst_amount=Decimal("0.00"),
                total_amount=Decimal("1000.00"),
                status=InvoiceStatus.Pending,
                source=InvoiceSource.csv_import,
            )
        )
    await db.commit()

    recent_reply = await instant_reports.recent_invoices_reply(db, company)
    assert "Recent Invoices (2 of 5):" in recent_reply
    assert "…and 3 more" in recent_reply
    assert "reply 'all invoices'" in recent_reply

    all_reply = await instant_reports.all_invoices_reply(db, company)
    assert "All Invoices (5):" in all_reply
    assert "…and" not in all_reply
    for i in range(5):
        assert f"INV-{i}" in all_reply


@pytest.mark.asyncio
async def test_payments_reply_lists_real_payments(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    dealer = Dealer(company_id=company.id, name="Matru")
    db.add(dealer)
    await db.flush()
    invoice = Invoice(
        company_id=company.id,
        invoice_number="INV-1",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer.id,
        invoice_date=date(2026, 1, 1),
        due_date=date(2026, 1, 1),
        subtotal=Decimal("30000.00"),
        gst_amount=Decimal("0.00"),
        total_amount=Decimal("30000.00"),
        status=InvoiceStatus.Paid,
        source=InvoiceSource.csv_import,
    )
    db.add(invoice)
    await db.flush()
    db.add(
        Payment(
            company_id=company.id,
            invoice_id=invoice.id,
            amount=Decimal("30000.00"),
            payment_date=date(2026, 1, 15),
            source=PaymentSource.whatsapp,
        )
    )
    await db.commit()

    recent_reply = await instant_reports.recent_payments_reply(db, company)
    assert "30,000" in recent_reply
    assert "INV-1" in recent_reply
    assert "2026-01-15" in recent_reply

    all_reply = await instant_reports.all_payments_reply(db, company)
    assert "30,000" in all_reply
    assert "INV-1" in all_reply


# ── party_balance_reply / stock_item_reply ──────────────────────────────────


@pytest.mark.asyncio
async def test_party_balance_reply_finds_dealer(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    dealer = Dealer(company_id=company.id, name="Ram Traders")
    db.add(dealer)
    await db.flush()
    db.add(
        Invoice(
            company_id=company.id,
            invoice_number="INV-1",
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

    reply = await instant_reports.party_balance_reply(db, company, "ram")
    assert "Ram Traders" in reply
    assert "owes you" in reply
    assert "25,000" in reply


@pytest.mark.asyncio
async def test_party_balance_reply_no_match(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    reply = await instant_reports.party_balance_reply(db, company, "Nobody")
    assert "no dealer or supplier found" in reply.lower()


@pytest.mark.asyncio
async def test_stock_item_reply_finds_product(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    db.add(
        Product(
            company_id=company.id,
            name="Rice",
            unit="kg",
            selling_price=Decimal("400.00"),
            stock_quantity=Decimal("200"),
        )
    )
    await db.commit()

    reply = await instant_reports.stock_item_reply(db, company, "rice")
    assert "Rice" in reply
    assert "200 kg" in reply  # not "200.0000" — _format_quantity applied
    assert "400" in reply


@pytest.mark.asyncio
async def test_stock_item_reply_no_match(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    reply = await instant_reports.stock_item_reply(db, company, "nonexistent")
    assert "couldn't find" in reply.lower()


# ── try_deterministic_sales_impact ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_sales_impact_single_item(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    db.add(
        Product(
            company_id=company.id,
            name="Rice",
            unit="kg",
            selling_price=Decimal("400.00"),
            purchase_price=Decimal("300.00"),
            stock_quantity=Decimal("200"),
        )
    )
    await db.commit()

    reply = await instant_reports.try_deterministic_sales_impact(
        db, company, "if I sell 50 kg of rice"
    )
    assert reply is not None
    # Regression check: whole-quantity Decimals must render as "50", not "5"
    # (_format_quantity's rstrip("0") mangles un-quantized bare Decimals).
    assert "50 Rice" in reply
    assert "150 left in stock" in reply
    assert "revenue" in reply.lower()
    assert "20,000" in reply
    assert "profit" in reply.lower()
    assert "5,000" in reply


@pytest.mark.asyncio
async def test_sales_impact_multi_item_mixed_cost_data(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    db.add(
        Product(
            company_id=company.id,
            name="Rice",
            unit="kg",
            selling_price=Decimal("400.00"),
            purchase_price=Decimal("300.00"),
            stock_quantity=Decimal("200"),
        )
    )
    db.add(
        Product(
            company_id=company.id,
            name="Dal",
            unit="kg",
            selling_price=Decimal("450.00"),
            stock_quantity=Decimal("100"),
        )
    )
    await db.commit()

    reply = await instant_reports.try_deterministic_sales_impact(
        db, company, "if I sell 50 rice and 20 dal, what's my profit?"
    )
    assert reply is not None
    assert "50 Rice" in reply
    assert "20 Dal" in reply
    assert "no purchase price on file for Dal" in reply


@pytest.mark.asyncio
async def test_sales_impact_no_trigger_phrase_returns_none(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    result = await instant_reports.try_deterministic_sales_impact(
        db, company, "what is my cash position"
    )
    assert result is None


@pytest.mark.asyncio
async def test_sales_impact_unresolvable_product_returns_none(db: AsyncSession) -> None:
    """No catalogue match for the parsed name — must fall back to the LLM
    path (return None), never claim a fake product exists.
    """
    company = await _fresh_company(db)
    db.add(
        Product(
            company_id=company.id, name="Rice", stock_quantity=Decimal("100"), unit="kg"
        )
    )
    await db.commit()

    result = await instant_reports.try_deterministic_sales_impact(
        db, company, "if I sell 50 kg of quinoa"
    )
    assert result is None


async def _make_trend_invoice(
    db: AsyncSession,
    company: Company,
    dealer: Dealer,
    *,
    total: Decimal,
    invoice_date: date,
) -> Invoice:
    invoice = Invoice(
        company_id=company.id,
        invoice_number=f"INV-{uuid.uuid4().hex[:10]}",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer.id,
        invoice_date=invoice_date,
        due_date=invoice_date + timedelta(days=14),
        subtotal=total,
        gst_amount=Decimal("0.00"),
        total_amount=total,
        status=InvoiceStatus.Pending,
        source=InvoiceSource.csv_import,
    )
    db.add(invoice)
    await db.commit()
    return invoice


@pytest.mark.asyncio
async def test_trend_report_reply_shows_rising_dealer_and_cash_headline(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    today = business_now(company.timezone).date()
    dealer = Dealer(company_id=company.id, name="Rising Traders")
    db.add(dealer)
    await db.flush()

    # Current 30d window: 2 orders totaling 5000 (clears the evidence floor).
    await _make_trend_invoice(db, company, dealer, total=Decimal("3000"), invoice_date=today)
    await _make_trend_invoice(
        db, company, dealer, total=Decimal("2000"), invoice_date=today - timedelta(days=3)
    )
    # Prior 30d window: 1 order totaling 500 -> a clear riser.
    await _make_trend_invoice(
        db, company, dealer, total=Decimal("500"), invoice_date=today - timedelta(days=35)
    )

    reply = await instant_reports.trend_report_reply(db, company)
    assert "Rising Traders" in reply
    assert "Dealer Trend" in reply
    assert "Cash Trend" in reply


# ── delivery_status_reply ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delivery_status_empty_state(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    reply = await instant_reports.delivery_status_reply(db, company)
    assert "no invoices or broadcasts" in reply.lower()


@pytest.mark.asyncio
async def test_delivery_status_shows_invoice_send_with_dealer_name(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    dealer = Dealer(company_id=company.id, name="Ram Traders", phone="9876543210")
    db.add(dealer)
    await db.flush()
    db.add(
        NotificationLog(
            company_id=company.id,
            notification_type="invoice_document",
            recipient_whatsapp=dealer.phone,
            message_text="Invoice INV-000123 PDF",
            whatsapp_message_id="wamid.abc",
            delivery_status="read",
            sent_at=datetime.now(UTC),
        )
    )
    await db.commit()

    reply = await instant_reports.delivery_status_reply(db, company)
    assert "Invoice INV-000123" in reply
    assert "Ram Traders" in reply
    assert "read" in reply.lower()


@pytest.mark.asyncio
async def test_delivery_status_groups_broadcast_by_message_text(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    now = datetime.now(UTC)
    statuses = ["delivered", "delivered", "sent"]
    for i, delivery_status in enumerate(statuses):
        db.add(
            NotificationLog(
                company_id=company.id,
                notification_type="marketing_broadcast",
                recipient_whatsapp=f"98765432{i:02d}",
                message_text="Diwali offer — 10% off this week!",
                whatsapp_message_id=f"wamid.broadcast{i}",
                delivery_status=delivery_status,
                sent_at=now,
            )
        )
    await db.commit()

    reply = await instant_reports.delivery_status_reply(db, company)
    assert "Broadcast" in reply
    assert "3 dealers" in reply
    assert "2 delivered" in reply
    assert "1 sent" in reply


@pytest.mark.asyncio
async def test_delivery_status_ignores_other_notification_types(db: AsyncSession) -> None:
    """follow_up_sent/supplier_payment_reminder/etc. are automated nudges to
    the distributor themselves, not a message they explicitly triggered to a
    dealer/supplier — must never show up here.
    """
    company = await _fresh_company(db)
    db.add(
        NotificationLog(
            company_id=company.id,
            notification_type="follow_up_sent",
            recipient_whatsapp=company.whatsapp_number,
            message_text="Reminder: follow up with a dealer",
            delivery_status="sent",
            sent_at=datetime.now(UTC),
        )
    )
    await db.commit()

    reply = await instant_reports.delivery_status_reply(db, company)
    assert "no invoices or broadcasts" in reply.lower()


@pytest.mark.asyncio
async def test_delivery_status_orders_most_recent_batch_first(db: AsyncSession) -> None:
    company = await _fresh_company(db)
    dealer = Dealer(company_id=company.id, name="Old Traders", phone="9111111111")
    db.add(dealer)
    await db.flush()
    now = datetime.now(UTC)
    db.add(
        NotificationLog(
            company_id=company.id,
            notification_type="invoice_document",
            recipient_whatsapp=dealer.phone,
            message_text="Invoice INV-OLD PDF",
            delivery_status="delivered",
            sent_at=now - timedelta(days=2),
        )
    )
    db.add(
        NotificationLog(
            company_id=company.id,
            notification_type="invoice_document",
            recipient_whatsapp=dealer.phone,
            message_text="Invoice INV-NEW PDF",
            delivery_status="sent",
            sent_at=now,
        )
    )
    await db.commit()

    reply = await instant_reports.delivery_status_reply(db, company)
    assert reply.index("INV-NEW") < reply.index("INV-OLD")
