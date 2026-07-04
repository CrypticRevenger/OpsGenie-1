"""Shared exception types for the importer package.

Kept separate from engine.py/payment_row.py so both can raise/catch them
without a circular import between the two.
"""

from __future__ import annotations


class UnsupportedFileError(ValueError):
    """Raised when the file extension isn't a recognised import format."""


class UnrecognisedFormatError(ValueError):
    """Raised when no importer recognises the file's headers, or required columns are missing."""
