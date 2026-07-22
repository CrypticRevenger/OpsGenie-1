"""Pydantic schemas for Supplier — request and response models."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator

from app.services.phone import InvalidPhoneNumberError, normalize_party_phone


def _normalize_phone(v: str | None) -> str | None:
    if v is None or not v.strip():
        return None
    try:
        return normalize_party_phone(v)
    except InvalidPhoneNumberError as exc:
        raise ValueError(str(exc)) from exc


class SupplierCreate(BaseModel):
    """Payload to add a supplier to a company."""

    name: str
    phone: str | None = None
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

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, v: str | None) -> str | None:
        return _normalize_phone(v)


class SupplierUpdate(BaseModel):
    """Partial update — only the fields the founder wants to change."""

    name: str | None = None
    phone: str | None = None
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

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, v: str | None) -> str | None:
        return _normalize_phone(v)


class SupplierResponse(BaseModel):
    """Full supplier representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    phone: str | None
    payment_terms_days: int | None
    credit_limit: Decimal | None
    notes: str | None
    created_at: datetime
