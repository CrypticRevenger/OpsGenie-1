"""PendingOperation ORM model.

Phase 2A — the generic confirm-gate for every guided write workflow (see
app/services/workflows/, app/services/writes/pending_operation.py). One row
represents one validated write awaiting an explicit "YES": payload stores the
RAW user-supplied inputs only (never a pre-computed total), so
execute_pending_operation always re-derives the actual write fresh against
current DB state rather than trusting a possibly-stale preview.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._mixins import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.company import Company


class PendingOperationType(enum.StrEnum):
    """What kind of write this confirmation is for. Room for create_invoice
    (Phase 2B) and others (add_dealer, add_supplier, cancel_invoice) later —
    each new member needs a hand-written ALTER TYPE migration, same
    convention as every other Postgres enum in this codebase.
    """

    record_payment = "record_payment"


class PendingOperation(UUIDMixin, TimestampMixin, Base):
    """One write awaiting the user's explicit confirmation."""

    __tablename__ = "pending_operations"
    __table_args__ = (Index("ix_pending_operations_company_id", "company_id"),)

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    operation_type: Mapped[PendingOperationType] = mapped_column(
        Enum(PendingOperationType, name="pendingoperationtype", create_constraint=True),
        nullable=False,
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # ── Relationships ────────────────────────────────────────────────────────
    # foreign_keys pins this to pending_operations.company_id —
    # companies.active_pending_operation_id is a second FK path between the
    # two tables that isn't this relationship.
    company: Mapped[Company] = relationship(
        "Company", back_populates="pending_operations", foreign_keys=[company_id]
    )
