"""Dashboard session-auth tests.

    uv run alembic upgrade head
    uv run pytest tests/test_dashboard_auth.py -v
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from app.core.config import get_settings
from app.core.dashboard_auth import SESSION_COOKIE_NAME, reset_login_rate_limit
from app.main import app
from app.models.company import Company
from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceDirection, InvoiceSource, InvoiceStatus
from app.models.product import Product
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture(autouse=True)
def _clear_login_rate_limit():
    # _login_attempts is module-level state (no shared store exists in this
    # app), so failed attempts from one test would otherwise leak into the
    # next — every request in these tests shares the same "unknown" bucket
    # since httpx's ASGITransport doesn't populate a real client host.
    reset_login_rate_limit()
    yield
    reset_login_rate_limit()


@pytest.mark.asyncio
async def test_login_success_sets_session_cookie() -> None:
    settings = get_settings()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as anon_client:
        resp = await anon_client.post(
            "/dashboard/login", data={"password": settings.dashboard_password}
        )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/dashboard"
    assert SESSION_COOKIE_NAME in resp.cookies


@pytest.mark.asyncio
async def test_login_wrong_password_rerenders_form() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as anon_client:
        resp = await anon_client.post("/dashboard/login", data={"password": "definitely-wrong"})
    assert resp.status_code == 401
    assert "Incorrect password" in resp.text
    assert SESSION_COOKIE_NAME not in resp.cookies


@pytest.mark.asyncio
async def test_login_rejects_when_password_unconfigured(monkeypatch) -> None:
    """Fail-closed check: if DASHBOARD_PASSWORD were ever unset, login must
    always reject rather than silently allowing anyone in.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "dashboard_password", None)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as anon_client:
        resp = await anon_client.post("/dashboard/login", data={"password": "anything"})
    assert resp.status_code == 401
    assert SESSION_COOKIE_NAME not in resp.cookies


@pytest.mark.asyncio
async def test_protected_route_redirects_when_unauthenticated() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as anon_client:
        resp = await anon_client.get("/dashboard/companies")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/dashboard/login"


@pytest.mark.asyncio
async def test_protected_route_rejects_wrong_cookie_value() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        cookies={SESSION_COOKIE_NAME: "not-a-real-session-token"},
    ) as wrong_client:
        resp = await wrong_client.get("/dashboard/companies")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/dashboard/login"


@pytest.mark.asyncio
async def test_protected_route_rejects_expired_session_token() -> None:
    # Regression: the old session token was a bare sha256(password) with no
    # embedded expiry at all — a leaked/extracted cookie was valid forever,
    # regardless of the cookie's own (client-controlled) max_age. The real
    # token now embeds and server-verifies an expires_at.
    import time

    from app.core.dashboard_auth import _sign

    settings = get_settings()
    expired_at = int(time.time()) - 60
    expired_token = f"{expired_at}.{_sign(expired_at, settings.dashboard_password)}"

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        cookies={SESSION_COOKIE_NAME: expired_token},
    ) as expired_client:
        resp = await expired_client.get("/dashboard/companies")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/dashboard/login"


@pytest.mark.asyncio
async def test_login_rate_limited_after_repeated_failures() -> None:
    # Regression: login previously had no rate limit anywhere in the app.
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as anon_client:
        for _ in range(5):
            resp = await anon_client.post(
                "/dashboard/login", data={"password": "definitely-wrong"}
            )
            assert resp.status_code == 401
        limited = await anon_client.post(
            "/dashboard/login", data={"password": "definitely-wrong"}
        )
    assert limited.status_code == 429
    assert "Too many attempts" in limited.text


@pytest.mark.asyncio
async def test_login_rate_limit_does_not_block_eventual_correct_password() -> None:
    settings = get_settings()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as anon_client:
        for _ in range(3):
            resp = await anon_client.post(
                "/dashboard/login", data={"password": "definitely-wrong"}
            )
            assert resp.status_code == 401
        success = await anon_client.post(
            "/dashboard/login", data={"password": settings.dashboard_password}
        )
    assert success.status_code == 303


@pytest.mark.asyncio
async def test_company_list_renders_once_authenticated() -> None:
    settings = get_settings()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as auth_client:
        login_resp = await auth_client.post(
            "/dashboard/login", data={"password": settings.dashboard_password}
        )
        assert login_resp.status_code == 303

        resp = await auth_client.get("/dashboard/companies")
    assert resp.status_code == 200
    assert "Companies" in resp.text


