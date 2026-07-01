"""Unit tests for the importer normaliser — date and amount parsing.

These tests are pure unit tests (no DB, no server) and run instantly.
They validate every date format variant and amount edge case before
the Tally-specific column mapping is added.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from app.services.importer.normalizer import normalise_header, parse_amount, parse_date
from app.services.importer.result import ImportResult

# ── parse_date ────────────────────────────────────────────────────────────────


class TestParseDate:
    def test_iso_format(self):
        assert parse_date("2026-01-15") == date(2026, 1, 15)

    def test_iso_format_single_digit_month_day(self):
        assert parse_date("2026-1-5") == date(2026, 1, 5)

    def test_tally_default_format(self):
        # DD-MM-YYYY — the default Tally export format
        assert parse_date("15-01-2026") == date(2026, 1, 15)

    def test_tally_format_single_digit(self):
        assert parse_date("5-1-2026") == date(2026, 1, 5)

    def test_vyapar_slash_format(self):
        # DD/MM/YYYY — Vyapar default
        assert parse_date("15/01/2026") == date(2026, 1, 15)

    def test_iso_slash_format(self):
        assert parse_date("2026/01/15") == date(2026, 1, 15)

    def test_whitespace_stripped(self):
        assert parse_date("  2026-01-15  ") == date(2026, 1, 15)

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match="Unrecognised date format"):
            parse_date("Jan 15, 2026")

    def test_invalid_date_raises(self):
        with pytest.raises(ValueError):
            parse_date("32-01-2026")  # day 32 doesn't exist

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            parse_date("")


# ── parse_amount ──────────────────────────────────────────────────────────────


class TestParseAmount:
    def test_plain_integer(self):
        assert parse_amount("50000") == Decimal("50000.00")

    def test_plain_decimal(self):
        assert parse_amount("49350.50") == Decimal("49350.50")

    def test_with_rupee_symbol(self):
        assert parse_amount("₹49,350.00") == Decimal("49350.00")

    def test_with_commas(self):
        assert parse_amount("1,84,000") == Decimal("184000.00")

    def test_with_leading_trailing_spaces(self):
        assert parse_amount("  25000  ") == Decimal("25000.00")

    def test_zero(self):
        assert parse_amount("0") == Decimal("0.00")

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="Empty amount"):
            parse_amount("")

    def test_text_raises(self):
        with pytest.raises(ValueError, match="Cannot parse amount"):
            parse_amount("N/A")

    def test_currency_only_raises(self):
        with pytest.raises(ValueError, match="Empty amount"):
            parse_amount("₹")


# ── normalise_header ──────────────────────────────────────────────────────────


class TestNormaliseHeader:
    def test_lowercase(self):
        assert normalise_header("InvoiceNumber") == "invoicenumber"

    def test_spaces_to_underscores(self):
        assert normalise_header("Invoice Number") == "invoice_number"

    def test_hyphens_to_underscores(self):
        assert normalise_header("Invoice-Number") == "invoice_number"

    def test_multiple_spaces(self):
        assert normalise_header("Due  Date") == "due_date"

    def test_leading_trailing_whitespace(self):
        assert normalise_header("  party name  ") == "party_name"


# ── ImportResult ──────────────────────────────────────────────────────────────


class TestImportResult:
    def test_initial_state(self):
        r = ImportResult(filename="test.csv", source_format="csv")
        assert r.rows_processed == 0
        assert r.rows_succeeded == 0
        assert r.rows_failed == 0
        assert r.errors == []

    def test_add_success(self):
        r = ImportResult(filename="test.csv", source_format="csv")
        r.add_success()
        assert r.rows_processed == 1
        assert r.rows_succeeded == 1
        assert r.rows_failed == 0

    def test_add_failure(self):
        r = ImportResult(filename="test.csv", source_format="csv")
        r.add_failure(row_number=3, reason="Missing due_date", raw_value="")
        assert r.rows_processed == 1
        assert r.rows_succeeded == 0
        assert r.rows_failed == 1
        assert len(r.errors) == 1
        assert r.errors[0].row_number == 3

    def test_success_property_true(self):
        r = ImportResult(filename="f.csv", source_format="csv")
        r.add_success()
        assert r.success is True

    def test_success_property_false(self):
        r = ImportResult(filename="f.csv", source_format="csv")
        r.add_failure(1, "bad row")
        assert r.success is False

    def test_partial_property(self):
        r = ImportResult(filename="f.csv", source_format="csv")
        r.add_success()
        r.add_failure(2, "bad row")
        assert r.partial is True
        assert r.success is False

    def test_error_detail_json(self):
        r = ImportResult(filename="f.csv", source_format="csv")
        r.add_failure(5, "Invalid date", "32-13-2026")
        detail = r.error_detail_json
        assert detail == [{"row": 5, "reason": "Invalid date", "raw_value": "32-13-2026"}]

    def test_error_detail_json_empty_when_no_errors(self):
        r = ImportResult(filename="f.csv", source_format="csv")
        r.add_success()
        assert r.error_detail_json == []
