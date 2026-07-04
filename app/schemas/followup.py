"""Pydantic schemas for the invoice due-date follow-up endpoint."""

from __future__ import annotations

from pydantic import BaseModel

from app.services.followup import FollowUpSendStatus


class FollowUpSendResponse(BaseModel):
    status: FollowUpSendStatus
    invoice_number: str | None = None
