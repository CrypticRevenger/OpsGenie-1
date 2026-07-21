"""BriefingService pure-function tests — Phase 5B.

No network — assemble_briefing_payload, confidence_indicator, and
find_unverified_amounts are all deterministic. The one test that touches the
real Claude API lives in tests/test_briefing_service.py, gated on
ANTHROPIC_API_KEY being set.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from app.i18n import DEFAULT_LOCALE
from app.services.briefing import (
    assemble_briefing_payload,
    build_watch_this_week,
    confidence_indicator,
    find_unverified_amounts,
    stale_data_banner,
)
from app.services.recommendations import ActionItem
from app.services.snapshot import CashDeficitForecast, DealerCollection, Snapshot, SupplierPayment
from app.services.stock_forecast import StockOutForecast


def _base_snapshot(**overrides) -> Snapshot:
    defaults = dict(
        company_id=uuid.uuid4(),
        generated_at=datetime.now(UTC),
        cash_available_today=Decimal("184000.00"),
        expected_collections_7d=[],
        expected_collections_7d_total=Decimal("320000.00"),
        expected_payments_7d=[],
        expected_payments_7d_total=Decimal("245000.00"),
        net_cash_position=Decimal("75000.00"),
        cash_deficit=False,
        overdue_dealers=[],
        data_freshness_hours=1.0,
        data_completeness_score=None,
        confidence_score=94.0,
    )
    defaults.update(overrides)
    return Snapshot(**defaults)


def _action_item(**overrides) -> ActionItem:
    defaults = dict(
        priority=2,
        action_type="call_dealer",
        entity_name="XYZ Traders",
        entity_id=uuid.uuid4(),
        amount=Decimal("42000.00"),
        reason="XYZ Traders owes 42000.00, 12 days overdue.",
        days_overdue=12,
    )
    defaults.update(overrides)
    return ActionItem(**defaults)


# ── stale_data_banner (Step 16) ───────────────────────────────────────────────


def test_stale_data_banner_none_when_fresh():
    assert stale_data_banner(1.0) is None
    assert stale_data_banner(24.0) is None  # exactly at threshold = still fresh


def test_stale_data_banner_present_when_stale():
    banner = stale_data_banner(30.0)
    assert banner is not None
    assert banner.startswith("⚠")
    assert "1 day" in banner


def test_stale_data_banner_multi_day():
    assert "2 day" in stale_data_banner(50.0)


def test_stale_data_banner_never_imported():
    banner = stale_data_banner(None)
    assert banner is not None
    assert "No data has been received" in banner


# ── assemble_briefing_payload ─────────────────────────────────────────────────


def test_assemble_briefing_payload_traces_every_field_to_the_snapshot():
    snapshot = _base_snapshot()
    action = _action_item()
    payload = assemble_briefing_payload(snapshot, [action])

    assert payload["cash_position"]["available_today"] == "184000.00"
    assert payload["cash_position"]["expected_in_7_days"] == "320000.00"
    assert payload["cash_position"]["expected_out_7_days"] == "245000.00"
    assert payload["cash_position"]["net_position"] == "75000.00"
    assert payload["cash_position"]["shortage_expected"] is False

    assert len(payload["recommendations"]) == 1
    rec = payload["recommendations"][0]
    assert rec["entity_name"] == "XYZ Traders"
    assert rec["amount"] == "42000.00"
    assert rec["days_overdue"] == 12


def test_assemble_briefing_payload_handles_amount_none():
    snapshot = _base_snapshot()
    action = _action_item(action_type="stale_data_warning", amount=None, days_overdue=None)
    payload = assemble_briefing_payload(snapshot, [action])
    assert payload["recommendations"][0]["amount"] is None


# ── confidence_indicator ──────────────────────────────────────────────────────


def test_confidence_indicator_includes_percentage():
    text = confidence_indicator(94.0, 1.0)
    assert "94%" in text


def test_confidence_indicator_handles_no_data_ever_imported():
    text = confidence_indicator(0.0, None)
    assert "no data has ever been imported" in text


def test_confidence_indicator_handles_fresh_data():
    text = confidence_indicator(100.0, 0.5)
    assert "less than an hour ago" in text


# ── find_unverified_amounts ───────────────────────────────────────────────────


def test_find_unverified_amounts_clean_when_all_figures_traceable():
    payload = {"cash_position": {"available_today": "184000.00"}}
    generated_text = "Available: ₹1,84,000 today."
    # Note: Indian digit grouping "1,84,000" strips to "184000" the same as
    # "184,000" would — comma stripping is grouping-agnostic.
    assert find_unverified_amounts(generated_text, payload) == []


def test_find_unverified_amounts_catches_fabricated_figure():
    payload = {"cash_position": {"available_today": "184000.00"}}
    generated_text = "Available: ₹184000.00 today. Also expect ₹999999 tomorrow."
    unverified = find_unverified_amounts(generated_text, payload)
    assert "999999" in unverified


def test_find_unverified_amounts_no_amounts_mentioned():
    payload = {"cash_position": {"available_today": "184000.00"}}
    generated_text = "Everything looks fine, no numbers here."
    assert find_unverified_amounts(generated_text, payload) == []


# ── build_watch_this_week ──────────────────────────────────────────────────


def test_build_watch_this_week_none_when_nothing_to_show():
    snapshot = _base_snapshot()
    assert build_watch_this_week(snapshot, [], DEFAULT_LOCALE) is None


def test_build_watch_this_week_includes_cash_shortage_with_trigger():
    trigger = SupplierPayment(
        supplier_id=uuid.uuid4(),
        supplier_name="Big Supplier",
        amount=Decimal("90000.00"),
        due_date=date(2026, 1, 3),
        urgent=False,
    )
    snapshot = _base_snapshot(
        cash_deficit_forecast=CashDeficitForecast(days_until=3, trigger_payment=trigger)
    )
    section = build_watch_this_week(snapshot, [], DEFAULT_LOCALE)
    assert section is not None
    assert "Watch this week" in section
    assert "Big Supplier" in section


def test_build_watch_this_week_includes_stock_out_below_threshold():
    snapshot = _base_snapshot()
    forecast = StockOutForecast(
        product_id=uuid.uuid4(),
        product_name="Paracetamol",
        stock_quantity=Decimal("20"),
        units_per_day=Decimal("4"),
        days_of_cover=5,
    )
    section = build_watch_this_week(snapshot, [forecast], DEFAULT_LOCALE)
    assert section is not None
    assert "Paracetamol" in section


def test_build_watch_this_week_excludes_stock_out_above_threshold():
    snapshot = _base_snapshot()
    forecast = StockOutForecast(
        product_id=uuid.uuid4(),
        product_name="Overstocked",
        stock_quantity=Decimal("1000"),
        units_per_day=Decimal("4"),
        days_of_cover=250,
    )
    assert build_watch_this_week(snapshot, [forecast], DEFAULT_LOCALE) is None


def test_build_watch_this_week_includes_predue_collection_within_window():
    generated_at = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)
    collection = DealerCollection(
        dealer_id=uuid.uuid4(),
        dealer_name="ABC Medical",
        amount=Decimal("48000.00"),
        due_date=date(2026, 1, 3),  # 2 days out
    )
    snapshot = _base_snapshot(generated_at=generated_at, expected_collections_7d=[collection])
    section = build_watch_this_week(snapshot, [], DEFAULT_LOCALE)
    assert section is not None
    assert "ABC Medical" in section


def test_build_watch_this_week_excludes_predue_beyond_window():
    generated_at = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)
    collection = DealerCollection(
        dealer_id=uuid.uuid4(),
        dealer_name="Far Out Dealer",
        amount=Decimal("1000.00"),
        due_date=date(2026, 1, 6),  # 5 days out — beyond the pre-due window
    )
    snapshot = _base_snapshot(generated_at=generated_at, expected_collections_7d=[collection])
    assert build_watch_this_week(snapshot, [], DEFAULT_LOCALE) is None


def test_build_watch_this_week_orders_cash_before_stock_before_predue():
    generated_at = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)
    trigger = SupplierPayment(
        supplier_id=uuid.uuid4(),
        supplier_name="Supplier",
        amount=Decimal("1000.00"),
        due_date=date(2026, 1, 2),
        urgent=False,
    )
    stock_forecast = StockOutForecast(
        product_id=uuid.uuid4(),
        product_name="ProductX",
        stock_quantity=Decimal("10"),
        units_per_day=Decimal("2"),
        days_of_cover=5,
    )
    collection = DealerCollection(
        dealer_id=uuid.uuid4(),
        dealer_name="DealerY",
        amount=Decimal("500.00"),
        due_date=date(2026, 1, 3),
    )
    snapshot = _base_snapshot(
        generated_at=generated_at,
        cash_deficit_forecast=CashDeficitForecast(days_until=1, trigger_payment=trigger),
        expected_collections_7d=[collection],
    )
    section = build_watch_this_week(snapshot, [stock_forecast], DEFAULT_LOCALE)
    assert section.index("Supplier") < section.index("ProductX") < section.index("DealerY")
