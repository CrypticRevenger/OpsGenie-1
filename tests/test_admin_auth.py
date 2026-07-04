"""Admin authentication tests — Phase 6.

The `client` fixture in conftest.py auto-sends a valid X-API-Key, so these
tests build their own clients to exercise the unauthenticated/wrong-key
paths deliberately.

    uv run alembic upgrade head
    uv run pytest tests/test_admin_auth.py -v
"""

from __future__ import annotations

import pytest
from app.core.config import get_settings
from app.main import app
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_admin_route_without_key_returns_401() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as anon_client:
        resp = await anon_client.get("/admin/companies")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Unauthorized"


@pytest.mark.asyncio
async def test_admin_route_with_wrong_key_returns_401() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"X-API-Key": "not-the-real-key"}
    ) as wrong_client:
        resp = await wrong_client.get("/admin/companies")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Unauthorized"


@pytest.mark.asyncio
async def test_admin_route_with_correct_key_succeeds(client: AsyncClient) -> None:
    # `client` already sends the real key configured in settings.
    resp = await client.get("/admin/companies")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_health_reachable_without_any_key() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as anon_client:
        resp = await anon_client.get("/health")
    assert resp.status_code in (200, 503)  # never 401 — health is intentionally unauthenticated


@pytest.mark.asyncio
async def test_admin_route_rejects_when_server_key_unconfigured(monkeypatch) -> None:
    """Fail-closed check: if ADMIN_API_KEY were ever unset, every admin
    request must be rejected rather than silently allowed through.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "admin_api_key", None)
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"X-API-Key": "anything"}
    ) as anon_client:
        resp = await anon_client.get("/admin/companies")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Unauthorized"
