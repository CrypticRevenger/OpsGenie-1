"""Pydantic schemas for Dealer — request and response models."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator


class DealerCreate(BaseModel):
    """Payload to add a dealer to a company."""

    name: str
    phone: str | None = None
    address: str | None = None
    gst_number: str | None = None
    payment_terms_days: int | None = None
    credit_limit: Decimal | None = None
    notes: str | None = None

    @field_validator("payment_terms_days")
    @classmethod
    def must_be_positive(cls, v: int | None) -> int | None:
        if v is not None and v <= 0:
            raise ValueError("payment_terms_days must be a positive integer")
        return v

    @field_validator("credit_limit")
    @classmethod
    def must_be_non_negative(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and v < 0:
            raise ValueError("credit_limit must be zero or positive")
        return v


class DealerUpdate(BaseModel):
    """Partial update — only the fields the founder wants to change."""

    name: str | None = None
    phone: str | None = None
    address: str | None = None
    gst_number: str | None = None
    payment_terms_days: int | None = None
    credit_limit: Decimal | None = None
    notes: str | None = None

    @field_validator("payment_terms_days")
    @classmethod
    def must_be_positive(cls, v: int | None) -> int | None:
        if v is not None and v <= 0:
            raise ValueError("payment_terms_days must be a positive integer")
        return v

    @field_validator("credit_limit")
    @classmethod
    def must_be_non_negative(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and v < 0:
            raise ValueError("credit_limit must be zero or positive")
        return v


class DealerResponse(BaseModel):
    """Full dealer representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    phone: str | None
    address: str | None
    gst_number: str | None
    payment_terms_days: int | None
    credit_limit: Decimal | None
    notes: str | None
    created_at: datetime
