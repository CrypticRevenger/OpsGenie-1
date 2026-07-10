"""Dashboard session-auth tests.

    uv run alembic upgrade head
    uv run pytest tests/test_dashboard_auth.py -v
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.core.config import get_settings
from app.core.dashboard_auth import SESSION_COOKIE_NAME
from app.main import app
from app.models.company import Company
from app.models.product import Product
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


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
