"""Pydantic schemas for the cashflow endpoint — BusinessSnapshotService +
RecommendationEngine output, read-only.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class DealerCollectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dealer_id: uuid.UUID
    dealer_name: str
    amount: Decimal
    due_date: date


class SupplierPaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    supplier_id: uuid.UUID
    supplier_name: str
    amount: Decimal
    due_date: date
    urgent: bool


class OverdueDealerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dealer_id: uuid.UUID
    dealer_name: str
    outstanding: Decimal
    days_overdue: int
    late_payment_count_6mo: int
    risk_level: str
    credit_limit: Decimal | None


class ActionItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    priority: int
    action_type: str
    entity_name: str
    entity_id: uuid.UUID | None
    amount: Decimal | None
    reason: str
    days_overdue: int | None


class CashflowResponse(BaseModel):
    """BusinessSnapshotService's snapshot + RecommendationEngine's ranked
    action list, combined into one read. This payload is exactly what a
    later Claude narration layer (a separate, later phase) would receive —
    every number here is already final; narration only rephrases it.
    """

    company_id: uuid.UUID
    generated_at: datetime
    cash_available_today: Decimal
    expected_collections_7d: list[DealerCollectionResponse]
    expected_collections_7d_total: Decimal
    expected_payments_7d: list[SupplierPaymentResponse]
    expected_payments_7d_total: Decimal
    net_cash_position: Decimal
    cash_deficit: bool
    overdue_dealers: list[OverdueDealerResponse]
    data_freshness_hours: float | None
    data_completeness_score: float | None
    confidence_score: float
    recommendations: list[ActionItemResponse]
