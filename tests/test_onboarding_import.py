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
from app.models.company import Company, OnboardingState
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

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


async def _register_company(client: AsyncClient) -> tuple[str, str]:
    """Register and return (company_id, onboarding_token).

    Both public per-company routes require the token — knowing the UUID is
    deliberately not enough (app/services/onboarding_token.py).
    """
    resp = await client.post(
        "/onboard",
        json={
            "business_name": "Import Wizard Co",
            "owner_name": "Owner",
            "whatsapp_number": _unique_number(),
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return body["company_id"], body["onboarding_token"]


@pytest.mark.asyncio
async def test_import_receivable_updates_summary(client: AsyncClient) -> None:
    company_id, token = await _register_company(client)

    resp = await client.post(
        f"/onboard/{company_id}/import",
        params={"token": token, "direction": "receivable"},
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
    company_id, token = await _register_company(client)

    await client.post(
        f"/onboard/{company_id}/import",
        params={"token": token, "direction": "receivable"},
        files={"file": ("sales_register.csv", RECEIVABLE_CSV, "text/csv")},
    )
    resp = await client.post(
        f"/onboard/{company_id}/import",
        params={"token": token, "direction": "payable"},
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
    company_id, token = await _register_company(client)
    csv_with_bad_row = RECEIVABLE_CSV.replace(b"5000.00,0.00,5000.00", b"5000.00,0.00,not-a-number")

    resp = await client.post(
        f"/onboard/{company_id}/import",
        params={"token": token, "direction": "receivable"},
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
    company_id, token = await _register_company(client)
    activate_resp = await client.post(f"/onboard/{company_id}/activate", params={"token": token})
    assert activate_resp.status_code == 200

    resp = await client.post(
        f"/onboard/{company_id}/import",
        params={"token": token, "direction": "receivable"},
        files={"file": ("invoices.csv", RECEIVABLE_CSV, "text/csv")},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_import_oversize_file_returns_413(client: AsyncClient) -> None:
    company_id, token = await _register_company(client)
    # One byte over the 5 MB public-route cap (stricter than the 10 MB
    # founder admin route — see app/api/onboarding.py's _MAX_UPLOAD_BYTES).
    oversize = b"x" * (5 * 1024 * 1024 + 1)
    resp = await client.post(
        f"/onboard/{company_id}/import",
        params={"token": token, "direction": "receivable"},
        files={"file": ("huge.csv", oversize, "text/csv")},
    )
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_import_unrecognised_format_returns_400(client: AsyncClient) -> None:
    company_id, token = await _register_company(client)
    bad_csv = b"name,age,city\nX,1,Y\n"

    resp = await client.post(
        f"/onboard/{company_id}/import",
        params={"token": token, "direction": "receivable"},
        files={"file": ("bad.csv", bad_csv, "text/csv")},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_import_disabled_returns_503(client: AsyncClient) -> None:
    company_id, token = await _register_company(client)
    settings = get_settings()
    original = settings.onboarding_enabled
    settings.onboarding_enabled = False
    try:
        resp = await client.post(
            f"/onboard/{company_id}/import",
            params={"token": token, "direction": "receivable"},
            files={"file": ("invoices.csv", RECEIVABLE_CSV, "text/csv")},
        )
        assert resp.status_code == 503
    finally:
        settings.onboarding_enabled = original


# ── Product & current stock upload ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_import_payments_allocates_against_earlier_invoice(client: AsyncClient) -> None:
    """file_kind=payments wasn't reachable through the onboarding wizard before
    PDF support landed (the endpoint's file_kind Literal only allowed
    invoices/products) — now it is, same as the admin route."""
    company_id, token = await _register_company(client)

    await client.post(
        f"/onboard/{company_id}/import",
        params={"token": token, "direction": "receivable"},
        files={"file": ("sales_register.csv", RECEIVABLE_CSV, "text/csv")},
    )

    payments_csv = b"party_name,payment_date,amount\nRam Traders,2026-01-10,5000.00\n"
    resp = await client.post(
        f"/onboard/{company_id}/import",
        params={"token": token, "file_kind": "payments", "direction": "receivable"},
        files={"file": ("receipts.csv", payments_csv, "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["import_result"]["rows_succeeded"] == 1
    summary = data["summary"]
    # Ram Traders' INV-100 (5000.00) is now fully paid — receivable drops to
    # just Shree Enterprises' outstanding INV-101 (3000.00).
    assert summary["receivable_total"] == "3000.00"


@pytest.mark.asyncio
async def test_import_pdf_invoice_updates_summary(client: AsyncClient) -> None:
    """The wizard's Dealer/Supplier invoices fields now also accept a Tally-
    style PDF (voucher/invoice printouts), not just .csv/.xlsx."""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    for line in [
        "Bill of Supply",
        "ACME AGRI SUPPLIES Invoice No. Dated",
        "1 Market Road, 785 23-Jan-26",
        "Sometown-560001",
        "Buyer (Bill to)",
        "M/s.Test Dealer Co Dispatched through Destination",
        "Cuttack, Odisha",
        "Total (cid:299) 23,992.00",
    ]:
        pdf.cell(0, 6, text=line, new_x="LMARGIN", new_y="NEXT")
    contents = bytes(pdf.output())

    company_id, token = await _register_company(client)
    resp = await client.post(
        f"/onboard/{company_id}/import",
        params={"token": token, "direction": "receivable"},
        files={"file": ("sale_register.pdf", contents, "application/pdf")},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["import_result"]["rows_succeeded"] == 1
    assert data["import_result"]["source_format"] == "pdf"
    summary = data["summary"]
    assert summary["dealer_count"] == 1
    assert summary["receivable_total"] == "23992.00"


@pytest.mark.asyncio
async def test_import_products_updates_summary(client: AsyncClient) -> None:
    company_id, token = await _register_company(client)

    resp = await client.post(
        f"/onboard/{company_id}/import",
        params={"token": token, "file_kind": "products"},
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
    company_id, token = await _register_company(client)

    resp = await client.post(
        f"/onboard/{company_id}/import",
        params={"token": token, "file_kind": "products"},
        files={"file": ("stock.csv", PRODUCT_CSV, "text/csv")},
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_import_invoices_without_direction_returns_400(client: AsyncClient) -> None:
    company_id, token = await _register_company(client)

    resp = await client.post(
        f"/onboard/{company_id}/import",
        # file_kind defaults to "invoices"; direction omitted.
        params={"token": token},
        files={"file": ("invoices.csv", RECEIVABLE_CSV, "text/csv")},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_import_products_alias_headers_and_missing_fields(client: AsyncClient) -> None:
    """Header matching is alias-based and case/whitespace-insensitive; missing
    optional fields (price/unit/stock/GST) default sensibly rather than
    failing the row."""
    company_id, token = await _register_company(client)
    csv_bytes = b"Product Name,Cost,Rate\nSoap,20,35\n"

    resp = await client.post(
        f"/onboard/{company_id}/import",
        params={"token": token, "file_kind": "products"},
        files={"file": ("stock.csv", csv_bytes, "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["import_result"]["rows_succeeded"] == 1
    assert data["summary"]["product_count"] == 1


@pytest.mark.asyncio
async def test_import_products_rejects_zero_price_row_only(
    client: AsyncClient,
) -> None:
    """A bad price fails only that row — the rest of the file still imports
    (per this importer's per-row SAVEPOINT isolation). A negative stock
    figure is real data (e.g. Tally's "(-)" closing quantity — units sold
    with no matching purchase on file), not a bad row: it's imported as-is,
    same as Product.stock_quantity already allows for any other write path."""
    company_id, token = await _register_company(client)
    csv_bytes = (
        b"Name,Purchase Price,Selling Price,Unit,Stock,GST%\n"
        b"Good Product,300,400,kg,100,5\n"
        b"Zero Price,300,0,kg,100,5\n"
        b"Negative Stock,300,400,kg,-10,5\n"
    )

    resp = await client.post(
        f"/onboard/{company_id}/import",
        params={"token": token, "file_kind": "products"},
        files={"file": ("stock.csv", csv_bytes, "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["import_result"]["rows_succeeded"] == 2
    assert data["import_result"]["rows_failed"] == 1
    assert data["summary"]["product_count"] == 2


@pytest.mark.asyncio
async def test_import_products_missing_name_column_returns_400(client: AsyncClient) -> None:
    company_id, token = await _register_company(client)
    csv_bytes = b"Price,Stock\n400,100\n"

    resp = await client.post(
        f"/onboard/{company_id}/import",
        params={"token": token, "file_kind": "products"},
        files={"file": ("stock.csv", csv_bytes, "text/csv")},
    )
    assert resp.status_code == 400


# ── Security: the UUID-oracle chain ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_already_registered_does_not_disclose_company_id_or_token(
    client: AsyncClient,
) -> None:
    """Posting a number that is already registered must reveal nothing.

    Regression: this branch returned the real company_id. A WhatsApp number is
    public (printed on invoices, encoded in the wa.me link), so anyone could
    post a real distributor's number, receive their UUID, and use it against
    /import — writing into their books and reading back their receivable and
    payable totals, entirely unauthenticated.
    """
    number = _unique_number()
    payload = {
        "business_name": "Oracle Co",
        "owner_name": "Owner",
        "whatsapp_number": number,
    }
    first = await client.post("/onboard", json=payload)
    assert first.status_code == 200
    assert first.json()["status"] == "registered"

    # An attacker who merely knows the number posts it again.
    second = await client.post("/onboard", json=payload)
    assert second.status_code == 200
    body = second.json()
    assert body["status"] == "already_registered"
    assert body["company_id"] is None
    assert body["onboarding_token"] is None


@pytest.mark.asyncio
async def test_import_without_a_token_is_rejected(client: AsyncClient) -> None:
    company_id, _token = await _register_company(client)

    resp = await client.post(
        f"/onboard/{company_id}/import",
        params={"direction": "receivable"},
        files={"file": ("sales_register.csv", RECEIVABLE_CSV, "text/csv")},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_import_with_another_companys_token_is_rejected(client: AsyncClient) -> None:
    """A token is bound to the company it was issued for."""
    victim_id, _victim_token = await _register_company(client)
    _attacker_id, attacker_token = await _register_company(client)

    resp = await client.post(
        f"/onboard/{victim_id}/import",
        params={"token": attacker_token, "direction": "receivable"},
        files={"file": ("sales_register.csv", RECEIVABLE_CSV, "text/csv")},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_import_with_a_tampered_token_is_rejected(client: AsyncClient) -> None:
    company_id, token = await _register_company(client)
    expiry, _, signature = token.partition(".")
    # Flip the last signature character to something guaranteed *different* —
    # the previous version decided which digit to flip in based on the LAST
    # character but then replaced the FIRST one, so whenever signature[0]
    # already happened to equal the replacement digit the "tampered" token was
    # silently identical to the real one (~1 run in 16), a pre-existing flake
    # of the exact same class already fixed in test_company_export.py's
    # test_public_export_endpoint_rejects_tampered_signature.
    tampered_signature = signature[:-1] + ("1" if signature[-1] == "0" else "0")
    tampered = f"{expiry}.{tampered_signature}"

    resp = await client.post(
        f"/onboard/{company_id}/import",
        params={"token": tampered, "direction": "receivable"},
        files={"file": ("sales_register.csv", RECEIVABLE_CSV, "text/csv")},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_activate_without_a_token_is_rejected(client: AsyncClient) -> None:
    company_id, _token = await _register_company(client)
    resp = await client.post(f"/onboard/{company_id}/activate")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_deactivated_mid_onboarding_company_cannot_be_reactivated(
    client: AsyncClient, db: AsyncSession
) -> None:
    """The activate gate used to be written inverted.

    It rejected only `completed AND inactive`, so every *other* inactive state
    passed — meaning a company the founder had suspended part-way through
    onboarding could be switched back on through this public route, re-enabling
    its WhatsApp agent and firing a billable Meta welcome template.
    """
    company_id, token = await _register_company(client)
    company = await db.get(Company, uuid.UUID(company_id))
    company.onboarding_state = OnboardingState.product_awaiting_name
    company.subscription_active = False
    await db.commit()

    resp = await client.post(f"/onboard/{company_id}/activate", params={"token": token})
    assert resp.status_code == 404

    await db.refresh(company)
    assert company.subscription_active is False
