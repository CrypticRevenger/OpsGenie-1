"""CashSnapshot ORM model.

Records the distributor's opening balance at a point in time.
BusinessSnapshotService derives the current cash position as:
    opening_balance + Σ payments_received − Σ payments_made
No running balance is stored — it is always recalculated.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._mixins import UUIDMixin
from app.models._types import Money

if TYPE_CHECKING:
    from app.models.company import Company


class CashSnapshot(UUIDMixin, Base):
    """A recorded opening-balance snapshot for a company."""

    __tablename__ = "cash_snapshots"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    opening_balance: Mapped[Decimal] = mapped_column(Money, nullable=False)
    # recorded_at is the canonical timestamp for this table (matches TDD spec).
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    recorded_by: Mapped[str | None] = mapped_column(String, nullable=True)

    # ── Relationships ────────────────────────────────────────────────────────
    company: Mapped[Company] = relationship("Company", back_populates="cash_snapshots")
