from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

logger = get_logger(__name__)


class OpsGenieError(Exception):
    """Base exception for application-level errors."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    error_code: str = "opsgenie_error"

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        self.message = message
        self.details = details or {}
        super().__init__(message)


class NotFoundError(OpsGenieError):
    status_code = status.HTTP_404_NOT_FOUND
    error_code = "not_found"

    def __init__(self, resource: str, identifier: str) -> None:
        super().__init__(
            f"{resource} not found: {identifier}",
            details={"resource": resource, "identifier": identifier},
        )


class ValidationError(OpsGenieError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    error_code = "validation_error"


class DatabaseError(OpsGenieError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    error_code = "database_error"


def _error_payload(exc: OpsGenieError) -> dict:
    payload = {
        "error": exc.error_code,
        "message": exc.message,
    }
    if exc.details:
        payload["details"] = exc.details
    return payload


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(OpsGenieError)
    async def handle_opsgenie_error(_: Request, exc: OpsGenieError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(exc),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "internal_server_error",
                "message": "An unexpected error occurred.",
            },
        )
