"""Self-serve onboarding import endpoint tests (POST /onboard/{id}/import).

The public counterpart to tests/test_admin_import.py's founder-only route —
same ImportEngine underneath, but scoped to a company still at the pre-
WhatsApp point of the self-serve wizard (onboarding_state == not_started,
not yet subscribed). See app/api/onboarding.py's _get_importable_company.

    uv run alembic upgrade head
    uv run pytest tests/test_onboarding_import.py -v
"""

from __future__ import annotations

import uuid

import pytest
from app.core.config import get_settings
from httpx import AsyncClient

RECEIVABLE_CSV = (
    b"invoice_number,direction,party_name,invoice_date,due_date,"
    b"subtotal,gst_amount,total_amount,description\n"
    b"INV-100,receivable,Ram Traders,2026-01-05,2026-02-04,5000.00,0.00,5000.00,goods\n"
    b"INV-101,receivable,Shree Enterprises,2026-01-06,2026-02-05,3000.00,0.00,3000.00,goods\n"
)

PAYABLE_CSV = (
    b"invoice_number,direction,party_name,invoice_date,due_date,"
    b"subtotal,gst_amount,total_amount,description\n"
    b"BILL-200,payable,Metro Distributors,2026-01-05,2026-02-04,8000.00,0.00,8000.00,stock\n"
)

PRODUCT_CSV = (
    b"Name,Purchase Price,Selling Price,Unit,Stock,GST%\n"
    b"Rice,300,400,kg,100,5\n"
    b"Dal,320,450,kg,50,12\n"
)


def _unique_number() -> str:
    return f"+919{uuid.uuid4().int % 1_000_000_000:09d}"


