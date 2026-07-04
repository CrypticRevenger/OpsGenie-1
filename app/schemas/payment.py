"""Pydantic schemas for Payment — response models."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.payment import PaymentSource


class PaymentResponse(BaseModel):
    """Full payment representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    invoice_id: uuid.UUID
    amount: Decimal
    payment_date: date
    method: str | None
    source: PaymentSource
    created_at: datetime
