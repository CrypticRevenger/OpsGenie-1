import pytest
from app.db.session import async_session_factory
from app.main import app
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


@pytest.fixture
async def db() -> AsyncSession:
    """Provide an AsyncSession that always rolls back after the test.

    This keeps schema tests isolated — each test starts with a clean slate
    without needing a separate test database or truncation logic.
    """
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.rollback()
