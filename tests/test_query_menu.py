"""Numbered query menu report-builder tests — Phase 8.

Pure function tests, no DB — same fixture style as tests/test_recommendations.py:
hand-built Snapshot/DealerCollection/SupplierPayment/OverdueDealer objects,
no network or database access.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.services.query_menu import (
    MENU_PROMPT,
    UNKNOWN_INPUT_REPLY,
    build_cash_position_report,
    build_collections_report,
    build_dealer_risk_report,
    build_suppliers_report,
    menu_router,
)
from app.services.snapshot import DealerCollection, OverdueDealer, Snapshot, SupplierPayment

TODAY = date(2026, 3, 15)
NOW = datetime(2026, 3, 15, 9, 0, tzinfo=UTC)


def _base_snapshot(**overrides) -> Snapshot:
    defaults = dict(
        company_id=uuid.uuid4(),
        generated_at=NOW,
        cash_available_today=Decimal("184000.00"),
        expected_collections_7d=[],
        expected_collections_7d_total=Decimal("0.00"),
        expected_payments_7d=[],
        expected_payments_7d_total=Decimal("0.00"),
        net_cash_position=Decimal("184000.00"),
        cash_deficit=False,
        overdue_dealers=[],
        data_freshness_hours=1.0,
        data_completeness_score=None,
        confidence_score=100.0,
    )
    defaults.update(overrides)
    return Snapshot(**defaults)


def _collection(**overrides) -> DealerCollection:
    defaults = dict(
        dealer_id=uuid.uuid4(),
        dealer_name="Kumar Agency",
        amount=Decimal("18000.00"),
        due_date=TODAY,
    )
    defaults.update(overrides)
    return DealerCollection(**defaults)


def _payment(**overrides) -> SupplierPayment:
    defaults = dict(
        supplier_id=uuid.uuid4(),
        supplier_name="Amul",
        amount=Decimal("82000.00"),
        due_date=TODAY + timedelta(days=2),
        urgent=True,
    )
    defaults.update(overrides)
    return SupplierPayment(**defaults)


def _dealer(**overrides) -> OverdueDealer:
    defaults = dict(
        dealer_id=uuid.uuid4(),
        dealer_name="XYZ Traders",
        outstanding=Decimal("42000.00"),
        days_overdue=12,
        late_payment_count_6mo=3,
        risk_level="Medium",
        credit_limit=Decimal("10000.00"),
    )
    defaults.update(overrides)
    return OverdueDealer(**defaults)


# ── Reply 1: Cash Position ───────────────────────────────────────────────────


def test_cash_position_report_no_shortage():
    snapshot = _base_snapshot(
        cash_available_today=Decimal("184000.00"),
        expected_collections_7d_total=Decimal("320000.00"),
        expected_payments_7d_total=Decimal("245000.00"),
        net_cash_position=Decimal("259000.00"),
        cash_deficit=False,
    )
    report = build_cash_position_report(snapshot)
    assert "Cash Position" in report
    assert "₹1,84,000" in report
    assert "₹3,20,000" in report
    assert "₹2,45,000" in report
    assert "+₹2,59,000" in report
    assert "No shortage expected this week." in report


def test_cash_position_report_shortage():
    snapshot = _base_snapshot(cash_deficit=True, net_cash_position=Decimal("-65000.00"))
    report = build_cash_position_report(snapshot)
    assert "-₹65,000" in report
    assert "Shortage expected this week." in report
    assert "No shortage" not in report


# ── Reply 2: Collections ─────────────────────────────────────────────────────


def test_collections_report_lists_each_dealer_with_due_phrase():
    snapshot = _base_snapshot(
        generated_at=NOW,
        expected_collections_7d=[
            _collection(dealer_name="Kumar Agency", amount=Decimal("18000.00"), due_date=TODAY),
            _collection(
                dealer_name="Ram Traders",
                amount=Decimal("31000.00"),
                due_date=TODAY + timedelta(days=3),
            ),
        ],
        expected_collections_7d_total=Decimal("49000.00"),
    )
    report = build_collections_report(snapshot)
    assert "Kumar Agency — ₹18,000 — due today" in report
    assert "Ram Traders — ₹31,000 — due" in report
    assert "Total expected this week: ₹49,000" in report


def test_collections_report_empty_list():
    snapshot = _base_snapshot(expected_collections_7d=[])
    report = build_collections_report(snapshot)
    assert "No collections expected in the next 7 days." in report
    assert "Total expected this week: ₹0" in report


def test_collections_report_due_phrase_boundaries():
    # TODAY (2026-03-15) is a Sunday: +1 day -> Monday, +6 days -> Saturday
    # (weekday name), +7 days -> falls on the same weekday as today, so it
    # must fall back to an explicit ISO date instead of a bare "Sunday".
    snapshot = _base_snapshot(
        expected_collections_7d=[
            _collection(dealer_name="Plus One", due_date=TODAY + timedelta(days=1)),
            _collection(dealer_name="Plus Six", due_date=TODAY + timedelta(days=6)),
            _collection(dealer_name="Plus Seven", due_date=TODAY + timedelta(days=7)),
        ]
    )
    report = build_collections_report(snapshot)
    assert "Plus One — ₹18,000 — due Monday" in report
    assert "Plus Six — ₹18,000 — due Saturday" in report
    assert "Plus Seven — ₹18,000 — due 2026-03-22" in report


# ── Reply 3: Suppliers ───────────────────────────────────────────────────────


def test_suppliers_report_urgent_cash_sufficient():
    snapshot = _base_snapshot(
        cash_available_today=Decimal("184000.00"),
        expected_payments_7d=[
            _payment(supplier_name="Amul", amount=Decimal("82000.00"), urgent=True),
        ],
        expected_payments_7d_total=Decimal("82000.00"),
    )
    report = build_suppliers_report(snapshot)
    assert "Amul — ₹82,000" in report
    assert "cash sufficient" in report
    assert "may be insufficient" not in report


def test_suppliers_report_urgent_cash_insufficient():
    snapshot = _base_snapshot(
        cash_available_today=Decimal("10000.00"),
        expected_payments_7d=[
            _payment(supplier_name="Amul", amount=Decimal("82000.00"), urgent=True),
        ],
        expected_payments_7d_total=Decimal("82000.00"),
    )
    report = build_suppliers_report(snapshot)
    assert "cash may be insufficient" in report


def test_suppliers_report_non_urgent_has_no_cash_annotation():
    snapshot = _base_snapshot(
        expected_payments_7d=[
            _payment(
                supplier_name="Sharma Traders",
                amount=Decimal("45000.00"),
                due_date=TODAY + timedelta(days=6),
                urgent=False,
            ),
        ],
        expected_payments_7d_total=Decimal("45000.00"),
    )
    report = build_suppliers_report(snapshot)
    assert "Sharma Traders — ₹45,000 — due" in report
    assert "cash" not in report.split("Supplier Payments Due")[1].split("Total")[0]


# ── Reply 4: Dealer Risk ─────────────────────────────────────────────────────


def test_dealer_risk_report_groups_by_risk_level():
    snapshot = _base_snapshot(
        overdue_dealers=[
            _dealer(dealer_name="XYZ Traders", risk_level="High", late_payment_count_6mo=3),
            _dealer(dealer_name="Kumar Agency", risk_level="Medium", late_payment_count_6mo=1),
            _dealer(dealer_name="Ram Traders", risk_level="Low", late_payment_count_6mo=0),
        ]
    )
    report = build_dealer_risk_report(snapshot)
    assert "High Risk:" in report
    assert "XYZ Traders" in report
    assert "3 late payments in 6 months" in report
    assert "Medium Risk:" in report
    assert "1 late payment in 6 months" in report
    assert "Low Risk:" in report
    assert "pays on time" in report
    # High section must appear before Medium, which must appear before Low.
    assert report.index("High Risk:") < report.index("Medium Risk:") < report.index("Low Risk:")


def test_dealer_risk_report_omits_empty_buckets():
    snapshot = _base_snapshot(
        overdue_dealers=[_dealer(dealer_name="XYZ Traders", risk_level="High")]
    )
    report = build_dealer_risk_report(snapshot)
    assert "High Risk:" in report
    assert "Medium Risk:" not in report
    assert "Low Risk:" not in report


def test_dealer_risk_report_no_overdue_dealers():
    snapshot = _base_snapshot(overdue_dealers=[])
    report = build_dealer_risk_report(snapshot)
    assert "No overdue dealers right now." in report


# ── menu_router wiring ───────────────────────────────────────────────────────


def test_menu_router_matches_all_four_commands():
    for command in ("1", "2", "3", "4"):
        assert menu_router.match(command) == command


def test_menu_router_executes_each_command_against_a_snapshot():
    snapshot = _base_snapshot()
    for command in ("1", "2", "3", "4"):
        result = menu_router.execute(command, snapshot)
        assert result.reply != ""
        assert result.notification_type.startswith("query_menu_")


def test_menu_prompt_and_unknown_reply_reference_all_four_options():
    assert MENU_PROMPT in UNKNOWN_INPUT_REPLY
    for label in ("1 Cash", "2 Collections", "3 Suppliers", "4 Dealer Risk"):
        assert label in MENU_PROMPT
