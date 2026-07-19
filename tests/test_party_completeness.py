"""party_completeness tests — the "which dealers/suppliers are missing
phone/credit days" query behind onboarding's import-path backfill flow (see
app/services/onboarding_flow.py) and the incomplete_party_data briefing
reminder (see app/services/recommendations.py).

Requires postgres running with migrations applied:

    uv run alembic upgrade head
    uv run pytest tests/test_party_completeness.py -v
"""

from __future__ import annotations

import uuid

import pytest
from app.models.company import Company
from app.models.dealer import Dealer
from app.models.supplier import Supplier
from app.services.party_completeness import count_parties_missing_fields, parties_missing_fields
from sqlalchemy.ext.asyncio import AsyncSession


def _unique_phone() -> str:
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


async def _make_company(db: AsyncSession) -> uuid.UUID:
    company = Company(
        business_name="Completeness Test Co", owner_name="Owner", whatsapp_number=_unique_phone()
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company.id


@pytest.mark.asyncio
async def test_dealer_with_only_name_counts_as_missing(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    db.add(Dealer(company_id=company_id, name="Ram Traders"))
    await db.commit()

    assert await count_parties_missing_fields(db, Dealer, company_id) == 1
    missing = await parties_missing_fields(db, Dealer, company_id)
    assert [d.name for d in missing] == ["Ram Traders"]


@pytest.mark.asyncio
async def test_dealer_with_both_fields_set_does_not_count(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    db.add(
        Dealer(
            company_id=company_id,
            name="Ram Traders",
            phone="+919876543210",
            payment_terms_days=15,
        )
    )
    await db.commit()

    assert await count_parties_missing_fields(db, Dealer, company_id) == 0
    assert await parties_missing_fields(db, Dealer, company_id) == []


@pytest.mark.asyncio
async def test_dealer_with_only_one_field_still_counts(db: AsyncSession) -> None:
    """OR, not AND — a dealer answered for phone but never credit days (or
    vice versa) is still incomplete, not "good enough"."""
    company_id = await _make_company(db)
    db.add(Dealer(company_id=company_id, name="Phone Only", phone="+919876543210"))
    db.add(Dealer(company_id=company_id, name="Credit Only", payment_terms_days=15))
    await db.commit()

    assert await count_parties_missing_fields(db, Dealer, company_id) == 2


@pytest.mark.asyncio
async def test_missing_list_is_name_ordered(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    db.add(Dealer(company_id=company_id, name="Zebra Traders"))
    db.add(Dealer(company_id=company_id, name="Annapurna Stores"))
    db.add(Dealer(company_id=company_id, name="Maa Tarini Traders"))
    await db.commit()

    missing = await parties_missing_fields(db, Dealer, company_id)
    assert [d.name for d in missing] == ["Annapurna Stores", "Maa Tarini Traders", "Zebra Traders"]


@pytest.mark.asyncio
async def test_dealer_and_supplier_counts_are_independent(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    db.add(Dealer(company_id=company_id, name="Incomplete Dealer"))
    db.add(
        Supplier(
            company_id=company_id,
            name="Complete Supplier",
            phone="+919988776655",
            payment_terms_days=30,
        )
    )
    await db.commit()

    assert await count_parties_missing_fields(db, Dealer, company_id) == 1
    assert await count_parties_missing_fields(db, Supplier, company_id) == 0


@pytest.mark.asyncio
async def test_no_parties_returns_zero_and_empty(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    assert await count_parties_missing_fields(db, Dealer, company_id) == 0
    assert await parties_missing_fields(db, Dealer, company_id) == []
