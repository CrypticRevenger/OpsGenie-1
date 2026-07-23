"""reply_has_unverified_money — the last-line-of-defence money-safety gate
for agent replies. No network, no DB: pure regex/set-membership logic.
"""

from __future__ import annotations

from app.services.agent.money_guard import collect_known_amounts, reply_has_unverified_money


def test_bare_four_digit_figure_with_no_marker_is_caught():
    # Regression: the audit's own example — "4500" has no currency marker, no
    # comma grouping, and (before this fix) fewer than the 5 bare digits the
    # regex required, so it passed unverified even though no tool output ever
    # produced 4500.
    tool_outputs = [{"outstanding": "12000.00"}]
    assert reply_has_unverified_money(
        "You have 4500 left with Ram Traders", tool_outputs
    )


def test_known_bare_figure_passes():
    tool_outputs = [{"outstanding": "4500.00"}]
    assert not reply_has_unverified_money(
        "You have 4500 left with Ram Traders", tool_outputs
    )


def test_currency_marked_figure_still_requires_verification():
    tool_outputs = [{"outstanding": "12000.00"}]
    assert reply_has_unverified_money("You have ₹4500 left", tool_outputs)


def test_comma_grouped_known_figure_passes():
    tool_outputs = [{"total": "500000.00"}]
    assert not reply_has_unverified_money("Total outstanding: 5,00,000", tool_outputs)


def test_small_bare_numbers_stay_exempt():
    # 1-2 digit bare numbers (day counts, quantities, list positions) are
    # deliberately not treated as money candidates — flagging them would make
    # routine narration ("3 dealers", "in 15 days") fail the guard constantly.
    tool_outputs = [{"dealer_count": 3}]
    assert not reply_has_unverified_money("You have 3 dealers overdue", tool_outputs)


def test_collect_known_amounts_walks_nested_tool_outputs():
    tool_outputs = [{"dealers": [{"name": "Ram", "outstanding": "4500.00"}]}]
    known = collect_known_amounts(tool_outputs)
    assert any(v == 4500 for v in known)
