"""BriefingService integration test — Phase 5B.

One test that calls a REAL LLM provider end to end, through the fallback
chain (whichever of the 4 configured providers actually succeeds first).
Gated on at least one provider key being configured so the suite stays green
without any key, but runs for real once one is in .env — this is the actual
verification SPEC's build order Step 8 asks for: "integrate the LLM provider,
send to one real distributor, verify every number in the output matches the
snapshot exactly."

    uv run alembic upgrade head
    uv run pytest tests/test_briefing_service.py -v
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from app.models.company import Company
from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceDirection, InvoiceSource, InvoiceStatus
from app.models.morning_briefing import MorningBriefing
from app.services.briefing import find_unverified_amounts, generate_briefing
from app.services.query_menu import MENU_PROMPT
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import has_any_llm_key_configured

pytestmark = pytest.mark.skipif(
    not has_any_llm_key_configured(),
    reason="No LLM provider key configured — skipping real API call",
)


def _unique_phone() -> str:
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


async def _make_company(db: AsyncSession) -> uuid.UUID:
    company = Company(
        business_name="Briefing Test Co",
        owner_name="Owner",
        whatsapp_number=_unique_phone(),
        opening_balance=Decimal("184000.00"),
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company.id


@pytest.mark.asyncio
async def test_generate_briefing_real_api_call(db: AsyncSession) -> None:
    company_id = await _make_company(db)
    dealer = Dealer(company_id=company_id, name="XYZ Traders", credit_limit=Decimal("10000.00"))
    db.add(dealer)
    await db.commit()
    await db.refresh(dealer)

    invoice = Invoice(
        company_id=company_id,
        invoice_number="INV-BRIEF-1",
        direction=InvoiceDirection.receivable,
        dealer_id=dealer.id,
        invoice_date=date.today() - timedelta(days=30),
        due_date=date.today() - timedelta(days=20),
        subtotal=Decimal("42000.00"),
        gst_amount=Decimal("0.00"),
        total_amount=Decimal("42000.00"),
        status=InvoiceStatus.Pending,
        source=InvoiceSource.csv_import,
    )
    db.add(invoice)
    await db.commit()

    briefing = await generate_briefing(db, company_id)

    assert isinstance(briefing, MorningBriefing)
    assert briefing.generated_text.strip() != ""
    lowered = briefing.generated_text.lower()
    assert "cash" in lowered
    assert "action" in lowered or "attention" in lowered
    # Phase 8 — every briefing ends with the numbered-menu discovery hint.
    assert briefing.generated_text.endswith(MENU_PROMPT)

    # Re-derive the same traceability check the endpoint uses — the real
    # response should mention only figures present in the source payload.
    unverified = find_unverified_amounts(briefing.generated_text, briefing.snapshot_json)
    assert unverified == [], f"The model mentioned untraceable amounts: {unverified}"
