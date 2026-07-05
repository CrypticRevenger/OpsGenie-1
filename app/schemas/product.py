"""Pydantic schemas for Product — request and response models."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator


class ProductCreate(BaseModel):
    """Payload to add a product to a company's catalogue."""

    name: str
    unit: str | None = None
    selling_price: Decimal | None = None
    purchase_price: Decimal | None = None
    stock_quantity: Decimal = Decimal("0")

    @field_validator("selling_price", "purchase_price")
    @classmethod
    def price_must_be_non_negative(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and v < 0:
            raise ValueError("price must be zero or positive")
        return v


class ProductUpdate(BaseModel):
    """Partial update — only the fields the founder wants to change."""

    name: str | None = None
    unit: str | None = None
    selling_price: Decimal | None = None
    purchase_price: Decimal | None = None
    stock_quantity: Decimal | None = None

    @field_validator("selling_price", "purchase_price")
    @classmethod
    def price_must_be_non_negative(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and v < 0:
            raise ValueError("price must be zero or positive")
        return v


class ProductResponse(BaseModel):
    """Full product representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    unit: str | None
    selling_price: Decimal | None
    purchase_price: Decimal | None
    stock_quantity: Decimal
    created_at: datetime
