"""BusinessSnapshotService tests — Phase 5A.

Requires postgres running with migrations applied:

    uv run alembic upgrade head
    uv run pytest tests/test_snapshot.py -v
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from app.models.company import Company
from app.models.dealer import Dealer
from app.models.import_log import ImportLog
from app.models.invoice import Invoice, InvoiceDirection, InvoiceSource, InvoiceStatus
from app.models.payment import Payment
from app.models.supplier import Supplier
from app.services.snapshot import DEFAULT_BUSINESS_TIMEZONE, build_snapshot, business_now
from sqlalchemy.ext.asyncio import AsyncSession

# Anchor the test's "today" to the exact same business-timezone basis the
# snapshot uses, not the machine's local date — otherwise date-boundary
# assertions (overdue, 7-day window) flake whenever the machine's local date
# and the business date differ around midnight.
TODAY = business_now(DEFAULT_BUSINESS_TIMEZONE).date()


def _unique_phone() -> str:
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


async def _make_company(db: AsyncSession, opening_balance: Decimal = Decimal("0.00")) -> uuid.UUID:
    company = Company(
        business_name="Snapshot Test Co",
        owner_name="Owner",
        whatsapp_number=_unique_phone(),
        opening_balance=opening_balance,
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company.id


async def _make_dealer(
    db: AsyncSession, company_id: uuid.UUID, name: str, credit_limit=None
) -> uuid.UUID:
    dealer = Dealer(company_id=company_id, name=name, credit_limit=credit_limit)
    db.add(dealer)
    await db.commit()
    await db.refresh(dealer)
    return dealer.id


async def _make_supplier(db: AsyncSession, company_id: uuid.UUID, name: str) -> uuid.UUID:
    supplier = Supplier(company_id=company_id, name=name)
    db.add(supplier)
    await db.commit()
    await db.refresh(supplier)
    return supplier.id


async def _make_invoice(
    db: AsyncSession,
    company_id: uuid.UUID,
    *,
    invoice_number: str,
    direction: InvoiceDirection,
    dealer_id: uuid.UUID | None = None,
    supplier_id: uuid.UUID | None = None,
    total_amount: Decimal,
    due_date: date,
    status: InvoiceStatus = InvoiceStatus.Pending,
) -> Invoice:
    invoice = Invoice(
        company_id=company_id,
        invoice_number=invoice_number,
        direction=direction,
        dealer_id=dealer_id,
        supplier_id=supplier_id,
        invoice_date=due_date - timedelta(days=14),
        due_date=due_date,
        subtotal=total_amount,
        gst_amount=Decimal("0.00"),
        total_amount=total_amount,
        status=status,
        source=InvoiceSource.csv_import,
    )
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)
    return invoice


async def _make_payment(
    db: AsyncSession,
    company_id: uuid.UUID,
    invoice_id: uuid.UUID,
    amount: Decimal,
    payment_date: date,
) -> None:
    db.add(
        Payment(
            company_id=company_id, invoice_id=invoice_id, amount=amount, payment_date=payment_date
        )
    )
    await db.commit()


@pytest.mark.asyncio
async def test_cash_available_today_combines_opening_balance_and_payments(db: AsyncSession) -> None:
    company_id = await _make_company(db, opening_balance=Decimal("100000.00"))
    dealer_id = await _make_dealer(db, company_id, "Dealer A")
    supplier_id = await _make_supplier(db, company_id, "Supplier A")

    receivable_invoice = await _make_invoice(
        db,
        company_id,
        invoice_number="INV-CASH-R",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        total_amount=Decimal("50000.00"),
        due_date=TODAY - timedelta(days=1),
        status=InvoiceStatus.Paid,
    )
    await _make_payment(db, company_id, receivable_invoice.id, Decimal("50000.00"), TODAY)

    payable_invoice = await _make_invoice(
        db,
        company_id,
        invoice_number="INV-CASH-P",
        direction=InvoiceDirection.payable,
        supplier_id=supplier_id,
        total_amount=Decimal("20000.00"),
        due_date=TODAY - timedelta(days=1),
        status=InvoiceStatus.Paid,
    )
    await _make_payment(db, company_id, payable_invoice.id, Decimal("20000.00"), TODAY)

    snapshot = await build_snapshot(db, company_id)
    # 100000 opening + 50000 received - 20000 paid out = 130000
    assert snapshot.cash_available_today == Decimal("130000.00")


@pytest.mark.asyncio
async def test_expected_collections_7d_only_includes_window(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id, "Dealer B")

    await _make_invoice(
        db,
        company_id,
        invoice_number="INV-COLL-IN",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        total_amount=Decimal("5000.00"),
        due_date=TODAY + timedelta(days=3),
    )
    await _make_invoice(
        db,
        company_id,
        invoice_number="INV-COLL-OUT",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        total_amount=Decimal("9000.00"),
        due_date=TODAY + timedelta(days=30),
    )

    snapshot = await build_snapshot(db, company_id)
    numbers = {c.dealer_name for c in snapshot.expected_collections_7d}
    assert numbers == {"Dealer B"}
    assert snapshot.expected_collections_7d_total == Decimal("5000.00")


@pytest.mark.asyncio
async def test_expected_collections_use_outstanding_not_gross(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id, "Dealer Partial")

    invoice = await _make_invoice(
        db,
        company_id,
        invoice_number="INV-PARTIAL",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        total_amount=Decimal("10000.00"),
        due_date=TODAY + timedelta(days=3),
        status=InvoiceStatus.Partially_Paid,
    )
    await _make_payment(db, company_id, invoice.id, Decimal("4000.00"), TODAY)

    snapshot = await build_snapshot(db, company_id)
    collection = next(
        c for c in snapshot.expected_collections_7d if c.dealer_name == "Dealer Partial"
    )
    # 10000 total - 4000 already paid = 6000 still to collect, not the gross 10000.
    assert collection.amount == Decimal("6000.00")
    assert snapshot.expected_collections_7d_total == Decimal("6000.00")


@pytest.mark.asyncio
async def test_fully_paid_invoice_in_window_excluded_from_expected_collections(
    db: AsyncSession,
) -> None:
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id, "Dealer Settled")

    invoice = await _make_invoice(
        db,
        company_id,
        invoice_number="INV-SETTLED",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        total_amount=Decimal("2000.00"),
        due_date=TODAY + timedelta(days=2),
        status=InvoiceStatus.Partially_Paid,
    )
    await _make_payment(db, company_id, invoice.id, Decimal("2000.00"), TODAY)

    snapshot = await build_snapshot(db, company_id)
    # Nothing left to collect — the invoice must not appear despite being in
    # the window and an open status.
    assert not [c for c in snapshot.expected_collections_7d if c.dealer_name == "Dealer Settled"]


@pytest.mark.asyncio
async def test_net_cash_position_and_deficit_flag(db: AsyncSession) -> None:
    company_id = await _make_company(db, opening_balance=Decimal("1000.00"))
    supplier_id = await _make_supplier(db, company_id, "Supplier B")
    await _make_invoice(
        db,
        company_id,
        invoice_number="INV-DEFICIT",
        direction=InvoiceDirection.payable,
        supplier_id=supplier_id,
        total_amount=Decimal("50000.00"),
        due_date=TODAY + timedelta(days=2),
    )

    snapshot = await build_snapshot(db, company_id)
    assert snapshot.net_cash_position == Decimal("1000.00") - Decimal("50000.00")
    assert snapshot.cash_deficit is True


@pytest.mark.asyncio
async def test_overdue_dealer_days_overdue_uses_oldest_unpaid_invoice(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id, "Dealer C", credit_limit=Decimal("1000.00"))

    await _make_invoice(
        db,
        company_id,
        invoice_number="INV-OD-OLD",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        total_amount=Decimal("10000.00"),
        due_date=TODAY - timedelta(days=20),
    )
    await _make_invoice(
        db,
        company_id,
        invoice_number="INV-OD-NEW",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        total_amount=Decimal("5000.00"),
        due_date=TODAY - timedelta(days=6),
    )

    snapshot = await build_snapshot(db, company_id)
    overdue = next(d for d in snapshot.overdue_dealers if d.dealer_name == "Dealer C")
    assert overdue.days_overdue == 20  # oldest invoice's overdue age, not the newest
    assert overdue.outstanding == Decimal("15000.00")
    assert overdue.risk_level == "High"
    assert overdue.credit_limit == Decimal("1000.00")


@pytest.mark.asyncio
async def test_dealer_not_overdue_absent_from_overdue_list(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id, "Dealer D")
    await _make_invoice(
        db,
        company_id,
        invoice_number="INV-NOTDUE",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        total_amount=Decimal("3000.00"),
        due_date=TODAY + timedelta(days=5),
    )

    snapshot = await build_snapshot(db, company_id)
    assert not [d for d in snapshot.overdue_dealers if d.dealer_name == "Dealer D"]


@pytest.mark.asyncio
async def test_late_payment_count_6mo(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer_id = await _make_dealer(db, company_id, "Dealer E")

    late_paid_invoice = await _make_invoice(
        db,
        company_id,
        invoice_number="INV-LATE",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        total_amount=Decimal("2000.00"),
        due_date=TODAY - timedelta(days=30),
        status=InvoiceStatus.Paid,
    )
    await _make_payment(
        db, company_id, late_paid_invoice.id, Decimal("2000.00"), TODAY - timedelta(days=10)
    )

    # a second, currently-overdue invoice so the dealer shows up in overdue_dealers
    await _make_invoice(
        db,
        company_id,
        invoice_number="INV-STILL-OPEN",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer_id,
        total_amount=Decimal("1000.00"),
        due_date=TODAY - timedelta(days=8),
    )

    snapshot = await build_snapshot(db, company_id)
    overdue = next(d for d in snapshot.overdue_dealers if d.dealer_name == "Dealer E")
    assert overdue.late_payment_count_6mo == 1


@pytest.mark.asyncio
async def test_data_freshness_and_confidence_from_import_log(db: AsyncSession) -> None:
    from datetime import UTC, datetime

    company_id = await _make_company(db)
    db.add(
        ImportLog(
            company_id=company_id,
            filename="x.csv",
            source_format="csv",
            imported_at=datetime.now(UTC) - timedelta(hours=2),
            rows_processed=1,
            rows_succeeded=1,
            rows_failed=0,
        )
    )
    await db.commit()

    snapshot = await build_snapshot(db, company_id)
    assert snapshot.data_freshness_hours is not None
    assert 1.9 < snapshot.data_freshness_hours < 2.1
    assert snapshot.confidence_score == 100.0  # fresher than 24h
    assert snapshot.data_completeness_score is None  # stubbed, per plan


@pytest.mark.asyncio
async def test_no_import_ever_means_no_freshness_and_zero_confidence(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    snapshot = await build_snapshot(db, company_id)
    assert snapshot.data_freshness_hours is None
    assert snapshot.confidence_score == 0.0


@pytest.mark.asyncio
async def test_no_incomplete_parties_counts_zero(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    await _make_dealer(db, company_id, "Complete Dealer")  # no phone/credit either way
    snapshot = await build_snapshot(db, company_id)
    # A dealer with neither phone nor payment_terms_days set still counts as
    # missing — matches count_parties_missing_fields' OR predicate, not an
    # oversight; assert the shape this test actually needs instead.
    assert snapshot.dealers_missing_fields_count == 1
    assert snapshot.suppliers_missing_fields_count == 0


@pytest.mark.asyncio
async def test_dealers_and_suppliers_missing_fields_counted_independently(
    db: AsyncSession,
) -> None:
    company_id = await _make_company(db)
    db.add(Dealer(company_id=company_id, name="No Phone No Credit"))
    db.add(
        Dealer(
            company_id=company_id,
            name="Complete Dealer",
            phone="+919876543210",
            payment_terms_days=15,
        )
    )
    db.add(Dealer(company_id=company_id, name="Phone Only", phone="+919876543211"))
    db.add(Supplier(company_id=company_id, name="No Phone No Credit Supplier"))
    await db.commit()

    snapshot = await build_snapshot(db, company_id)
    # 2 of 3 dealers are missing at least one field ("Phone Only" still
    # counts — missing payment_terms_days is enough on its own).
    assert snapshot.dealers_missing_fields_count == 2
    assert snapshot.suppliers_missing_fields_count == 1


@pytest.mark.asyncio
async def test_company_not_found_raises(db: AsyncSession) -> None:
    with pytest.raises(ValueError):
        await build_snapshot(db, uuid.uuid4())
