import logging
import sys

from app.core.config import get_settings

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"


def setup_logging() -> None:
    settings = get_settings()
    level = getattr(logging, settings.log_level, logging.INFO)

    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        datefmt=LOG_DATE_FORMAT,
        stream=sys.stdout,
        force=True,
    )

    access_logger = logging.getLogger("uvicorn.access")
    access_logger.setLevel(logging.WARNING if not settings.debug else logging.INFO)

    engine_logger = logging.getLogger("sqlalchemy.engine")
    engine_logger.setLevel(logging.INFO if settings.debug else logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
