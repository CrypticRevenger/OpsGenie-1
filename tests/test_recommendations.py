"""RecommendationEngine unit tests — Phase 5A.

Pure function tests, no DB — the whole point of keeping build_recommendations
a pure function of a hand-built Snapshot (see app/services/recommendations.py).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.services.recommendations import build_recommendations
from app.services.snapshot import OverdueDealer, Snapshot, SupplierPayment

TODAY = date(2026, 3, 15)


def _base_snapshot(**overrides) -> Snapshot:
    defaults = dict(
        company_id=uuid.uuid4(),
        generated_at=datetime.now(UTC),
        cash_available_today=Decimal("100000.00"),
        expected_collections_7d=[],
        expected_collections_7d_total=Decimal("0.00"),
        expected_payments_7d=[],
        expected_payments_7d_total=Decimal("0.00"),
        net_cash_position=Decimal("100000.00"),
        cash_deficit=False,
        overdue_dealers=[],
        data_freshness_hours=1.0,
        data_completeness_score=None,
        confidence_score=100.0,
        business_name="Test Company",
    )
    defaults.update(overrides)
    return Snapshot(**defaults)


def _dealer(**overrides) -> OverdueDealer:
    defaults = dict(
        dealer_id=uuid.uuid4(),
        dealer_name="Test Dealer",
        outstanding=Decimal("50000.00"),
        days_overdue=20,
        late_payment_count_6mo=0,
        risk_level="High",
        credit_limit=Decimal("30000.00"),
    )
    defaults.update(overrides)
    return OverdueDealer(**defaults)


def _supplier_payment(**overrides) -> SupplierPayment:
    defaults = dict(
        supplier_id=uuid.uuid4(),
        supplier_name="Test Supplier",
        amount=Decimal("80000.00"),
        due_date=TODAY + timedelta(days=1),
        urgent=True,
    )
    defaults.update(overrides)
    return SupplierPayment(**defaults)


# ── Rule 1: cash deficit ──────────────────────────────────────────────────────


def test_cash_deficit_fires_warning():
    snapshot = _base_snapshot(cash_deficit=True, net_cash_position=Decimal("-65000.00"))
    actions = build_recommendations(snapshot)
    warnings = [a for a in actions if a.action_type == "cash_deficit_warning"]
    assert len(warnings) == 1
    assert warnings[0].priority == 1
    assert warnings[0].amount == Decimal("65000.00")
    # Customer-facing text must never leak the raw company UUID.
    assert warnings[0].entity_name == "Test Company"


def test_no_cash_deficit_no_warning():
    snapshot = _base_snapshot(cash_deficit=False)
    actions = build_recommendations(snapshot)
    assert not [a for a in actions if a.action_type == "cash_deficit_warning"]


# ── Rule 2: critical supplier payment ────────────────────────────────────────


def test_urgent_payment_with_insufficient_cash_fires_critical_warning():
    payment = _supplier_payment(urgent=True, amount=Decimal("90000.00"))
    snapshot = _base_snapshot(
        cash_available_today=Decimal("50000.00"), expected_payments_7d=[payment]
    )
    actions = build_recommendations(snapshot)
    warnings = [a for a in actions if a.action_type == "critical_payment_warning"]
    assert len(warnings) == 1
    assert warnings[0].priority == 1
    assert warnings[0].entity_id == payment.supplier_id


def test_urgent_payment_with_sufficient_cash_no_warning():
    payment = _supplier_payment(urgent=True, amount=Decimal("10000.00"))
    snapshot = _base_snapshot(
        cash_available_today=Decimal("50000.00"), expected_payments_7d=[payment]
    )
    actions = build_recommendations(snapshot)
    assert not [a for a in actions if a.action_type == "critical_payment_warning"]


def test_non_urgent_payment_never_fires_critical_warning_even_if_cash_short():
    payment = _supplier_payment(urgent=False, amount=Decimal("999999.00"))
    snapshot = _base_snapshot(cash_available_today=Decimal("1.00"), expected_payments_7d=[payment])
    actions = build_recommendations(snapshot)
    assert not [a for a in actions if a.action_type == "critical_payment_warning"]


# ── Rule 3: call dealer ───────────────────────────────────────────────────────


def test_dealer_over_credit_limit_and_overdue_15_days_fires_call():
    dealer = _dealer(
        outstanding=Decimal("50000.00"), credit_limit=Decimal("30000.00"), days_overdue=20
    )
    snapshot = _base_snapshot(overdue_dealers=[dealer])
    actions = build_recommendations(snapshot)
    calls = [a for a in actions if a.action_type == "call_dealer"]
    assert len(calls) == 1
    assert calls[0].priority == 2
    assert calls[0].entity_id == dealer.dealer_id
    assert calls[0].days_overdue == 20


def test_dealer_under_credit_limit_no_call_even_if_overdue():
    dealer = _dealer(
        outstanding=Decimal("10000.00"), credit_limit=Decimal("30000.00"), days_overdue=20
    )
    snapshot = _base_snapshot(overdue_dealers=[dealer])
    actions = build_recommendations(snapshot)
    assert not [a for a in actions if a.action_type == "call_dealer"]


def test_dealer_with_no_credit_limit_still_calls_when_severely_overdue():
    """Fallback rule: no credit_limit set means no threshold to compare
    against, but a dealer 100+ days overdue must not fall through every rule
    silently — confirmed against real AP BIOCARE data where this happened.
    """
    dealer = _dealer(outstanding=Decimal("999999.00"), credit_limit=None, days_overdue=100)
    snapshot = _base_snapshot(overdue_dealers=[dealer])
    actions = build_recommendations(snapshot)
    calls = [a for a in actions if a.action_type == "call_dealer"]
    assert len(calls) == 1
    assert calls[0].entity_id == dealer.dealer_id
    assert "no credit limit on file" in calls[0].reason


def test_dealer_with_no_credit_limit_not_yet_overdue_15_days_no_call():
    dealer = _dealer(outstanding=Decimal("999999.00"), credit_limit=None, days_overdue=10)
    snapshot = _base_snapshot(overdue_dealers=[dealer])
    actions = build_recommendations(snapshot)
    assert not [a for a in actions if a.action_type == "call_dealer"]


def test_dealer_overdue_exactly_15_days_not_yet_call_worthy():
    dealer = _dealer(
        outstanding=Decimal("50000.00"), credit_limit=Decimal("1000.00"), days_overdue=15
    )
    snapshot = _base_snapshot(overdue_dealers=[dealer])
    actions = build_recommendations(snapshot)
    assert not [a for a in actions if a.action_type == "call_dealer"]


def test_call_dealer_actions_ordered_by_outstanding_descending():
    small = _dealer(
        outstanding=Decimal("31000.00"), credit_limit=Decimal("1000.00"), days_overdue=20
    )
    large = _dealer(
        outstanding=Decimal("99000.00"), credit_limit=Decimal("1000.00"), days_overdue=25
    )
    snapshot = _base_snapshot(overdue_dealers=[small, large])
    actions = build_recommendations(snapshot)
    calls = [a for a in actions if a.action_type == "call_dealer"]
    assert [c.entity_id for c in calls] == [large.dealer_id, small.dealer_id]


# ── Rule 4: stale data ────────────────────────────────────────────────────────


def test_stale_data_over_24h_fires_warning():
    snapshot = _base_snapshot(data_freshness_hours=48.0)
    actions = build_recommendations(snapshot)
    warnings = [a for a in actions if a.action_type == "stale_data_warning"]
    assert len(warnings) == 1
    # Customer-facing text must never leak the raw company UUID.
    assert warnings[0].entity_name == "Test Company"


def test_no_data_ever_imported_fires_stale_warning():
    snapshot = _base_snapshot(data_freshness_hours=None)
    actions = build_recommendations(snapshot)
    assert len([a for a in actions if a.action_type == "stale_data_warning"]) == 1


def test_fresh_data_no_stale_warning():
    snapshot = _base_snapshot(data_freshness_hours=2.0)
    actions = build_recommendations(snapshot)
    assert not [a for a in actions if a.action_type == "stale_data_warning"]


# ── Rule 5: follow-up reminder ────────────────────────────────────────────────


def test_dealer_overdue_5_to_15_days_fires_follow_up():
    dealer = _dealer(days_overdue=10, credit_limit=None)
    snapshot = _base_snapshot(overdue_dealers=[dealer])
    actions = build_recommendations(snapshot)
    follow_ups = [a for a in actions if a.action_type == "follow_up_reminder"]
    assert len(follow_ups) == 1
    assert follow_ups[0].priority == 4


def test_dealer_overdue_under_5_days_no_follow_up():
    dealer = _dealer(days_overdue=3, credit_limit=None)
    snapshot = _base_snapshot(overdue_dealers=[dealer])
    actions = build_recommendations(snapshot)
    assert not [a for a in actions if a.action_type == "follow_up_reminder"]


def test_dealer_overdue_over_15_days_gets_call_not_follow_up_when_over_limit():
    dealer = _dealer(
        days_overdue=20, outstanding=Decimal("50000.00"), credit_limit=Decimal("1000.00")
    )
    snapshot = _base_snapshot(overdue_dealers=[dealer])
    actions = build_recommendations(snapshot)
    types = {a.action_type for a in actions}
    assert "call_dealer" in types
    assert "follow_up_reminder" not in types


# ── Combined scenario ─────────────────────────────────────────────────────────


def test_priorities_sorted_correctly_across_a_realistic_mixed_snapshot():
    urgent_payment = _supplier_payment(urgent=True, amount=Decimal("90000.00"))
    call_dealer = _dealer(
        outstanding=Decimal("50000.00"), credit_limit=Decimal("1000.00"), days_overdue=20
    )
    follow_up_dealer = _dealer(days_overdue=8, credit_limit=None)

    snapshot = _base_snapshot(
        cash_deficit=True,
        net_cash_position=Decimal("-10000.00"),
        cash_available_today=Decimal("5000.00"),
        expected_payments_7d=[urgent_payment],
        overdue_dealers=[call_dealer, follow_up_dealer],
        data_freshness_hours=48.0,
    )
    actions = build_recommendations(snapshot)
    action_types_in_order = [a.action_type for a in actions]

    # priority-1 items first (cash deficit + critical payment, in that rule order),
    # then call_dealer, then stale_data, then follow_up_reminder
    assert action_types_in_order == [
        "cash_deficit_warning",
        "critical_payment_warning",
        "call_dealer",
        "stale_data_warning",
        "follow_up_reminder",
    ]
    assert [a.priority for a in actions] == [1, 1, 2, 3, 4]
