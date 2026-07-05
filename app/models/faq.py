"""FAQ ORM model.

A small per-company Q&A list the founder populates via the admin API
(app/api/admin/faq.py) so the WhatsApp assistant can answer policy-style
questions (delivery days, return policy, etc.) from real, founder-approved
text instead of guessing — see app/services/agent/read_tools.py's get_faqs.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._mixins import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.company import Company


class FAQ(UUIDMixin, TimestampMixin, Base):
    """One question/answer pair for a company."""

    __tablename__ = "faqs"
    __table_args__ = (Index("ix_faqs_company_id", "company_id"),)

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    question: Mapped[str] = mapped_column(String, nullable=False)
    answer: Mapped[str] = mapped_column(String, nullable=False)

    # ── Relationships ────────────────────────────────────────────────────────
    company: Mapped[Company] = relationship("Company", back_populates="faqs")
