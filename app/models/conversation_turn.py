"""ConversationTurn ORM model — multi-turn memory for the WhatsApp agent.

One row per human-readable dialogue turn (the user's message or the agent's
final reply). Intermediate tool calls are NOT stored — the agent re-derives
those each message against the current DB state, so history gives conversational
continuity ("and Shyam?") without ever replaying stale numbers. Only the last N
turns are loaded as context (see app/services/agent).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._mixins import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.company import Company


class ConversationTurn(UUIDMixin, TimestampMixin, Base):
    """A single user/assistant message in a company's WhatsApp conversation."""

    __tablename__ = "conversation_turns"
    __table_args__ = (Index("ix_conversation_turns_company_created", "company_id", "created_at"),)

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    # "user" (inbound WhatsApp message) or "assistant" (the agent's reply).
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    company: Mapped[Company] = relationship("Company", back_populates="conversation_turns")
