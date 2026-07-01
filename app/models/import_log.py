"""ImportLog ORM model.

Tracks every CSV/Excel file upload attempt, including per-row success/failure
counts.  A single bad row never fails the whole import — partial success is
the expected behaviour and is recorded here.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._mixins import UUIDMixin

if TYPE_CHECKING:
    from app.models.company import Company


class ImportLog(UUIDMixin, Base):
    """A record of a single CSV or Excel import attempt."""

    __tablename__ = "import_logs"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(String, nullable=False)
    source_format: Mapped[str] = mapped_column(String, nullable=False)
    # imported_at is the canonical timestamp for this table (matches TDD spec).
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    rows_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_succeeded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_detail_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # ── Relationships ────────────────────────────────────────────────────────
    company: Mapped[Company] = relationship("Company", back_populates="import_logs")
