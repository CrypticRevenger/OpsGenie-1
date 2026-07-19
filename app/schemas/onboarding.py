"""Schemas for the public self-serve onboarding endpoint."""

from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.schemas.import_result import ImportResponse


class OnboardRequest(BaseModel):
    business_name: str = Field(min_length=1, max_length=200)
    owner_name: str = Field(min_length=1, max_length=200)
    whatsapp_number: str = Field(min_length=1, max_length=32)
    email: str | None = Field(default=None, max_length=200)
    business_type: str | None = Field(default=None, max_length=100)
    # Locale code; the guided WhatsApp onboarding asks language first and sets
    # the real value, so this is just the initial default. Normalized to a
    # supported code (unknown -> en).
    preferred_language: str = Field(default="en", max_length=32)
    city: str | None = Field(default=None, max_length=100)
    gst_number: str | None = Field(default=None, max_length=32)

    @field_validator("preferred_language")
    @classmethod
    def normalize_locale_code(cls, v: str) -> str:
        from app.i18n import resolve_locale

        return resolve_locale(v).code


class OnboardResponse(BaseModel):
    status: str  # "registered" | "already_registered"
    company_id: uuid.UUID
    whatsapp_number: str
    message: str


class OnboardImportSummary(BaseModel):
    """The self-serve reconciliation screen shown right after a website
    import — counts + outstanding totals as they stand right now, whatever
    combination of files (or none at all) produced them. Not import-specific
    bookkeeping: recomputed fresh from Dealer/Supplier/Invoice/Payment every
    call, so it stays correct however the data got there.
    """

    dealer_count: int
    supplier_count: int
    receivable_invoice_count: int
    receivable_total: Decimal
    payable_invoice_count: int
    payable_total: Decimal


class OnboardImportResponse(BaseModel):
    import_result: ImportResponse
    summary: OnboardImportSummary
