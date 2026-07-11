from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.admin import router as admin_router
from app.api.dashboard import router as dashboard_router
from app.api.export import router as export_router
from app.api.health import router as health_router
from app.api.onboarding import router as onboarding_router
from app.api.site import router as site_router
from app.api.webhooks import router as webhooks_router
from app.core.auth import require_api_key
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import get_logger, setup_logging
from app.core.scheduler import shutdown_scheduler, start_scheduler
from app.db.session import engine

STATIC_DIR = Path(__file__).resolve().parent / "static"

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
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(health_router)
    # Every /admin/* route requires X-API-Key — wired once here rather than
    # per-router, so no individual admin route file needs to know auth exists.
    app.include_router(admin_router, dependencies=[Depends(require_api_key)])
    # Webhooks are called by external services (Meta) that can't send an
    # X-API-Key — deliberately outside the admin_router's auth dependency.
    # Each webhook route has its own verification mechanism instead.
    app.include_router(webhooks_router)
    # Public self-serve onboarding wizard — no X-API-Key (distributors reach
    # it); gated instead by the onboarding_enabled kill-switch.
    app.include_router(onboarding_router)
    # Public marketing site (landing page, privacy/terms/contact).
    app.include_router(site_router)
    # Password-gated server-rendered admin dashboard — its own session auth
    # is internal to its sub-routers (require_dashboard_session), not
    # require_api_key: a browser can't attach a custom header on normal
    # navigation.
    app.include_router(dashboard_router)
    # Public, signed-link company data export — a distributor has no
    # dashboard login, so this is verified by a short-lived HMAC signature
    # baked into the URL itself instead of X-API-Key or a session.
    app.include_router(export_router)

    return app


app = create_app()
