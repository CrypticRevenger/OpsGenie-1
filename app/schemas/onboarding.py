"""Schemas for the public self-serve onboarding endpoint."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class OnboardRequest(BaseModel):
    business_name: str = Field(min_length=1, max_length=200)
    owner_name: str = Field(min_length=1, max_length=200)
    whatsapp_number: str = Field(min_length=1, max_length=32)
    access_code: str = Field(min_length=1, max_length=200)


class OnboardResponse(BaseModel):
    status: str  # "registered" | "already_registered"
    company_id: uuid.UUID
    whatsapp_number: str
    message: str
