"""Pydantic schemas for Invoice — response models."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.invoice import InvoiceDirection, InvoiceSource, InvoiceStatus
from app.schemas.payment import PaymentResponse


class InvoiceResponse(BaseModel):
    """Full invoice representation returned by the API.

    amount_paid / amount_outstanding are computed server-side from Payments —
    not stored columns — so they're always consistent with the ledger.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    invoice_number: str
    direction: InvoiceDirection
    dealer_id: uuid.UUID | None
    supplier_id: uuid.UUID | None
    invoice_date: date
    due_date: date
    subtotal: Decimal
    gst_amount: Decimal
    total_amount: Decimal
    status: InvoiceStatus
    source: InvoiceSource
    amount_paid: Decimal
    amount_outstanding: Decimal
    created_at: datetime
    updated_at: datetime


class InvoiceDetailResponse(InvoiceResponse):
    """Single-invoice view — adds the full list of payments recorded against it."""

    payments: list[PaymentResponse]
