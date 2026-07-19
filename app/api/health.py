import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.core.config import get_settings
from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    settings = get_settings()
    checked_at = datetime.now(UTC).isoformat()

    # CORS is otherwise unconfigured for this app (every other route is
    # same-origin or already authenticated) — this one header is scoped to
    # just this endpoint so the static marketing site (a different origin,
    # e.g. the Vercel deployment) can read the real JSON body cross-origin
    # instead of firing a `no-cors` fetch that can't distinguish this
    # response from Render's own opaque cold-start placeholder page (see
    # app/static/js/main.js's pingAwake).
    cors_headers = {"Access-Control-Allow-Origin": "*"}

    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        # Log the real error server-side; never return it to the caller — a
        # driver exception can carry connection-string fragments, and this
        # endpoint is unauthenticated.
        logger.exception("Health check database probe failed")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "app": settings.app_name,
                "version": __version__,
                "environment": settings.app_env,
                "database": "disconnected",
                "checked_at": checked_at,
            },
            headers=cors_headers,
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "healthy",
            "app": settings.app_name,
            "version": __version__,
            "environment": settings.app_env,
            "database": "connected",
            "checked_at": checked_at,
        },
        headers=cors_headers,
    )
