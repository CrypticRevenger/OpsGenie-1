"""Vyapar importer — handles Vyapar CSV and Excel exports.

Vyapar is a popular accounting app used by Indian distributors as an
alternative to Tally.  It exports invoices with slightly different column
names and uses DD/MM/YYYY dates by default.

Column aliases should be extended as real Vyapar files are encountered.
"""

from __future__ import annotations

from app.services.importer.base import BaseImporter


class VyaparImporter(BaseImporter):
    """Handles Vyapar invoice export files."""

    SOURCE_NAME = "vyapar"

    REQUIRED_CANONICAL_COLUMNS = {
        "invoice_number",
        "party_name",
        "invoice_date",
        "due_date",
        "total_amount",
    }

    COLUMN_ALIASES: dict[str, str] = {
        # ── Invoice number ──────────────────────────────────────────────
        "invoice_number": "invoice_number",
        "invoice_no": "invoice_number",
        "invoice_no.": "invoice_number",
        "voucher_no": "invoice_number",
        # ── Party ───────────────────────────────────────────────────────
        "party_name": "party_name",
        "customer_name": "party_name",
        "buyer_name": "party_name",
        "vendor_name": "party_name",
        # ── Dates ───────────────────────────────────────────────────────
        "invoice_date": "invoice_date",
        "date": "invoice_date",
        "due_date": "due_date",
        "payment_due_date": "due_date",
        # ── Amounts ─────────────────────────────────────────────────────
        "total_amount": "total_amount",
        "grand_total": "total_amount",
        "total": "total_amount",
        "invoice_amount": "total_amount",
        "subtotal": "subtotal",
        "taxable_amount": "subtotal",
        "gst_amount": "gst_amount",
        "tax_amount": "gst_amount",
        # ── Description ─────────────────────────────────────────────────
        "description": "description",
        "item_name": "description",
        "remarks": "description",
        # ── Vyapar-specific signature columns ───────────────────────────
        # Used in detect() to confirm this is a Vyapar file.
        "gstin": "gst_number",
        "state": "state",
        "payment_status": "payment_status",
    }

    _VYAPAR_SIGNATURE = {"payment_status", "gstin", "grand_total", "buyer_name"}

    @classmethod
    def detect(cls, normalised_headers: list[str]) -> bool:
        """Detect Vyapar exports via signature columns or column count."""
        header_set = set(normalised_headers)
        has_signature = bool(header_set & cls._VYAPAR_SIGNATURE)
        matched = sum(1 for h in normalised_headers if h in cls.COLUMN_ALIASES)
        return has_signature or matched >= 4
