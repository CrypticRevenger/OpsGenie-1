"""Pydantic schemas for Company — request and response models."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator


class CompanyCreate(BaseModel):
    """Payload to create a new company (distributor) via the admin endpoint."""

    business_name: str
    owner_name: str
    whatsapp_number: str
    email: str | None = None
    business_type: str | None = None
    preferred_language: str = "en"
    opening_balance: Decimal = Decimal("0")

    @field_validator("whatsapp_number")
    @classmethod
    def must_be_e164(cls, v: str) -> str:
        """Enforce E.164 format: +<country_code><number>, digits only after +."""
        v = v.strip()
        if not v.startswith("+") or not v[1:].isdigit() or len(v) < 8:
            raise ValueError(
                "whatsapp_number must be in E.164 format, e.g. +919876543210"
            )
        return v

    @field_validator("opening_balance")
    @classmethod
    def must_be_non_negative(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("opening_balance must be zero or positive")
        return v


class CompanyResponse(BaseModel):
    """Full company representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_name: str
    owner_name: str
    whatsapp_number: str
    email: str | None
    business_type: str | None
    preferred_language: str
    subscription_active: bool
    opening_balance: Decimal
    created_at: datetime
