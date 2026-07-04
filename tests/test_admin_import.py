"""Admin import endpoint integration tests — Phase 3.

Requires postgres running with migrations applied:

    uv run alembic upgrade head
    uv run pytest tests/test_admin_import.py -v
"""

from __future__ import annotations

import uuid

import pytest
from app.models.import_log import ImportLog
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

CANONICAL_CSV = (
    b"invoice_number,direction,party_name,invoice_date,due_date,"
    b"subtotal,gst_amount,total_amount,description\n"
    b"INV-100,receivable,Test Dealer,2026-01-05,2026-02-04,5000.00,0.00,5000.00,goods\n"
)


def _unique_phone() -> str:
    return f"+91{uuid.uuid4().int % 10_000_000_000:010d}"


async def _create_company(client: AsyncClient) -> str:
    resp = await client.post(
        "/admin/companies",
        json={
            "business_name": "Import Endpoint Test Co",
            "owner_name": "Owner",
            "whatsapp_number": _unique_phone(),
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_import_invoices_csv_end_to_end(client: AsyncClient) -> None:
    company_id = await _create_company(client)

    resp = await client.post(
        f"/admin/companies/{company_id}/import",
        params={"direction": "receivable", "file_kind": "invoices"},
        files={"file": ("invoices.csv", CANONICAL_CSV, "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["rows_processed"] == 1
    assert data["rows_succeeded"] == 1
    assert data["rows_skipped"] == 0
    assert data["rows_failed"] == 0
    assert data["errors"] == []


@pytest.mark.asyncio
async def test_import_unknown_company_returns_404(client: AsyncClient) -> None:
    resp = await client.post(
        f"/admin/companies/{uuid.uuid4()}/import",
        params={"direction": "receivable"},
        files={"file": ("invoices.csv", CANONICAL_CSV, "text/csv")},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_import_oversize_file_returns_413(client: AsyncClient) -> None:
    company_id = await _create_company(client)
    # One byte over the 10 MB cap — must be rejected before parsing.
    oversize = b"x" * (10 * 1024 * 1024 + 1)
    resp = await client.post(
        f"/admin/companies/{company_id}/import",
        params={"direction": "receivable", "file_kind": "invoices"},
        files={"file": ("huge.csv", oversize, "text/csv")},
    )
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_import_unrecognised_format_returns_400(client: AsyncClient) -> None:
    company_id = await _create_company(client)
    bad_csv = b"name,age,city\nX,1,Y\n"

    resp = await client.post(
        f"/admin/companies/{company_id}/import",
        params={"direction": "receivable"},
        files={"file": ("mystery.csv", bad_csv, "text/csv")},
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"].lower()
    assert "columns" in detail or "recognised" in detail


@pytest.mark.asyncio
async def test_import_unsupported_extension_returns_400(client: AsyncClient) -> None:
    company_id = await _create_company(client)

    resp = await client.post(
        f"/admin/companies/{company_id}/import",
        params={"direction": "receivable"},
        files={"file": ("invoices.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_import_log_written_matches_response(client: AsyncClient, db: AsyncSession) -> None:
    company_id = await _create_company(client)

    resp = await client.post(
        f"/admin/companies/{company_id}/import",
        params={"direction": "receivable", "file_kind": "invoices"},
        files={"file": ("invoices.csv", CANONICAL_CSV, "text/csv")},
    )
    data = resp.json()

    log = await db.scalar(
        select(ImportLog).where(ImportLog.company_id == uuid.UUID(company_id))
    )
    assert log is not None
    assert log.filename == "invoices.csv"
    assert log.rows_processed == data["rows_processed"]
    assert log.rows_succeeded == data["rows_succeeded"] + data["rows_skipped"]
    assert log.rows_failed == data["rows_failed"]
