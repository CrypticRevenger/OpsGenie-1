"""Pydantic schemas for the Daily Business Summary endpoints — read-only,
mirrors app/schemas/cashflow.py's shape.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class DailySnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    business_date: date
    sales_amount: Decimal
    sales_margin: Decimal
    items_missing_cost_data: int
    revenue_excluded_no_cost_data: Decimal
    collections_amount: Decimal
    supplier_payments_amount: Decimal
    net_cash_movement: Decimal
    outstanding_receivables: Decimal
    invoices_created: int
    payments_recorded: int
    orders_created: int


class MonthToDateTotals(BaseModel):
    sales_amount: Decimal
    sales_margin: Decimal
    net_cash_movement: Decimal
    invoices_created: int
    payments_recorded: int
    orders_created: int


class MonthSummaryResponse(BaseModel):
    year: int
    month: int
    totals: MonthToDateTotals
    days: list[DailySnapshotResponse] = Field(default_factory=list)


class EveningBriefSendResponse(BaseModel):
    sent: bool
