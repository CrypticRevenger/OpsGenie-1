"""Unit tests for the pluggable importer architecture.

These are pure unit tests — no DB, no server, no file I/O.
They validate:
  - BaseImporter contract (header mapping, validation, row normalisation)
  - TallyImporter detection across known column variants
  - VyaparImporter detection
  - CanonicalImporter detection
  - detect_importer() priority and fallback behaviour
"""

from __future__ import annotations

import pytest
from app.services.importer.base import BaseImporter
from app.services.importer.canonical import CanonicalImporter
from app.services.importer.detector import detect_importer
from app.services.importer.tally import TallyImporter
from app.services.importer.vyapar import VyaparImporter

# ── Helpers ───────────────────────────────────────────────────────────────────


def normalised(headers: list[str]) -> list[str]:
    """Inline normalisation so tests are readable without importing normaliser."""
    import re

    return [re.sub(r"[\s\-]+", "_", h.strip().lower()) for h in headers]


# ── BaseImporter contract ──────────────────────────────────────────────────────


class _ConcreteImporter(BaseImporter):
    """Minimal concrete importer used only in tests."""

    SOURCE_NAME = "test"
    REQUIRED_CANONICAL_COLUMNS = {"invoice_number", "total_amount"}
    COLUMN_ALIASES = {
        "inv_no": "invoice_number",
        "amount": "total_amount",
        "narration": "description",
    }


class TestBaseImporterMapHeaders:
    def test_maps_known_headers(self):
        hmap = _ConcreteImporter.map_headers(["inv_no", "amount"])
        assert hmap == {"inv_no": "invoice_number", "amount": "total_amount"}

    def test_ignores_unknown_headers(self):
        hmap = _ConcreteImporter.map_headers(["inv_no", "amount", "unknown_col"])
        assert "unknown_col" not in hmap

    def test_empty_headers(self):
        assert _ConcreteImporter.map_headers([]) == {}

    def test_all_optional_columns_mapped(self):
        hmap = _ConcreteImporter.map_headers(["inv_no", "amount", "narration"])
        assert hmap["narration"] == "description"


class TestBaseImporterValidateRequired:
    def test_all_required_present(self):
        hmap = {"inv_no": "invoice_number", "amount": "total_amount"}
        missing = _ConcreteImporter.validate_required(hmap)
        assert missing == []

    def test_missing_one_required(self):
        hmap = {"inv_no": "invoice_number"}
        missing = _ConcreteImporter.validate_required(hmap)
        assert "total_amount" in missing

    def test_missing_all_required(self):
        missing = _ConcreteImporter.validate_required({})
        assert sorted(missing) == ["invoice_number", "total_amount"]


class TestBaseImporterNormaliseRow:
    def test_maps_source_to_canonical(self):
        hmap = {"inv_no": "invoice_number", "amount": "total_amount"}
        raw = {"inv_no": "INV-001", "amount": "50000", "extra": "ignored"}
        result = _ConcreteImporter.normalise_row(raw, hmap)
        assert result == {"invoice_number": "INV-001", "total_amount": "50000"}

    def test_extra_source_columns_ignored(self):
        hmap = {"inv_no": "invoice_number"}
        raw = {"inv_no": "INV-001", "junk": "xyz"}
        result = _ConcreteImporter.normalise_row(raw, hmap)
        assert "junk" not in result

    def test_missing_source_column_skipped(self):
        # header_map says 'amount' maps to 'total_amount', but row has no 'amount'
        hmap = {"inv_no": "invoice_number", "amount": "total_amount"}
        raw = {"inv_no": "INV-001"}
        result = _ConcreteImporter.normalise_row(raw, hmap)
        assert "total_amount" not in result


# ── TallyImporter detection ───────────────────────────────────────────────────


class TestTallyImporterDetect:
    def test_detects_voucher_no_signature(self):
        headers = normalised(["Voucher No", "Date", "Party Name", "Amount"])
        assert TallyImporter.detect(headers) is True

    def test_detects_vch_no_abbreviation(self):
        headers = normalised(["Vch No.", "Voucher Date", "Particulars", "Net Amount"])
        assert TallyImporter.detect(headers) is True

    def test_detects_narration_signature(self):
        headers = normalised(["Date", "Narration", "Amount", "Particulars"])
        assert TallyImporter.detect(headers) is True

    def test_detects_party_ledger_name(self):
        headers = normalised(["Voucher No", "Party Ledger Name", "Amount", "Date"])
        assert TallyImporter.detect(headers) is True

    def test_detects_when_3_aliases_match_without_signature(self):
        # No Tally signature column, but 3 aliases match
        headers = normalised(["Invoice No", "Bill Date", "Due Date", "Net Amount"])
        assert TallyImporter.detect(headers) is True

    def test_does_not_detect_unrelated_headers(self):
        headers = normalised(["Name", "Email", "Phone", "City"])
        assert TallyImporter.detect(headers) is False


