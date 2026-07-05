"""Schemas for the public self-serve onboarding endpoint."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class OnboardRequest(BaseModel):
    business_name: str = Field(min_length=1, max_length=200)
    owner_name: str = Field(min_length=1, max_length=200)
    whatsapp_number: str = Field(min_length=1, max_length=32)
    email: str | None = Field(default=None, max_length=200)
    business_type: str | None = Field(default=None, max_length=100)
    preferred_language: str = Field(default="en", max_length=10)
    city: str | None = Field(default=None, max_length=100)
    gst_number: str | None = Field(default=None, max_length=32)


class OnboardResponse(BaseModel):
    status: str  # "registered" | "already_registered"
    company_id: uuid.UUID
    whatsapp_number: str
    message: str
