from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.core.config import get_settings
from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    settings = get_settings()
    checked_at = datetime.now(UTC).isoformat()

    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "app": settings.app_name,
                "version": __version__,
                "environment": settings.app_env,
                "database": "disconnected",
                "error": str(exc),
                "checked_at": checked_at,
            },
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
    )
