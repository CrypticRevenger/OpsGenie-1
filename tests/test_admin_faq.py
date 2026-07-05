"""Admin FAQ endpoint tests — Phase 2B.

    uv run alembic upgrade head
    uv run pytest tests/test_admin_faq.py -v
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


def _unique_phone() -> str:
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


async def _create_company(client: AsyncClient) -> str:
    resp = await client.post(
        "/admin/companies",
        json={
            "business_name": "FAQ Test Co",
            "owner_name": "Owner",
            "whatsapp_number": _unique_phone(),
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_create_faq(client: AsyncClient) -> None:
    company_id = await _create_company(client)
    payload = {"question": "What are your delivery days?", "answer": "Monday to Saturday"}
    resp = await client.post(f"/admin/companies/{company_id}/faqs", json=payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["question"] == "What are your delivery days?"
    assert data["answer"] == "Monday to Saturday"
    assert data["company_id"] == company_id


@pytest.mark.asyncio
async def test_create_faq_company_not_found(client: AsyncClient) -> None:
    resp = await client.post(
        f"/admin/companies/{uuid.uuid4()}/faqs",
        json={"question": "Q", "answer": "A"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_faqs(client: AsyncClient) -> None:
    company_id = await _create_company(client)
    await client.post(
        f"/admin/companies/{company_id}/faqs", json={"question": "Q1", "answer": "A1"}
    )
    await client.post(
        f"/admin/companies/{company_id}/faqs", json={"question": "Q2", "answer": "A2"}
    )

    resp = await client.get(f"/admin/companies/{company_id}/faqs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    questions = [f["question"] for f in data["items"]]
    assert "Q1" in questions
    assert "Q2" in questions


@pytest.mark.asyncio
async def test_update_faq(client: AsyncClient) -> None:
    company_id = await _create_company(client)
    create_resp = await client.post(
        f"/admin/companies/{company_id}/faqs", json={"question": "Old Q", "answer": "Old A"}
    )
    faq_id = create_resp.json()["id"]

    resp = await client.patch(
        f"/admin/companies/{company_id}/faqs/{faq_id}", json={"answer": "New A"}
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["question"] == "Old Q"
    assert data["answer"] == "New A"


@pytest.mark.asyncio
async def test_delete_faq(client: AsyncClient) -> None:
    company_id = await _create_company(client)
    create_resp = await client.post(
        f"/admin/companies/{company_id}/faqs", json={"question": "Q", "answer": "A"}
    )
    faq_id = create_resp.json()["id"]

    resp = await client.delete(f"/admin/companies/{company_id}/faqs/{faq_id}")
    assert resp.status_code == 204

    get_resp = await client.get(f"/admin/companies/{company_id}/faqs")
    assert get_resp.json()["total"] == 0
