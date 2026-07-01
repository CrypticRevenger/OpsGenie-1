"""Admin API integration tests — Phase 2.

Tests the company, dealer, and supplier admin endpoints against a live DB.
Requires postgres to be running with migrations applied:

    uv run alembic upgrade head
    uv run pytest tests/test_admin.py -v
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient

# ── Helpers ──────────────────────────────────────────────────────────────────


def _unique_phone() -> str:
    """Generate a unique E.164 phone number for each test run."""
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


# ── Company endpoints ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_company(client: AsyncClient) -> None:
    payload = {
        "business_name": "Sharma Distributors",
        "owner_name": "Rajesh Sharma",
        "whatsapp_number": _unique_phone(),
        "email": "rajesh@sharma.com",
        "opening_balance": "150000.00",
    }
    resp = await client.post("/admin/companies", json=payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["business_name"] == "Sharma Distributors"
    assert data["owner_name"] == "Rajesh Sharma"
    assert data["subscription_active"] is True
    assert data["preferred_language"] == "en"
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_create_company_duplicate_whatsapp_returns_409(
    client: AsyncClient,
) -> None:
    phone = _unique_phone()
    payload = {
        "business_name": "First Co",
        "owner_name": "Owner One",
        "whatsapp_number": phone,
    }
    r1 = await client.post("/admin/companies", json=payload)
    assert r1.status_code == 201

    # Same number → conflict
    payload["business_name"] = "Second Co"
    r2 = await client.post("/admin/companies", json=payload)
    assert r2.status_code == 409
    assert "already exists" in r2.json()["detail"]


@pytest.mark.asyncio
async def test_create_company_invalid_whatsapp_returns_422(
    client: AsyncClient,
) -> None:
    payload = {
        "business_name": "Bad Phone Co",
        "owner_name": "Owner",
        "whatsapp_number": "9876543210",  # missing leading +
    }
    resp = await client.post("/admin/companies", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_company(client: AsyncClient) -> None:
    phone = _unique_phone()
    create_resp = await client.post(
        "/admin/companies",
        json={
            "business_name": "Patel Traders",
            "owner_name": "Suresh Patel",
            "whatsapp_number": phone,
        },
    )
    assert create_resp.status_code == 201
    company_id = create_resp.json()["id"]

    get_resp = await client.get(f"/admin/companies/{company_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == company_id


@pytest.mark.asyncio
async def test_get_company_not_found(client: AsyncClient) -> None:
    resp = await client.get(f"/admin/companies/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_companies(client: AsyncClient) -> None:
    # Create two companies
    for i in range(2):
        await client.post(
            "/admin/companies",
            json={
                "business_name": f"List Test Co {i}",
                "owner_name": "Owner",
                "whatsapp_number": _unique_phone(),
            },
        )
    resp = await client.get("/admin/companies")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) >= 2


# ── Dealer endpoints ──────────────────────────────────────────────────────────


async def _create_company(client: AsyncClient) -> str:
    """Create a company and return its ID string."""
    resp = await client.post(
        "/admin/companies",
        json={
            "business_name": "Fixture Co",
            "owner_name": "Fixture Owner",
            "whatsapp_number": _unique_phone(),
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_create_dealer(client: AsyncClient) -> None:
    company_id = await _create_company(client)
    payload = {
        "name": "Kapoor Retail",
        "phone": "+919988776655",
        "payment_terms_days": 30,
        "credit_limit": "50000.00",
    }
    resp = await client.post(f"/admin/companies/{company_id}/dealers", json=payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["name"] == "Kapoor Retail"
    assert data["company_id"] == company_id
    assert data["payment_terms_days"] == 30
    assert Decimal(data["credit_limit"]) == Decimal("50000.00")


@pytest.mark.asyncio
async def test_create_dealer_company_not_found(client: AsyncClient) -> None:
    resp = await client.post(
        f"/admin/companies/{uuid.uuid4()}/dealers",
        json={"name": "Ghost Dealer"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_dealers(client: AsyncClient) -> None:
    company_id = await _create_company(client)
    for name in ("Dealer A", "Dealer B"):
        await client.post(f"/admin/companies/{company_id}/dealers", json={"name": name})

    resp = await client.get(f"/admin/companies/{company_id}/dealers")
    assert resp.status_code == 200
    names = [d["name"] for d in resp.json()]
    assert "Dealer A" in names
    assert "Dealer B" in names


@pytest.mark.asyncio
async def test_get_dealer(client: AsyncClient) -> None:
    company_id = await _create_company(client)
    create_resp = await client.post(
        f"/admin/companies/{company_id}/dealers", json={"name": "Single Dealer"}
    )
    dealer_id = create_resp.json()["id"]

    resp = await client.get(f"/admin/companies/{company_id}/dealers/{dealer_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == dealer_id


@pytest.mark.asyncio
async def test_get_dealer_not_found(client: AsyncClient) -> None:
    company_id = await _create_company(client)
    resp = await client.get(f"/admin/companies/{company_id}/dealers/{uuid.uuid4()}")
    assert resp.status_code == 404


# ── Supplier endpoints ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_supplier(client: AsyncClient) -> None:
    company_id = await _create_company(client)
    payload = {
        "name": "Hindustan Unilever",
        "phone": "+911122334455",
        "payment_terms_days": 15,
        "credit_limit": "200000.00",
    }
    resp = await client.post(f"/admin/companies/{company_id}/suppliers", json=payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["name"] == "Hindustan Unilever"
    assert data["company_id"] == company_id
    assert data["payment_terms_days"] == 15


@pytest.mark.asyncio
async def test_create_supplier_company_not_found(client: AsyncClient) -> None:
    resp = await client.post(
        f"/admin/companies/{uuid.uuid4()}/suppliers",
        json={"name": "Ghost Supplier"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_suppliers(client: AsyncClient) -> None:
    company_id = await _create_company(client)
    for name in ("Supplier X", "Supplier Y"):
        await client.post(
            f"/admin/companies/{company_id}/suppliers", json={"name": name}
        )

    resp = await client.get(f"/admin/companies/{company_id}/suppliers")
    assert resp.status_code == 200
    names = [s["name"] for s in resp.json()]
    assert "Supplier X" in names
    assert "Supplier Y" in names


@pytest.mark.asyncio
async def test_get_supplier(client: AsyncClient) -> None:
    company_id = await _create_company(client)
    create_resp = await client.post(
        f"/admin/companies/{company_id}/suppliers", json={"name": "Single Supplier"}
    )
    supplier_id = create_resp.json()["id"]

    resp = await client.get(f"/admin/companies/{company_id}/suppliers/{supplier_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == supplier_id


@pytest.mark.asyncio
async def test_get_supplier_not_found(client: AsyncClient) -> None:
    company_id = await _create_company(client)
    resp = await client.get(f"/admin/companies/{company_id}/suppliers/{uuid.uuid4()}")
    assert resp.status_code == 404


# ── Cross-entity isolation ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dealers_scoped_to_company(client: AsyncClient) -> None:
    """A dealer created in company A must not appear in company B's dealer list."""
    company_a = await _create_company(client)
    company_b = await _create_company(client)

    await client.post(f"/admin/companies/{company_a}/dealers", json={"name": "A's Dealer"})

    resp = await client.get(f"/admin/companies/{company_b}/dealers")
    assert resp.status_code == 200
    names = [d["name"] for d in resp.json()]
    assert "A's Dealer" not in names
