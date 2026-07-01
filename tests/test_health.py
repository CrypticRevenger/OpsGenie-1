import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_returns_json(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code in {200, 503}
    payload = response.json()
    assert payload["app"] == "OpsGenie"
    assert payload["status"] in {"healthy", "unhealthy"}
    assert payload["database"] in {"connected", "disconnected"}
    assert "checked_at" in payload


@pytest.mark.asyncio
async def test_health_reports_database_state(client: AsyncClient) -> None:
    response = await client.get("/health")
    payload = response.json()

    if payload["database"] == "connected":
        assert response.status_code == 200
        assert payload["status"] == "healthy"
    else:
        assert response.status_code == 503
        assert payload["status"] == "unhealthy"
        assert "error" in payload
