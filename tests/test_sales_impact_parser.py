"""Pure unit tests for the "if I sell N of X" text parser — no DB, no async.

    uv run pytest tests/test_sales_impact_parser.py -v
"""

from __future__ import annotations

from app.services.sales_impact_parser import parse_sales_impact_query


def test_no_trigger_phrase_returns_none() -> None:
    assert parse_sales_impact_query("what is my cash position") is None
    assert parse_sales_impact_query("how much rice do I have") is None


def test_single_item_if_i_sell() -> None:
    assert parse_sales_impact_query("if I sell 50 kg of rice") == [
        {"product_name": "rice", "quantity_sold": "50"}
    ]


def test_single_item_if_i_sold_past_tense() -> None:
    assert parse_sales_impact_query("if I sold 20 dal") == [
        {"product_name": "dal", "quantity_sold": "20"}
    ]


def test_what_if_i_sell_variant() -> None:
    assert parse_sales_impact_query("what if I sell 5 chairs") == [
        {"product_name": "chairs", "quantity_sold": "5"}
    ]


def test_multiple_items_joined_by_and() -> None:
    assert parse_sales_impact_query("if I sold 50 rice and 20 dal") == [
        {"product_name": "rice", "quantity_sold": "50"},
        {"product_name": "dal", "quantity_sold": "20"},
    ]


def test_trailing_question_clause_is_ignored_not_treated_as_an_item() -> None:
    result = parse_sales_impact_query("if I sell 50 kg of rice, how much would be left?")
    assert result == [{"product_name": "rice", "quantity_sold": "50"}]


def test_multi_item_with_trailing_question() -> None:
    result = parse_sales_impact_query(
        "what if i sell 10 units of chicken and 5 boxes of eggs, what's my profit?"
    )
    assert result == [
        {"product_name": "chicken", "quantity_sold": "10"},
        {"product_name": "eggs", "quantity_sold": "5"},
    ]


def test_negative_quantity_never_extracted() -> None:
    # No leading digit for the regex to match ("-5" isn't \d+) — no item,
    # so the whole thing returns None rather than a bogus negative sale.
    assert parse_sales_impact_query("if i sell -5 rice") is None


def test_case_insensitive_trigger() -> None:
    assert parse_sales_impact_query("IF I SELL 10 Rice") == [
        {"product_name": "Rice", "quantity_sold": "10"}
    ]


def test_decimal_quantity() -> None:
    assert parse_sales_impact_query("if I sell 2.5 kg of rice") == [
        {"product_name": "rice", "quantity_sold": "2.5"}
    ]
