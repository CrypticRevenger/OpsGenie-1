"""Public self-serve onboarding tests.

The access code comes from the live .env (ONBOARDING_ACCESS_CODE). If it's
unset the code-dependent tests skip, since onboarding is fail-closed and would
reject everything.

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

CODE = get_settings().onboarding_access_code

requires_code = pytest.mark.skipif(
    not CODE, reason="ONBOARDING_ACCESS_CODE not set — onboarding is disabled"
)


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


@requires_code
@pytest.mark.asyncio
async def test_onboard_valid_creates_pending_company(client: AsyncClient, db: AsyncSession) -> None:
    number = _unique_number()
    resp = await client.post(
        "/onboard",
        json={
            "business_name": "Onboard Co",
            "owner_name": "Owner",
            "whatsapp_number": number,
            "access_code": CODE,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "registered"
    assert data["whatsapp_number"] == number

    company = await db.scalar(select(Company).where(Company.whatsapp_number == number))
    assert company is not None
    assert company.subscription_active is False  # pending until activated


@requires_code
@pytest.mark.asyncio
async def test_onboard_wrong_code_rejected(client: AsyncClient, db: AsyncSession) -> None:
    number = _unique_number()
    resp = await client.post(
        "/onboard",
        json={
            "business_name": "Nope Co",
            "owner_name": "Owner",
            "whatsapp_number": number,
            "access_code": "definitely-wrong",
        },
    )
    assert resp.status_code == 403
    # Nothing was written.
    company = await db.scalar(select(Company).where(Company.whatsapp_number == number))
    assert company is None


@requires_code
@pytest.mark.asyncio
async def test_onboard_duplicate_is_friendly(client: AsyncClient) -> None:
    number = _unique_number()
    body = {
        "business_name": "Dup Co",
        "owner_name": "Owner",
        "whatsapp_number": number,
        "access_code": CODE,
    }
    first = await client.post("/onboard", json=body)
    assert first.json()["status"] == "registered"
    second = await client.post("/onboard", json=body)
    assert second.status_code == 200
    assert second.json()["status"] == "already_registered"


@requires_code
@pytest.mark.asyncio
async def test_onboard_normalizes_messy_number(client: AsyncClient, db: AsyncSession) -> None:
    tail = uuid.uuid4().int % 1_000_000_000  # 9 digits -> valid Indian mobile with 9 prefix
    messy = f"+91 9{tail:09d}"  # spaces get stripped, still valid E.164
    resp = await client.post(
        "/onboard",
        json={
            "business_name": "Messy Co",
            "owner_name": "Owner",
            "whatsapp_number": messy,
            "access_code": CODE,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["whatsapp_number"] == messy.replace(" ", "")


@requires_code
@pytest.mark.asyncio
async def test_onboard_invalid_number_422(client: AsyncClient) -> None:
    resp = await client.post(
        "/onboard",
        json={
            "business_name": "Bad Co",
            "owner_name": "Owner",
            "whatsapp_number": "abc",
            "access_code": CODE,
        },
    )
    assert resp.status_code == 422


@requires_code
@pytest.mark.asyncio
async def test_onboard_number_without_country_code_rejected(client: AsyncClient) -> None:
    # The footgun: a bare local number (no country code) must be rejected, not
    # silently stored as a wrong E.164 that no inbound would ever match.
    resp = await client.post(
        "/onboard",
        json={
            "business_name": "No CC Co",
            "owner_name": "Owner",
            "whatsapp_number": "9876543210",
            "access_code": CODE,
        },
    )
    assert resp.status_code == 422
