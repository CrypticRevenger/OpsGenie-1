"""Canonical importer — OpsGenie's own documented CSV/Excel format.

This is the fallback importer for files that don't match Tally or Vyapar.
It uses OpsGenie's own column names directly, making it useful for:

1. Manual exports / hand-crafted files from distributors.
2. Files produced by other accounting software not yet supported.
3. Integration testing without a real Tally/Vyapar installation.

The canonical format is defined by the column names in
``app/services/importer/base.py``.
"""

from __future__ import annotations

from app.services.importer.base import BaseImporter


class CanonicalImporter(BaseImporter):
    """Handles OpsGenie's own documented import format.

    In the canonical format, ``direction`` IS a column (receivable | payable).
    This is the only importer where that is true.
    """

    SOURCE_NAME = "canonical"

    REQUIRED_CANONICAL_COLUMNS = {
        "invoice_number",
        "direction",  # required only in canonical format
        "party_name",
        "invoice_date",
        "due_date",
        "total_amount",
    }

    COLUMN_ALIASES: dict[str, str] = {
        "invoice_number": "invoice_number",
        "direction": "direction",  # receivable | payable
        "party_name": "party_name",
        "invoice_date": "invoice_date",
        "due_date": "due_date",
        "subtotal": "subtotal",
        "gst_amount": "gst_amount",
        "total_amount": "total_amount",
        "description": "description",
        # Optional provenance columns — not required, but preserved into
        # BusinessEvent.payload by ImportEngine when present (traceability
        # back to the original source document/row).
        "voucher_reference": "voucher_reference",
        "source_file": "source_file",
    }

    @classmethod
    def detect(cls, normalised_headers: list[str]) -> bool:
        """Canonical format is detected by the presence of a 'direction' column.

        That column doesn't exist in Tally or Vyapar exports, so it uniquely
        identifies an OpsGenie canonical file.
        """
        return "direction" in normalised_headers
