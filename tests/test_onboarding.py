"""Public self-serve onboarding tests.

Onboarding is fully public now — no access code. onboarding_enabled defaults
True, so these run against the live .env unless a test explicitly flips it.

    uv run alembic upgrade head
    uv run pytest tests/test_onboarding.py -v
"""

from __future__ import annotations

import uuid

import pytest
from app.core.config import get_settings
from app.models.company import Company
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _unique_number() -> str:
    # A valid Indian mobile (national part starts with 9, 10 digits) so it
    # passes libphonenumber's is_valid_number check in the onboarding path.
    return f"+919{uuid.uuid4().int % 1_000_000_000:09d}"


@pytest.mark.asyncio
async def test_onboard_page_served(client: AsyncClient) -> None:
    resp = await client.get("/onboard")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "OpsGenie" in resp.text


@pytest.mark.asyncio
async def test_onboard_valid_creates_pending_company(client: AsyncClient, db: AsyncSession) -> None:
    number = _unique_number()
    resp = await client.post(
        "/onboard",
        json={
            "business_name": "Onboard Co",
            "owner_name": "Owner",
            "whatsapp_number": number,
            "email": "owner@onboardco.test",
            "business_type": "FMCG Distributor",
            "preferred_language": "hi",
            "city": "Berhampur",
            "gst_number": "21ABCDE1234F1Z5",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "registered"
    assert data["whatsapp_number"] == number

    company = await db.scalar(select(Company).where(Company.whatsapp_number == number))
    assert company is not None
    assert company.subscription_active is False  # pending until activated
    assert company.email == "owner@onboardco.test"
    assert company.business_type == "FMCG Distributor"
    assert company.preferred_language == "hi"
    assert company.city == "Berhampur"
    assert company.gst_number == "21ABCDE1234F1Z5"


@pytest.mark.asyncio
async def test_onboard_rejects_founder_number(
    client: AsyncClient, db: AsyncSession, monkeypatch
) -> None:
    """A company can't register with the same number FOUNDER_WHATSAPP_NUMBER
    uses to receive every company's stale-data/briefing-failure alerts —
    otherwise that company's chat would silently get every other company's
    internal ops alerts too (the bug this guard prevents).
    """
    founder_number = _unique_number()
    monkeypatch.setattr(get_settings(), "founder_whatsapp_number", founder_number)

    resp = await client.post(
        "/onboard",
        json={
            "business_name": "Collider Co",
            "owner_name": "Owner",
            "whatsapp_number": founder_number,
        },
    )
    assert resp.status_code == 409, resp.text

    company = await db.scalar(select(Company).where(Company.whatsapp_number == founder_number))
    assert company is None


@pytest.mark.asyncio
async def test_onboard_optional_fields_omitted(client: AsyncClient, db: AsyncSession) -> None:
    number = _unique_number()
    resp = await client.post(
        "/onboard",
        json={"business_name": "Minimal Co", "owner_name": "Owner", "whatsapp_number": number},
    )
    assert resp.status_code == 200, resp.text

    company = await db.scalar(select(Company).where(Company.whatsapp_number == number))
    assert company is not None
    assert company.email is None
    assert company.city is None
    assert company.gst_number is None
    assert company.preferred_language == "en"


@pytest.mark.asyncio
async def test_onboard_duplicate_is_friendly(client: AsyncClient) -> None:
    number = _unique_number()
    body = {"business_name": "Dup Co", "owner_name": "Owner", "whatsapp_number": number}
    first = await client.post("/onboard", json=body)
    assert first.json()["status"] == "registered"
    second = await client.post("/onboard", json=body)
    assert second.status_code == 200
    assert second.json()["status"] == "already_registered"


@pytest.mark.asyncio
async def test_onboard_normalizes_messy_number(client: AsyncClient) -> None:
    tail = uuid.uuid4().int % 1_000_000_000  # 9 digits -> valid Indian mobile with 9 prefix
    messy = f"+91 9{tail:09d}"  # spaces get stripped, still valid E.164
    resp = await client.post(
        "/onboard",
        json={"business_name": "Messy Co", "owner_name": "Owner", "whatsapp_number": messy},
    )
    assert resp.status_code == 200
    assert resp.json()["whatsapp_number"] == messy.replace(" ", "")


@pytest.mark.asyncio
async def test_onboard_invalid_number_422(client: AsyncClient) -> None:
    resp = await client.post(
        "/onboard",
        json={"business_name": "Bad Co", "owner_name": "Owner", "whatsapp_number": "abc"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_onboard_number_without_country_code_rejected(client: AsyncClient) -> None:
    # The footgun: a bare local number (no country code) must be rejected, not
    # silently stored as a wrong E.164 that no inbound would ever match.
    resp = await client.post(
        "/onboard",
        json={"business_name": "No CC Co", "owner_name": "Owner", "whatsapp_number": "9876543210"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_onboard_disabled_returns_503(client: AsyncClient) -> None:
    settings = get_settings()
    original = settings.onboarding_enabled
    settings.onboarding_enabled = False
    try:
        resp = await client.post(
            "/onboard",
            json={
                "business_name": "Disabled Co",
                "owner_name": "Owner",
                "whatsapp_number": _unique_number(),
            },
        )
        assert resp.status_code == 503
    finally:
        settings.onboarding_enabled = original


@pytest.mark.asyncio
async def test_activate_turns_on_subscription_and_sends_welcome(
    client: AsyncClient, db: AsyncSession
) -> None:
    number = _unique_number()
    register = await client.post(
        "/onboard",
        json={"business_name": "Activate Co", "owner_name": "Owner", "whatsapp_number": number},
    )
    company_id = register.json()["company_id"]

    resp = await client.post(f"/onboard/{company_id}/activate")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "activated"
    assert data["subscription_active"] is True

    company = await db.scalar(select(Company).where(Company.whatsapp_number == number))
    assert company is not None
    assert company.subscription_active is True


@pytest.mark.asyncio
async def test_activate_idempotent_second_call(client: AsyncClient) -> None:
    number = _unique_number()
    register = await client.post(
        "/onboard",
        json={"business_name": "Idempotent Co", "owner_name": "Owner", "whatsapp_number": number},
    )
    company_id = register.json()["company_id"]

    first = await client.post(f"/onboard/{company_id}/activate")
    assert first.json()["status"] == "activated"

    second = await client.post(f"/onboard/{company_id}/activate")
    assert second.status_code == 200
    assert second.json()["status"] == "already_active"
    assert second.json()["welcome_sent"] is False


@pytest.mark.asyncio
async def test_activate_unknown_company_404(client: AsyncClient) -> None:
    resp = await client.post(f"/onboard/{uuid.uuid4()}/activate")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_activate_when_onboarding_disabled_503(client: AsyncClient) -> None:
    number = _unique_number()
    register = await client.post(
        "/onboard",
        json={"business_name": "Late Disable Co", "owner_name": "Owner", "whatsapp_number": number},
    )
    company_id = register.json()["company_id"]

    settings = get_settings()
    original = settings.onboarding_enabled
    settings.onboarding_enabled = False
    try:
        resp = await client.post(f"/onboard/{company_id}/activate")
        assert resp.status_code == 503
    finally:
        settings.onboarding_enabled = original
