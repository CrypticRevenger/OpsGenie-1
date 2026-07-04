"""Admin briefing endpoint tests — Phase 5B.

POST tests are skipped unless at least one LLM provider key is configured
(real network call, real cost). GET tests don't need a key — they only read
what's already stored.

    uv run alembic upgrade head
    uv run pytest tests/test_admin_briefing.py -v
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceDirection, InvoiceSource, InvoiceStatus
from app.models.morning_briefing import MorningBriefing
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import has_any_llm_key_configured

requires_api_key = pytest.mark.skipif(
    not has_any_llm_key_configured(),
    reason="No LLM provider key configured — skipping real API call",
)


def _unique_phone() -> str:
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


async def _create_company(client: AsyncClient) -> str:
    resp = await client.post(
        "/admin/companies",
        json={
            "business_name": "Briefing Endpoint Test Co",
            "owner_name": "Owner",
            "whatsapp_number": _unique_phone(),
            "opening_balance": "50000.00",
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@requires_api_key
@pytest.mark.asyncio
async def test_post_briefing_creates_and_stores(client: AsyncClient, db: AsyncSession) -> None:
    company_id = await _create_company(client)
    dealer = Dealer(
        company_id=uuid.UUID(company_id), name="Test Dealer", credit_limit=Decimal("1000.00")
    )
    db.add(dealer)
    await db.commit()
    await db.refresh(dealer)

    invoice = Invoice(
        company_id=uuid.UUID(company_id),
        invoice_number="INV-EP-1",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer.id,
        invoice_date=date.today() - timedelta(days=30),
        due_date=date.today() - timedelta(days=20),
        subtotal=Decimal("5000.00"),
        gst_amount=Decimal("0.00"),
        total_amount=Decimal("5000.00"),
        status=InvoiceStatus.Pending,
        source=InvoiceSource.csv_import,
    )
    db.add(invoice)
    await db.commit()

    resp = await client.post(f"/admin/companies/{company_id}/briefing")
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["company_id"] == company_id
    assert data["generated_text"].strip() != ""


@pytest.mark.asyncio
async def test_post_briefing_unknown_company_404(client: AsyncClient) -> None:
    resp = await client.post(f"/admin/companies/{uuid.uuid4()}/briefing")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_briefing_404_when_none_generated_yet(client: AsyncClient) -> None:
    company_id = await _create_company(client)
    resp = await client.get(f"/admin/companies/{company_id}/briefing")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_briefing_returns_most_recent(client: AsyncClient, db: AsyncSession) -> None:
    company_id = await _create_company(client)

    older = MorningBriefing(
        company_id=uuid.UUID(company_id),
        generated_text="Older briefing",
        snapshot_json={"cash_position": {"available_today": "1000.00"}},
        confidence_score=Decimal("90.00"),
        data_freshness_hours=2,
    )
    db.add(older)
    await db.commit()

    newer = MorningBriefing(
        company_id=uuid.UUID(company_id),
        generated_text="Newer briefing",
        snapshot_json={"cash_position": {"available_today": "2000.00"}},
        confidence_score=Decimal("95.00"),
        data_freshness_hours=1,
    )
    db.add(newer)
    await db.commit()

    resp = await client.get(f"/admin/companies/{company_id}/briefing")
    assert resp.status_code == 200
    assert resp.json()["generated_text"] == "Newer briefing"


@pytest.mark.asyncio
async def test_get_briefing_unknown_company_404(client: AsyncClient) -> None:
    resp = await client.get(f"/admin/companies/{uuid.uuid4()}/briefing")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_briefing_surfaces_unverified_amounts(
    client: AsyncClient, db: AsyncSession
) -> None:
    company_id = await _create_company(client)
    briefing = MorningBriefing(
        company_id=uuid.UUID(company_id),
        generated_text="Available: ₹1000.00 today. Also ₹999999 mystery amount.",
        snapshot_json={"cash_position": {"available_today": "1000.00"}},
        confidence_score=Decimal("90.00"),
        data_freshness_hours=1,
    )
    db.add(briefing)
    await db.commit()

    resp = await client.get(f"/admin/companies/{company_id}/briefing")
    assert resp.status_code == 200
    assert "999999" in resp.json()["unverified_amounts"]
