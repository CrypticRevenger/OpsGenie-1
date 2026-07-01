from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api.admin import router as admin_router
from app.api.health import router as health_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import get_logger, setup_logging
from app.db.session import engine

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logger.info("Starting %s (%s)", settings.app_name, settings.app_env)
    yield
    await engine.dispose()
    logger.info("Database engine disposed")


def create_app() -> FastAPI:
    setup_logging()
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        debug=settings.debug,
        lifespan=lifespan,
    )

    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(admin_router)

    return app


app = create_app()
