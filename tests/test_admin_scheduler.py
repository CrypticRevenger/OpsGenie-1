"""Admin scheduler-tick endpoint tests.

POST /admin/scheduler/tick lets an external cron (see .github/workflows/
keep-alive.yml) force one APScheduler-equivalent dispatch pass regardless of
whether the internal interval job happened to already be running — see
app/api/admin/scheduler.py's module docstring for why that's necessary on a
free-tier host that spins the process down when idle.

    uv run alembic upgrade head
    uv run pytest tests/test_admin_scheduler.py -v
"""

from __future__ import annotations

import app.api.admin.scheduler as scheduler_route
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_trigger_tick_returns_202_and_runs_dispatch(
    client: AsyncClient, monkeypatch
) -> None:
    calls = []
    fake_result = {
        "server_time_utc": "2026-01-01T00:00:00+00:00",
        "lock_acquired": True,
        "companies": [],
    }

    async def _fake_tick(now=None) -> dict:
        calls.append(now)
        return fake_result

    monkeypatch.setattr(scheduler_route, "run_scheduled_tick", _fake_tick)

    resp = await client.post("/admin/scheduler/tick")
    assert resp.status_code == 202
    assert resp.json() == fake_result
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_trigger_tick_requires_api_key() -> None:
    from app.main import app
    from httpx import ASGITransport

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as anon_client:
        resp = await anon_client.post("/admin/scheduler/tick")
    assert resp.status_code == 401