async def _register_company(client: AsyncClient) -> str:
    resp = await client.post(
        "/onboard",
        json={
            "business_name": "Import Wizard Co",
            "owner_name": "Owner",
            "whatsapp_number": _unique_number(),
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["company_id"]


@pytest.mark.asyncio
async def test_import_receivable_updates_summary(client: AsyncClient) -> None:
    company_id = await _register_company(client)

    resp = await client.post(
        f"/onboard/{company_id}/import",
        params={"direction": "receivable"},
        files={"file": ("sales_register.csv", RECEIVABLE_CSV, "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["import_result"]["rows_succeeded"] == 2
    assert data["import_result"]["rows_failed"] == 0
    summary = data["summary"]
    assert summary["dealer_count"] == 2
    assert summary["supplier_count"] == 0
    assert summary["receivable_invoice_count"] == 2
    assert summary["receivable_total"] == "8000.00"
    assert summary["payable_invoice_count"] == 0
    assert summary["payable_total"] == "0.00"


@pytest.mark.asyncio
async def test_import_both_directions_combines_summary(client: AsyncClient) -> None:
    company_id = await _register_company(client)

    await client.post(
        f"/onboard/{company_id}/import",
        params={"direction": "receivable"},
        files={"file": ("sales_register.csv", RECEIVABLE_CSV, "text/csv")},
    )
    resp = await client.post(
        f"/onboard/{company_id}/import",
        params={"direction": "payable"},
        files={"file": ("purchase_register.csv", PAYABLE_CSV, "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    summary = resp.json()["summary"]
    # Second call's summary reflects everything imported so far, not just
    # this one file — the reconciliation screen only needs the last response.
    assert summary["dealer_count"] == 2
    assert summary["supplier_count"] == 1
    assert summary["receivable_total"] == "8000.00"
    assert summary["payable_total"] == "8000.00"


@pytest.mark.asyncio
async def test_import_row_error_surfaced_without_failing_whole_file(client: AsyncClient) -> None:
    company_id = await _register_company(client)
    csv_with_bad_row = RECEIVABLE_CSV.replace(b"5000.00,0.00,5000.00", b"5000.00,0.00,not-a-number")

    resp = await client.post(
        f"/onboard/{company_id}/import",
        params={"direction": "receivable"},
        files={"file": ("sales_register.csv", csv_with_bad_row, "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    result = resp.json()["import_result"]
    assert result["rows_succeeded"] == 1
    assert result["rows_failed"] == 1
    assert len(result["errors"]) == 1


@pytest.mark.asyncio
async def test_import_unknown_company_404(client: AsyncClient) -> None:
    resp = await client.post(
        f"/onboard/{uuid.uuid4()}/import",
        params={"direction": "receivable"},
        files={"file": ("invoices.csv", RECEIVABLE_CSV, "text/csv")},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_import_already_active_company_returns_404(client: AsyncClient) -> None:
    """A company that already made it through activation (or any company not
    at the fresh not_started/not_subscribed point) can't be imported into —
    closes the leaked/guessed-UUID hole against a real, live distributor.
    """
    company_id = await _register_company(client)
    activate_resp = await client.post(f"/onboard/{company_id}/activate")
    assert activate_resp.status_code == 200

    resp = await client.post(
        f"/onboard/{company_id}/import",
        params={"direction": "receivable"},
        files={"file": ("invoices.csv", RECEIVABLE_CSV, "text/csv")},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_import_oversize_file_returns_413(client: AsyncClient) -> None:
    company_id = await _register_company(client)
    # One byte over the 5 MB public-route cap (stricter than the 10 MB
    # founder admin route — see app/api/onboarding.py's _MAX_UPLOAD_BYTES).
    oversize = b"x" * (5 * 1024 * 1024 + 1)
    resp = await client.post(
        f"/onboard/{company_id}/import",
        params={"direction": "receivable"},
        files={"file": ("huge.csv", oversize, "text/csv")},
    )
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_import_unrecognised_format_returns_400(client: AsyncClient) -> None:
    company_id = await _register_company(client)
    bad_csv = b"name,age,city\nX,1,Y\n"

    resp = await client.post(
        f"/onboard/{company_id}/import",
        params={"direction": "receivable"},
        files={"file": ("bad.csv", bad_csv, "text/csv")},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_import_disabled_returns_503(client: AsyncClient) -> None:
    company_id = await _register_company(client)
    settings = get_settings()
    original = settings.onboarding_enabled
    settings.onboarding_enabled = False
    try:
        resp = await client.post(
            f"/onboard/{company_id}/import",
            params={"direction": "receivable"},
            files={"file": ("invoices.csv", RECEIVABLE_CSV, "text/csv")},
        )
        assert resp.status_code == 503
    finally:
        settings.onboarding_enabled = original


# ── Product & current stock upload ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_import_products_updates_summary(client: AsyncClient) -> None:
    company_id = await _register_company(client)

    resp = await client.post(
        f"/onboard/{company_id}/import",
        params={"file_kind": "products"},
        files={"file": ("stock.csv", PRODUCT_CSV, "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["import_result"]["rows_succeeded"] == 2
    assert data["import_result"]["rows_failed"] == 0
    summary = data["summary"]
    assert summary["product_count"] == 2
    # Products don't touch dealer/supplier/invoice counts.
    assert summary["dealer_count"] == 0
    assert summary["receivable_invoice_count"] == 0


@pytest.mark.asyncio
async def test_import_products_no_direction_required(client: AsyncClient) -> None:
    """Unlike file_kind=invoices, direction is optional (and ignored) for
    file_kind=products — products have no receivable/payable concept."""
    company_id = await _register_company(client)

    resp = await client.post(
        f"/onboard/{company_id}/import",
        params={"file_kind": "products"},
        files={"file": ("stock.csv", PRODUCT_CSV, "text/csv")},
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_import_invoices_without_direction_returns_400(client: AsyncClient) -> None:
    company_id = await _register_company(client)

    resp = await client.post(
        f"/onboard/{company_id}/import",
        # file_kind defaults to "invoices"; direction omitted.
        files={"file": ("invoices.csv", RECEIVABLE_CSV, "text/csv")},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_import_products_alias_headers_and_missing_fields(client: AsyncClient) -> None:
    """Header matching is alias-based and case/whitespace-insensitive; missing
    optional fields (price/unit/stock/GST) default sensibly rather than
    failing the row."""
    company_id = await _register_company(client)
    csv_bytes = b"Product Name,Cost,Rate\nSoap,20,35\n"

    resp = await client.post(
        f"/onboard/{company_id}/import",
        params={"file_kind": "products"},
        files={"file": ("stock.csv", csv_bytes, "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["import_result"]["rows_succeeded"] == 1
    assert data["summary"]["product_count"] == 1


@pytest.mark.asyncio
async def test_import_products_missing_name_column_returns_400(client: AsyncClient) -> None:
    company_id = await _register_company(client)
    csv_bytes = b"Price,Stock\n400,100\n"

    resp = await client.post(
        f"/onboard/{company_id}/import",
        params={"file_kind": "products"},
        files={"file": ("stock.csv", csv_bytes, "text/csv")},
    )
    assert resp.status_code == 400
