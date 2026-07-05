"""Pydantic schemas for FAQ — request and response models."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FAQCreate(BaseModel):
    """Payload to add a Q&A pair to a company's FAQ list."""

    question: str
    answer: str


class FAQUpdate(BaseModel):
    """Partial update — only the fields the founder wants to change."""

    question: str | None = None
    answer: str | None = None


class FAQResponse(BaseModel):
    """Full FAQ representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    question: str
    answer: str
    created_at: datetime
