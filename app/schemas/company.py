"""Pydantic schemas for Company — request and response models."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, field_validator


class CompanyCreate(BaseModel):
    """Payload to create a new company (distributor) via the admin endpoint."""

    business_name: str
    owner_name: str
    whatsapp_number: str
    email: str | None = None
    business_type: str | None = None
    preferred_language: str = "en"
    # IANA timezone that business-day boundaries (overdue, 7-day window) are
    # computed in. Defaults to India since that's the pilot market.
    timezone: str = "Asia/Kolkata"
    opening_balance: Decimal = Decimal("0")

    @field_validator("whatsapp_number")
    @classmethod
    def must_be_e164(cls, v: str) -> str:
        """Enforce E.164 format: +<country_code><number>, digits only after +."""
        v = v.strip()
        if not v.startswith("+") or not v[1:].isdigit() or len(v) < 8:
            raise ValueError("whatsapp_number must be in E.164 format, e.g. +919876543210")
        return v

    @field_validator("timezone")
    @classmethod
    def must_be_valid_timezone(cls, v: str) -> str:
        """Reject an unknown IANA zone at create time rather than letting it
        blow up later inside build_snapshot.
        """
        v = v.strip()
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"'{v}' is not a valid IANA timezone name.") from exc
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
    timezone: str
    subscription_active: bool
    opening_balance: Decimal
    gst_rate: Decimal
    evening_brief_hour: int | None
    created_at: datetime


class CompanyUpdate(BaseModel):
    """Partial-update payload for PATCH /admin/companies/{id}. Only fields the
    founder can adjust after creation — gst_rate (V0.2's WhatsApp-guided
    invoice GST, see app/services/writes/orders.py) and evening_brief_hour
    (see app/services/evening_brief.py).
    """

    gst_rate: Decimal | None = None
    evening_brief_hour: int | None = None

    @field_validator("gst_rate")
    @classmethod
    def must_be_a_valid_percentage(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and not (Decimal("0") <= v <= Decimal("100")):
            raise ValueError("gst_rate must be between 0 and 100")
        return v

    @field_validator("evening_brief_hour")
    @classmethod
    def must_be_a_valid_hour(cls, v: int | None) -> int | None:
        if v is not None and not (0 <= v <= 23):
            raise ValueError("evening_brief_hour must be between 0 and 23")
        return v


class SubscriptionResponse(BaseModel):
    """Result of an activate/deactivate-subscription action."""

    company_id: uuid.UUID
    subscription_active: bool
    status: str  # "activated" | "already_active" | "deactivated" | "already_inactive"
    welcome_sent: bool = False
