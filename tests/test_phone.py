"""Unit tests for phone normalization — E.164 for dealer/supplier entry.

Pure unit tests (no DB, no server).
"""

from __future__ import annotations

import pytest
from app.services.phone import InvalidPhoneNumberError, normalize_party_phone


class TestNormalizePartyPhone:
    def test_bare_indian_mobile_number_normalizes_to_e164(self):
        assert normalize_party_phone("9876543210") == "+919876543210"

    def test_explicit_country_code_respected(self):
        assert normalize_party_phone("+14155552671") == "+14155552671"

    def test_00_prefix_treated_as_international_prefix(self):
        assert normalize_party_phone("0014155552671") == "+14155552671"

    def test_whitespace_and_punctuation_stripped(self):
        assert normalize_party_phone(" 98765 43210 ") == "+919876543210"
        assert normalize_party_phone("(987)-654-3210") == "+919876543210"

    def test_garbage_input_raises(self):
        with pytest.raises(InvalidPhoneNumberError):
            normalize_party_phone("not a phone number")

    def test_too_short_raises(self):
        with pytest.raises(InvalidPhoneNumberError):
            normalize_party_phone("12345")

    def test_empty_string_raises(self):
        with pytest.raises(InvalidPhoneNumberError):
            normalize_party_phone("")

    def test_default_region_override_changes_assumed_country_code(self):
        # Same bare digits, parsed against two different default regions —
        # confirms the override actually changes which country code gets
        # assumed for a number with no explicit "+<code>".
        assert normalize_party_phone("4155552671", default_region="US") == "+14155552671"
        assert normalize_party_phone("4155552671", default_region="IN") == "+914155552671"
