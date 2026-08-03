"""RecommendationEngine — per the technical design.

"Pure Python. No LLM. Reads snapshot. Outputs ranked action list as
structured JSON... Claude receives this list and converts to natural
language. Claude never modifies priority, amounts, or entity names."

Deliberately a pure function of a Snapshot — no DB access here. That keeps
every rule testable against hand-built snapshot fixtures with known expected
outputs (SPEC's own build order calls for exactly that), and guarantees the
narration layer (a later phase) can never influence which actions exist or
in what order — only how they're phrased.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.services.snapshot import Snapshot, is_cash_sufficient

ActionType = Literal[
    "cash_deficit_warning",
    "critical_payment_warning",
    "call_dealer",
    "stale_data_warning",
    "follow_up_reminder",
    "incomplete_party_data",
]

_URGENT_SUPPLIER_PAYMENT_HOURS = 48
_STALE_DATA_THRESHOLD_HOURS = 24
_CALL_DEALER_DAYS_OVERDUE = 15
_FOLLOW_UP_DAYS_OVERDUE_MIN = 5
_FOLLOW_UP_DAYS_OVERDUE_MAX = 15


@dataclass
class ActionItem:
    priority: int
    action_type: ActionType
    entity_name: str
    entity_id: uuid.UUID | None
    amount: Decimal | None
    reason: str
    days_overdue: int | None


def build_recommendations(snapshot: Snapshot) -> list[ActionItem]:
    """TDD rules, in priority order. Each rule appends independently — a
    dealer/supplier can appear in more than one rule's output (e.g. a
    critically overdue dealer shows up once as a call_dealer action; the
    thresholds are disjoint by construction so no dealer fires both the
    call_dealer and follow_up_reminder rules for the same invoice).
    """
    actions: list[ActionItem] = []

    if snapshot.cash_deficit:
        deficit = -snapshot.net_cash_position
        actions.append(
            ActionItem(
                priority=1,
                action_type="cash_deficit_warning",
                entity_name=snapshot.business_name,
                entity_id=snapshot.company_id,
                amount=deficit,
                reason=f"Net cash position is a shortfall of {deficit} over the next 7 days.",
                days_overdue=None,
            )
        )

    for payment in snapshot.expected_payments_7d:
        if payment.urgent and not is_cash_sufficient(snapshot.cash_available_today, payment.amount):
            actions.append(
                ActionItem(
                    priority=1,
                    action_type="critical_payment_warning",
                    entity_name=payment.supplier_name,
                    entity_id=payment.supplier_id,
                    amount=payment.amount,
                    reason=(
                        f"{payment.supplier_name} payment of {payment.amount} due "
                        f"{payment.due_date} — cash on hand may be insufficient."
                    ),
                    days_overdue=None,
                )
            )

    # A dealer with a credit_limit set qualifies once outstanding exceeds it.
    # A dealer with NO credit_limit set has no threshold to compare against —
    # rather than falling silently out of every rule once past 15 days overdue
    # (confirmed against real AP BIOCARE data: neither real dealer had a
    # credit_limit set, and both were 100+ days overdue with zero
    # recommendations before this fallback existed), they still qualify once
    # severely overdue. No amount threshold is invented — days_overdue alone
    # is the trigger in that case.
    call_candidates = [
        dealer
        for dealer in snapshot.overdue_dealers
        if dealer.days_overdue > _CALL_DEALER_DAYS_OVERDUE
        and (dealer.credit_limit is None or dealer.outstanding > dealer.credit_limit)
    ]
    for dealer in sorted(call_candidates, key=lambda d: d.outstanding, reverse=True):
        if dealer.credit_limit is not None:
            reason = (
                f"{dealer.dealer_name} owes {dealer.outstanding}, over their credit "
                f"limit of {dealer.credit_limit}, {dealer.days_overdue} days overdue."
            )
        else:
            reason = (
                f"{dealer.dealer_name} owes {dealer.outstanding}, "
                f"{dealer.days_overdue} days overdue — no credit limit on file."
            )
        actions.append(
            ActionItem(
                priority=2,
                action_type="call_dealer",
                entity_name=dealer.dealer_name,
                entity_id=dealer.dealer_id,
                amount=dealer.outstanding,
                reason=reason,
                days_overdue=dealer.days_overdue,
            )
        )

    if snapshot.data_freshness_hours is None or (
        snapshot.data_freshness_hours > _STALE_DATA_THRESHOLD_HOURS
    ):
        actions.append(
            ActionItem(
                priority=3,
                action_type="stale_data_warning",
                entity_name=snapshot.business_name,
                entity_id=snapshot.company_id,
                amount=None,
                reason=(
                    "No data has ever been imported."
                    if snapshot.data_freshness_hours is None
                    else f"Data is {snapshot.data_freshness_hours:.1f} hours old."
                ),
                days_overdue=None,
            )
        )

    # Same "housekeeping, not urgent-money" tier as stale_data_warning — fires
    # once, covering both counts, when a distributor picked "later" during
    # onboarding's dealer/supplier missing-field backfill (see
    # app/services/onboarding_flow.py) instead of filling them in on the spot.
    if snapshot.dealers_missing_fields_count or snapshot.suppliers_missing_fields_count:
        parts = []
        if snapshot.dealers_missing_fields_count:
            parts.append(f"{snapshot.dealers_missing_fields_count} dealer(s)")
        if snapshot.suppliers_missing_fields_count:
            parts.append(f"{snapshot.suppliers_missing_fields_count} supplier(s)")
        actions.append(
            ActionItem(
                priority=3,
                action_type="incomplete_party_data",
                entity_name=snapshot.business_name,
                entity_id=None,
                amount=None,
                reason=f"{' and '.join(parts)} are missing phone number and/or credit days.",
                days_overdue=None,
            )
        )

    follow_up_candidates = [
        dealer
        for dealer in snapshot.overdue_dealers
        if _FOLLOW_UP_DAYS_OVERDUE_MIN <= dealer.days_overdue <= _FOLLOW_UP_DAYS_OVERDUE_MAX
    ]
    for dealer in sorted(follow_up_candidates, key=lambda d: d.outstanding, reverse=True):
        actions.append(
            ActionItem(
                priority=4,
                action_type="follow_up_reminder",
                entity_name=dealer.dealer_name,
                entity_id=dealer.dealer_id,
                amount=dealer.outstanding,
                reason=(
                    f"{dealer.dealer_name} owes {dealer.outstanding}, "
                    f"{dealer.days_overdue} days overdue — a gentle reminder is due."
                ),
                days_overdue=dealer.days_overdue,
            )
        )

    return actions