class TestTallyImporterColumnAliases:
    """Verify the alias map handles real-world Tally column name variations."""

    cases = [
        # invoice_number variants
        ("Voucher No", "invoice_number"),
        ("Vch No.", "invoice_number"),
        ("Vch No", "invoice_number"),
        ("Invoice No", "invoice_number"),
        ("Invoice Number", "invoice_number"),
        ("Bill No", "invoice_number"),
        ("Ref No", "invoice_number"),
        # party_name variants
        ("Party Name", "party_name"),
        ("Party", "party_name"),
        ("Party Ledger Name", "party_name"),
        ("Ledger Name", "party_name"),
        ("Particulars", "party_name"),
        ("Customer Name", "party_name"),
        ("Supplier Name", "party_name"),
        # invoice_date variants
        ("Date", "invoice_date"),
        ("Voucher Date", "invoice_date"),
        ("Invoice Date", "invoice_date"),
        ("Bill Date", "invoice_date"),
        # due_date variants
        ("Due Date", "due_date"),
        ("Credit Due Date", "due_date"),
        ("Payment Due Date", "due_date"),
        # total_amount variants
        ("Amount", "total_amount"),
        ("Net Amount", "total_amount"),
        ("Total Amount", "total_amount"),
        ("Gross Amount", "total_amount"),
        ("Invoice Amount", "total_amount"),
        ("Value", "total_amount"),
    ]

    @pytest.mark.parametrize("raw_header,expected_canonical", cases)
    def test_alias(self, raw_header: str, expected_canonical: str):
        norm = normalised([raw_header])
        hmap = TallyImporter.map_headers(norm)
        assert expected_canonical in hmap.values(), (
            f"Header '{raw_header}' (normalised: '{norm[0]}') "
            f"did not map to '{expected_canonical}'. "
            f"Got: {hmap}"
        )


class TestTallyImporterValidation:
    def test_valid_headers_pass(self):
        headers = normalised(
            ["Voucher No", "Party Name", "Date", "Due Date", "Net Amount"]
        )
        hmap = TallyImporter.map_headers(headers)
        missing = TallyImporter.validate_required(hmap)
        assert missing == []

    def test_missing_due_date_flagged(self):
        headers = normalised(["Voucher No", "Party Name", "Date", "Amount"])
        hmap = TallyImporter.map_headers(headers)
        missing = TallyImporter.validate_required(hmap)
        assert "due_date" in missing

    def test_missing_party_flagged(self):
        headers = normalised(["Voucher No", "Date", "Due Date", "Amount"])
        hmap = TallyImporter.map_headers(headers)
        missing = TallyImporter.validate_required(hmap)
        assert "party_name" in missing


# ── VyaparImporter detection ──────────────────────────────────────────────────


class TestVyaparImporterDetect:
    def test_detects_payment_status_signature(self):
        headers = normalised(["Invoice No", "Date", "Party Name", "Payment Status"])
        assert VyaparImporter.detect(headers) is True

    def test_detects_gstin_signature(self):
        headers = normalised(["Invoice No", "Party Name", "Amount", "GSTIN"])
        assert VyaparImporter.detect(headers) is True

    def test_detects_grand_total_signature(self):
        headers = normalised(["Invoice No", "Date", "Due Date", "Grand Total"])
        assert VyaparImporter.detect(headers) is True

    def test_does_not_detect_unrelated(self):
        headers = normalised(["Name", "Age", "Location"])
        assert VyaparImporter.detect(headers) is False


# ── CanonicalImporter detection ───────────────────────────────────────────────


class TestCanonicalImporterDetect:
    def test_detects_direction_column(self):
        headers = normalised(
            ["invoice_number", "direction", "party_name", "invoice_date",
             "due_date", "total_amount"]
        )
        assert CanonicalImporter.detect(headers) is True

    def test_does_not_detect_without_direction(self):
        headers = normalised(["invoice_number", "party_name", "total_amount"])
        assert CanonicalImporter.detect(headers) is False

    def test_requires_direction_as_canonical_column(self):
        # Canonical requires 'direction' — unlike Tally/Vyapar
        headers = normalised(
            ["invoice_number", "direction", "party_name",
             "invoice_date", "due_date", "total_amount"]
        )
        hmap = CanonicalImporter.map_headers(headers)
        missing = CanonicalImporter.validate_required(hmap)
        assert missing == []


# ── detect_importer() priority ────────────────────────────────────────────────


class TestDetectImporter:
    def test_canonical_wins_over_tally_when_direction_present(self):
        # If direction column is present, it MUST be canonical format
        raw_headers = ["invoice_number", "direction", "party_name",
                       "invoice_date", "due_date", "total_amount"]
        result = detect_importer(raw_headers)
        assert result is CanonicalImporter

    def test_tally_detected_for_voucher_no_headers(self):
        raw_headers = ["Voucher No", "Party Name", "Date", "Due Date", "Net Amount"]
        result = detect_importer(raw_headers)
        assert result is TallyImporter

    def test_vyapar_detected_for_payment_status_headers(self):
        raw_headers = ["Invoice No", "Party Name", "Amount", "Payment Status",
                       "Invoice Date", "Due Date"]
        result = detect_importer(raw_headers)
        assert result is VyaparImporter

    def test_returns_none_for_unrecognised_format(self):
        raw_headers = ["Column A", "Column B", "Column C"]
        result = detect_importer(raw_headers)
        assert result is None

    def test_returns_none_for_empty_headers(self):
        assert detect_importer([]) is None

    def test_case_insensitive_detection(self):
        # Raw headers with mixed case — normaliser should handle it
        raw_headers = ["VOUCHER NO", "PARTY NAME", "DATE", "DUE DATE", "AMOUNT"]
        result = detect_importer(raw_headers)
        assert result is TallyImporter

    def test_headers_with_extra_spaces_detected(self):
        raw_headers = ["  Voucher No  ", "  Party Name  ", "Date", "Due Date", "Amount"]
        result = detect_importer(raw_headers)
        assert result is TallyImporter