@pytest.mark.asyncio
async def test_company_list_shows_product_count(db: AsyncSession) -> None:
    """Regression test: the company list previously had no way to tell a
    company had any products without opening its detail hub.
    """
    company = Company(
        business_name="Dashboard Product Count Co",
        owner_name="Owner",
        whatsapp_number=f"+919{uuid.uuid4().int % 1_000_000_000:09d}",
    )
    db.add(company)
    await db.flush()
    db.add(Product(company_id=company.id, name="Rice", stock_quantity=Decimal("100")))
    db.add(Product(company_id=company.id, name="Dal", stock_quantity=Decimal("50")))
    await db.commit()

    try:
        settings = get_settings()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as auth_client:
            login_resp = await auth_client.post(
                "/dashboard/login", data={"password": settings.dashboard_password}
            )
            assert login_resp.status_code == 303
            resp = await auth_client.get("/dashboard/companies")

        assert resp.status_code == 200
        assert "Dashboard Product Count Co" in resp.text
        row_start = resp.text.index("Dashboard Product Count Co")
        row_end = resp.text.index("</tr>", row_start)
        row_html = resp.text[row_start:row_end]
        assert f'href="/dashboard/companies/{company.id}#products"' in row_html
        assert ">2<" in row_html
    finally:
        # This test commits (the dashboard route reads through a separate
        # connection, so an uncommitted row in `db` wouldn't be visible to
        # it) — clean up explicitly rather than leaving it in the shared
        # local dev database like the webhook-level tests currently do.
        await db.delete(company)
        await db.commit()


@pytest.mark.asyncio
async def test_company_detail_shows_paid_badge_correctly(db: AsyncSession) -> None:
    """Regression test: the Status column used to compare
    inv.status.value == "paid" (lowercase) against InvoiceStatus.Paid's real
    value "Paid" (capital P) — a case mismatch that made every invoice,
    company-wide, always render "Unpaid" regardless of its real status.
    """
    company = Company(
        business_name="Dashboard Paid Badge Co",
        owner_name="Owner",
        whatsapp_number=f"+919{uuid.uuid4().int % 1_000_000_000:09d}",
    )
    db.add(company)
    await db.flush()
    dealer = Dealer(company_id=company.id, name="Ram Traders")
    db.add(dealer)
    await db.flush()
    db.add(
        Invoice(
            company_id=company.id,
            invoice_number="INV-PAID-BADGE",
            direction=InvoiceDirection.receivable,
            dealer_id=dealer.id,
            invoice_date=date(2026, 1, 1),
            due_date=date(2026, 1, 1),
            subtotal=Decimal("30000.00"),
            gst_amount=Decimal("0.00"),
            total_amount=Decimal("30000.00"),
            status=InvoiceStatus.Paid,
            source=InvoiceSource.csv_import,
        )
    )
    db.add(
        Invoice(
            company_id=company.id,
            invoice_number="INV-PENDING-BADGE",
            direction=InvoiceDirection.receivable,
            dealer_id=dealer.id,
            invoice_date=date(2026, 1, 1),
            due_date=date(2026, 1, 1),
            subtotal=Decimal("10000.00"),
            gst_amount=Decimal("0.00"),
            total_amount=Decimal("10000.00"),
            status=InvoiceStatus.Pending,
            source=InvoiceSource.csv_import,
        )
    )
    await db.commit()

    try:
        settings = get_settings()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as auth_client:
            login_resp = await auth_client.post(
                "/dashboard/login", data={"password": settings.dashboard_password}
            )
            assert login_resp.status_code == 303
            resp = await auth_client.get(f"/dashboard/companies/{company.id}")

        assert resp.status_code == 200

        paid_row_start = resp.text.index("INV-PAID-BADGE")
        paid_row_end = resp.text.index("</tr>", paid_row_start)
        assert ">Paid<" in resp.text[paid_row_start:paid_row_end]

        pending_row_start = resp.text.index("INV-PENDING-BADGE")
        pending_row_end = resp.text.index("</tr>", pending_row_start)
        assert ">Unpaid<" in resp.text[pending_row_start:pending_row_end]
    finally:
        await db.delete(company)
        await db.commit()
