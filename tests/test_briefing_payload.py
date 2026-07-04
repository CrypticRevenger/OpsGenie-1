"""BriefingService pure-function tests — Phase 5B.

No network — assemble_briefing_payload, confidence_indicator, and
find_unverified_amounts are all deterministic. The one test that touches the
real Claude API lives in tests/test_briefing_service.py, gated on
ANTHROPIC_API_KEY being set.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from app.services.briefing import (
    assemble_briefing_payload,
    confidence_indicator,
    find_unverified_amounts,
    stale_data_banner,
)
from app.services.recommendations import ActionItem
from app.services.snapshot import Snapshot


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
