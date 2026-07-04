from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    str(settings.database_url),
    echo=settings.debug,
    poolclass=NullPool if settings.is_development else None,
    # Serverless Postgres (Neon free tier) suspends the compute when idle,
    # which silently drops pooled connections. pre_ping checks a connection is
    # still alive before handing it out and transparently reconnects if not,
    # so the first request after a suspension doesn't fail. Harmless on any
    # other host.
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
