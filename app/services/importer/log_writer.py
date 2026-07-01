"""ImportLog writer — saves the result of any import run to the database."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.import_log import ImportLog
from app.services.importer.result import ImportResult

logger = logging.getLogger(__name__)


async def write_import_log(
    db: AsyncSession,
    company_id,
    result: ImportResult,
) -> ImportLog:
    """Persist an ImportResult as an ImportLog row and return it.

    Called at the end of every import regardless of success or failure.
    The log is written even when rows_succeeded == 0, so the founder can
    see what went wrong.
    """
    log = ImportLog(
        company_id=company_id,
        filename=result.filename,
        source_format=result.source_format,
        imported_at=datetime.now(UTC),
        rows_processed=result.rows_processed,
        rows_succeeded=result.rows_succeeded,
        rows_failed=result.rows_failed,
        error_detail_json=result.error_detail_json if result.errors else None,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    logger.info(
        "ImportLog written: %s — %d/%d rows succeeded",
        result.filename,
        result.rows_succeeded,
        result.rows_processed,
    )
    return log
