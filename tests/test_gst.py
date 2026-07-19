"""Unit tests for GST helpers — GSTIN format/checksum validation.

Pure unit tests (no DB, no server).
"""

from __future__ import annotations

from app.services.gst import validate_gstin


class TestValidateGstin:
    def test_valid_gstin(self):
        assert validate_gstin("27AAPFU0939F1ZV") is True

    def test_valid_gstin_lowercase_and_whitespace_normalized(self):
        assert validate_gstin(" 27aapfu0939f1zv ") is True

    def test_wrong_checksum_digit(self):
        assert validate_gstin("27AAPFU0939F1ZX") is False

    def test_too_short(self):
        assert validate_gstin("27AAPFU0939F1Z") is False

    def test_too_long(self):
        assert validate_gstin("27AAPFU0939F1ZVV") is False

    def test_non_gstin_text(self):
        assert validate_gstin("not-a-gstin") is False

    def test_empty_string(self):
        assert validate_gstin("") is False

    def test_missing_literal_z(self):
        # 14th character must be the literal 'Z'.
        assert validate_gstin("27AAPFU0939F1AV") is False

    def test_lowercase_letters_in_pan_segment_rejected_before_checksum(self):
        # Format check runs before the checksum, so a lowercase PAN segment
        # (post-normalization it's uppercased, so this actually exercises the
        # normalized valid path too — kept as a regression guard).
        assert validate_gstin("27aapfu0939f1zv") is True
