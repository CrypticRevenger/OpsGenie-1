"""Schema integration tests — Phase 1.

These tests require a live PostgreSQL database with migrations applied.
Before running, start Postgres and apply migrations:

    docker compose -f docker/docker-compose.yml up -d postgres
    uv run alembic upgrade head
    uv run pytest tests/test_schema.py -v
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

import pytest
from app.models.company import Company
from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceDirection
from app.models.payment import Payment
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

# ── Infrastructure checks ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_all_13_tables_exist(db: AsyncSession) -> None:
    """Every table defined in the TDD schema must be present after migration."""
    result = await db.execute(
        text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
        """)
    )
    tables = {row[0] for row in result}
    expected = {
        "companies",
        "dealers",
        "suppliers",
        "products",
        "invoices",
        "invoice_items",
        "payments",
        "cash_snapshots",
        "business_events",
        "activity_timelines",
        "morning_briefings",
        "import_logs",
        "notification_logs",
    }
    missing = expected - tables
    assert not missing, f"Missing tables after migration: {missing}"


@pytest.mark.asyncio
async def test_invoice_status_enum_values(db: AsyncSession) -> None:
    """InvoiceStatus PostgreSQL enum must contain exactly the values from the TDD."""
    result = await db.execute(
        text("""
            SELECT e.enumlabel
            FROM pg_enum e
            JOIN pg_type t ON e.enumtypid = t.oid
            WHERE t.typname = 'invoicestatus'
            ORDER BY e.enumsortorder
        """)
    )
    values = [row[0] for row in result]
    assert values == ["Draft", "Sent", "Pending", "Partially_Paid", "Paid", "Overdue", "Cancelled"]


@pytest.mark.asyncio
async def test_foreign_key_constraints_exist(db: AsyncSession) -> None:
    """Core tables must have FK constraints declared in the migration."""
    result = await db.execute(
        text("""
            SELECT COUNT(*)
            FROM information_schema.table_constraints
            WHERE constraint_type = 'FOREIGN KEY'
              AND table_name IN (
                'dealers', 'suppliers', 'invoices',
                'payments', 'invoice_items', 'business_events'
              )
        """)
    )
    count = result.scalar_one()
    # At minimum one FK per table listed above
    assert count >= 6, f"Expected ≥6 FK constraints, found {count}"


@pytest.mark.asyncio
async def test_append_only_tables_have_no_updated_at(db: AsyncSession) -> None:
    """business_events and activity_timelines must NOT have an updated_at column."""
    result = await db.execute(
        text("""
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_name IN ('business_events', 'activity_timelines')
              AND column_name = 'updated_at'
        """)
    )
    rows = result.fetchall()
    assert rows == [], (
        "Append-only tables must not have updated_at: "
        + ", ".join(f"{r[0]}.{r[1]}" for r in rows)
    )


# ── ORM relationship chain ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_orm_relationship_chain(db: AsyncSession) -> None:
    """Company → Dealer → Invoice → Payment chain loads correctly via ORM.

    This validates:
    - FK constraints are active (insert succeeds in order)
    - SQLAlchemy relationships with back_populates resolve correctly
    - selectinload works across all four hops
    """
    unique_phone = f"+91{uuid.uuid4().int % 10_000_000_000:010d}"

    company = Company(
        business_name="Test Distributor",
        owner_name="Test Owner",
        whatsapp_number=unique_phone,
        opening_balance=Decimal("200000"),
    )
    db.add(company)
    await db.flush()  # obtain company.id before referencing it below

    dealer = Dealer(company_id=company.id, name="Test Dealer", phone="+910000000001")
    db.add(dealer)
    await db.flush()

    invoice = Invoice(
        company_id=company.id,
        invoice_number="INV-SCHEMA-001",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer.id,
        invoice_date=datetime.date.today(),
        due_date=datetime.date.today() + datetime.timedelta(days=14),
        subtotal=Decimal("10000"),
        gst_amount=Decimal("500"),
        total_amount=Decimal("10500"),
    )
    db.add(invoice)
    await db.flush()

    payment = Payment(
        company_id=company.id,
        invoice_id=invoice.id,
        amount=Decimal("10500"),
        payment_date=datetime.date.today(),
    )
    db.add(payment)
    await db.commit()

    # Reload with eager relationships to verify the full chain
    stmt = (
        select(Company)
        .where(Company.id == company.id)
        .options(
            selectinload(Company.dealers),
            selectinload(Company.invoices).options(selectinload(Invoice.payments)),
            selectinload(Company.payments),
        )
    )
    result = await db.execute(stmt)
    loaded = result.scalar_one()

    assert loaded.business_name == "Test Distributor"
    assert len(loaded.dealers) == 1
    assert loaded.dealers[0].name == "Test Dealer"
    assert len(loaded.invoices) == 1
    assert loaded.invoices[0].invoice_number == "INV-SCHEMA-001"
    assert len(loaded.invoices[0].payments) == 1
    assert loaded.invoices[0].payments[0].amount == Decimal("10500")
    assert len(loaded.payments) == 1
