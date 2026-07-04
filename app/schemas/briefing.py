"""Pydantic schemas for the morning briefing endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class MorningBriefingResponse(BaseModel):
    """Full briefing representation returned by the API.

    unverified_amounts is computed at generation time (find_unverified_amounts)
    and returned so a caller can see if anything in the narration looked
    untraceable to the source data — not stored as a column, since it's
    derived from generated_text + snapshot_json which are already persisted.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    generated_text: str
    confidence_score: Decimal | None
    data_freshness_hours: int | None
    sent_at: datetime | None
    delivery_status: str | None
    created_at: datetime
    unverified_amounts: list[str] = []
