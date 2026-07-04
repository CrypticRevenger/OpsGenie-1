import pytest
from app.core.config import get_settings
from app.db.session import async_session_factory
from app.main import app
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


def has_any_llm_key_configured() -> bool:
    """True if at least one of the 4 LLM provider keys is set in .env — used
    to gate tests that make a real network call to whichever provider the
    fallback chain actually reaches, rather than hardcoding one provider.
    """
    settings = get_settings()
    return any(
        [
            settings.anthropic_api_key,
            settings.gemini_api_key,
            settings.groq_api_key,
            settings.openrouter_api_key,
        ]
    )


@pytest.fixture
async def client() -> AsyncClient:
    """Pre-authenticated client — sends X-API-Key by default so the ~200
    tests written before Phase 6 auth existed don't need to know it exists.
    Tests that specifically exercise auth behavior build their own
    unauthenticated/wrong-key client instead of using this fixture.
    """
    settings = get_settings()
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-API-Key": settings.admin_api_key or ""},
    ) as async_client:
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
