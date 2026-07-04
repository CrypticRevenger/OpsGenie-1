from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from app import __version__
from app.api.admin import router as admin_router
from app.api.health import router as health_router
from app.api.webhooks import router as webhooks_router
from app.core.auth import require_api_key
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import get_logger, setup_logging
from app.core.scheduler import shutdown_scheduler, start_scheduler
from app.db.session import engine

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logger.info("Starting %s (%s)", settings.app_name, settings.app_env)
    # Phase 11 — the scheduled-dispatch poll job runs inside this process's
    # event loop (no-op when SCHEDULER_ENABLED=false).
    start_scheduler()
    yield
    shutdown_scheduler()
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
    # Every /admin/* route requires X-API-Key — wired once here rather than
    # per-router, so no individual admin route file needs to know auth exists.
    app.include_router(admin_router, dependencies=[Depends(require_api_key)])
    # Webhooks are called by external services (Meta) that can't send an
    # X-API-Key — deliberately outside the admin_router's auth dependency.
    # Each webhook route has its own verification mechanism instead.
    app.include_router(webhooks_router)

    return app


app = create_app()
