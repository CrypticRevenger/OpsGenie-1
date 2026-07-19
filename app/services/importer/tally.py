"""Tally importer — handles Tally ERP 9 / TallyPrime CSV and Excel exports.

Tally users can export several different report types:

1. Sales Register       — receivable invoices (to dealers)
2. Purchase Register    — payable invoices (from suppliers)
3. Sales Ledger         — sometimes combined
4. Day Book             — all vouchers, requires filtering

Column names in Tally exports vary because:
- Different Tally versions use slightly different labels.
- Operators can rename columns in the export settings.
- Some operators abbreviate ("Vch No." instead of "Voucher No.").
- Reports exported via the Tally XML gateway use different headers
  from those exported via the menu.

This importer is resilient to normal variations by maintaining a
comprehensive alias map.  When the real Tally export file is reviewed,
additional aliases can be added to this map without touching any other
code.

Design note
-----------
``direction`` (receivable vs payable) is *not* a Tally column.  Tally
exports the Sales Register and Purchase Register as separate files.
The importer therefore accepts a ``direction`` argument which the
upload endpoint supplies (e.g., ``?direction=receivable``).
"""

from __future__ import annotations

from app.services.importer.base import BaseImporter


class TallyImporter(BaseImporter):
    """Handles Tally ERP 9 and TallyPrime Sales / Purchase register exports.

    Recognises common column name variations seen across Tally versions
    and operator-configured exports.  Additional aliases should be added
    here as new real-world files are encountered — no other file changes.
    """

    SOURCE_NAME = "tally"

    # Canonical columns that must be resolved before any row is processed.
    # `direction` is intentionally absent — it is supplied by the endpoint.
    REQUIRED_CANONICAL_COLUMNS = {
        "invoice_number",
        "party_name",
        "invoice_date",
        "due_date",
        "total_amount",
    }

    # ── Column alias map ───────────────────────────────────────────────────
    # Key:   normalised source header (lower-case, spaces → underscores)
    # Value: canonical column name used by ImportEngine
    #
    # To add support for a new Tally export variant:
    #   1. Open the real file.
    #   2. Add the normalised header → canonical mapping here.
    #   3. Done. No other file changes needed.
    COLUMN_ALIASES: dict[str, str] = {
        # ── Invoice number ──────────────────────────────────────────────
        "voucher_no": "invoice_number",
        "voucher_no.": "invoice_number",
        "vch_no": "invoice_number",
        "vch_no.": "invoice_number",
        "vch._no.": "invoice_number",
        "voucher_number": "invoice_number",
        "invoice_no": "invoice_number",
        "invoice_no.": "invoice_number",
        "invoice_number": "invoice_number",
        "ref_no": "invoice_number",
        "reference_no": "invoice_number",
        "bill_no": "invoice_number",
        "bill_number": "invoice_number",
        # ── Party / counterparty ────────────────────────────────────────
        "party_name": "party_name",
        "party": "party_name",
        "party_ledger_name": "party_name",
        "ledger_name": "party_name",
        "account_name": "party_name",
        "customer_name": "party_name",
        "supplier_name": "party_name",
        "dealer_name": "party_name",
        "particulars": "party_name",
        # ── Invoice date ────────────────────────────────────────────────
        "date": "invoice_date",
        "voucher_date": "invoice_date",
        "invoice_date": "invoice_date",
        "bill_date": "invoice_date",
        "transaction_date": "invoice_date",
        # ── Due date ────────────────────────────────────────────────────
        "due_date": "due_date",
        "credit_due_date": "due_date",
        "payment_due_date": "due_date",
        "due_on": "due_date",
        "bill_due_date": "due_date",
        # ── Total amount ────────────────────────────────────────────────
        "amount": "total_amount",
        "net_amount": "total_amount",
        "total_amount": "total_amount",
        "invoice_amount": "total_amount",
        "bill_amount": "total_amount",
        "gross_amount": "total_amount",
        "value": "total_amount",
        "net_value": "total_amount",
        "dr/cr_amount": "total_amount",
        # ── Subtotal (optional) ─────────────────────────────────────────
        "subtotal": "subtotal",
        "taxable_amount": "subtotal",
        "assessable_value": "subtotal",
        "taxable_value": "subtotal",
        # ── GST / tax amount (optional) ─────────────────────────────────
        "gst_amount": "gst_amount",
        "tax_amount": "gst_amount",
        "igst_amount": "gst_amount",
        "sgst_amount": "gst_amount",
        "cgst_amount": "gst_amount",
        "total_gst": "gst_amount",
        "gst": "gst_amount",
        # Amount-already-paid / still-outstanding columns are deliberately
        # NOT listed here — they're not Tally-specific jargon, they're a
        # generic invoice concept every format shares, so ImportEngine
        # resolves them once, centrally (see OPTIONAL_MONEY_ALIASES and
        # infer_optional_money_columns in engine.py) instead of maintaining
        # three near-identical copies of the same alias list.
        # ── Description / narration (optional) ─────────────────────────
        "narration": "description",
        "description": "description",
        "particulars_description": "description",
        "item_description": "description",
        "remarks": "description",
        # ── Dr / Cr indicator — not used yet, kept for future use ───────
        "dr/cr": "dr_cr",
        "debit/credit": "dr_cr",
        "type": "dr_cr",
    }

    @classmethod
    def detect(cls, normalised_headers: list[str]) -> bool:
        """Detect Tally exports via voucher-style signature columns.

        Requires either a Tally-specific signature column, or at least 3
        recognisable aliases, to avoid false positives on generic CSV files.

        Yields to VyaparImporter when Vyapar-signature columns are present,
        because Vyapar files often share common column names (invoice_no,
        party_name, amount) that also match Tally aliases.
        """
        _VYAPAR_SIGNATURES = {"payment_status", "grand_total", "buyer_name"}
        if any(h in _VYAPAR_SIGNATURES for h in normalised_headers):
            return False  # let VyaparImporter handle it

        tally_signature_columns = {
            "voucher_no",
            "vch_no",
            "voucher_no.",
            "vch_no.",
            "voucher_date",
            "voucher_number",
            "vch._no.",
            "party_ledger_name",
            "ledger_name",
            "narration",
        }
        matched = sum(1 for h in normalised_headers if h in cls.COLUMN_ALIASES)
        has_signature = any(h in tally_signature_columns for h in normalised_headers)
        return has_signature or matched >= 3
