"""Unit tests for app/services/importer/pdf_extractor.py — no DB required.

Regex ground truth for the private per-page parsers was captured directly
from pdfplumber against real Tally-generated voucher/invoice PDFs (see
scripts/convert_phase3_dataset.py, the one-off tool this module generalises).
That real dataset is gitignored (real customer records), so these tests
reproduce the same *text structure* synthetically instead.

fpdf2 (already a project dependency) writes each fixture as literal
sequential lines; a quick manual check confirmed pdfplumber's extract_text()
reproduces single-column fpdf2 output in the same line order it was
written in, so building a fixture this way faithfully exercises the real
bytes -> pdfplumber -> regex pipeline, not just the regexes in isolation.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.services.importer.errors import UnsupportedFileError
from app.services.importer.pdf_extractor import (
    INVOICE_HEADERS,
    PAYMENT_HEADERS,
    _clean_party_name,
    _extract_gst,
    _indian_date_to_iso,
    _page_kind,
    _parse_indian_amount,
    _parse_invoice_page,
    _parse_voucher_page,
    extract_invoice_rows_from_pdf,
    extract_payment_rows_from_pdf,
)
from fpdf import FPDF


def _pdf_bytes(*pages: list[str]) -> bytes:
    pdf = FPDF()
    for lines in pages:
        pdf.add_page()
        pdf.set_font("Helvetica", size=11)
        for line in lines:
            pdf.cell(0, 6, text=line, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


RECEIPT_VOUCHER_LINES = [
    "ACME AGRI SUPPLIES",
    "1 Market Road,",
    "Sometown-560001",
    "Receipt Voucher",
    "No. : 9 Dated : 6-Jan-26",
    "Particulars Amount",
    "Account :",
    "M/s.Reliable Medical Store 40,000.00",
    "Through :",
    "IDFC FIRST BANK",
    "Amount (in words) :",
    "INR Forty Thousand Only",
]

PAYMENT_VOUCHER_LINES = [
    "ACME AGRI SUPPLIES",
    "1 Market Road,",
    "Sometown-560001",
    "Payment Voucher",
    "No. : 35 Dated : 8-Jan-26",
    "Particulars Amount",
    "Account :",
    "NUTRICROP BIOSCIENCES 45,000.00",
    "Through :",
    "Cash",
    "On Account of :",
    "OUTWARD TRANSPORTATION",
    "Amount (in words) :",
    "INR Forty Five Thousand Only",
]

SALE_INVOICE_LINES = [
    "Bill of Supply",
    "ACME AGRI SUPPLIES Invoice No. Dated",
    "1 Market Road, 785 23-Jan-26",
    "Sometown-560001",
    "Buyer (Bill to)",
    "M/s.Reliable Medical Store Dispatched through Destination",
    "Soro, Baleswar",
    "Sl Description of Goods HSN/SAC GST Quantity Rate Amount",
    "1 Widget 2309 0 % 8 Btl 831.00 6,648.00",
    "Total (cid:299) 23,992.00",
    "Amount Chargeable (in words) E. & O.E",
]

SALE_INVOICE_WITH_EWAY_LINES = [
    "Bill of Supply",
    "ACME AGRI SUPPLIES Invoice No. e-Way Bill No. Dated",
    "1 Market Road, 834 13-Mar-26",
    "Sometown-560001",
    "Buyer (Bill to)",
    "M/s.Reliable Medical Store Dispatched through Destination",
    "Soro, Baleswar",
    "Total (cid:299) 78,445.00",
]

TAX_INVOICE_WITH_GST_LINES = [
    "Tax Invoice",
    "ACME AGRI SUPPLIES Invoice No. Dated",
    "1 Market Road, 851 28-Mar-26",
    "Sometown-560001",
    "Buyer (Bill to)",
    "M/s.Reliable Medical Store Dispatched through Destination",
    "Soro, Baleswar",
    "CGST 392.04",
    "SGST 392.04",
    "Less : Round Off (-)0.08",
    "Total (cid:299) 36,386.00",
]

PURCHASE_INVOICE_LINES = [
    "Bill of Supply",
    "SHAKTI TRADERS Invoice No. Dated",
    "2 Supplier Lane, 900 10-Feb-26",
    "Suppliertown-560002",
    "Supplier (Bill from)",
    "Shakti Traders",
    "Total (cid:299) 15,000.00",
]


# ── Page-kind classification ────────────────────────────────────────────────


def test_page_kind_detects_receipt_voucher() -> None:
    assert _page_kind("\n".join(RECEIPT_VOUCHER_LINES)) == "receipt_voucher"


def test_page_kind_detects_payment_voucher() -> None:
    assert _page_kind("\n".join(PAYMENT_VOUCHER_LINES)) == "payment_voucher"


def test_page_kind_detects_invoice() -> None:
    assert _page_kind("\n".join(SALE_INVOICE_LINES)) == "invoice"


def test_page_kind_unknown_for_unrelated_text() -> None:
    assert _page_kind("Just some random unrelated page content.") == "unknown"


# ── Small parsing helpers ───────────────────────────────────────────────────


def test_indian_date_to_iso() -> None:
    assert _indian_date_to_iso("23-Jan-26") == "2026-01-23"
    assert _indian_date_to_iso("6-Mar-26") == "2026-03-06"


def test_indian_date_to_iso_rejects_bad_format() -> None:
    with pytest.raises(ValueError):
        _indian_date_to_iso("2026-01-23")


def test_parse_indian_amount_handles_lakh_grouping() -> None:
    assert _parse_indian_amount("1,00,000.00") == Decimal("100000.00")


def test_clean_party_name_strips_ms_prefix() -> None:
    assert _clean_party_name("M/s.Reliable Medical Store") == "Reliable Medical Store"
    assert _clean_party_name("Siddha Mahaveer Agencies") == "Siddha Mahaveer Agencies"


def test_extract_gst_sums_cgst_and_sgst() -> None:
    text = "CGST 392.04\nSGST 392.04\n"
    assert _extract_gst(text) == Decimal("784.08")


def test_extract_gst_falls_back_to_igst() -> None:
    text = "IGST 500.00\n"
    assert _extract_gst(text) == Decimal("500.00")


def test_extract_gst_zero_when_absent() -> None:
    assert _extract_gst("no tax lines here") == Decimal("0.00")


# ── Per-page parsers (direct text, matching real pdfplumber ground truth) ──


def test_parse_voucher_page_receipt() -> None:
    row = _parse_voucher_page("\n".join(RECEIPT_VOUCHER_LINES))
    assert row["party_name"] == "Reliable Medical Store"
    assert row["payment_date"] == "2026-01-06"
    assert row["amount"] == "40000.00"
    assert row["method"] == "IDFC FIRST BANK"
    assert row["voucher_reference"] == "9"


def test_parse_voucher_page_payment_with_on_account_of() -> None:
    row = _parse_voucher_page("\n".join(PAYMENT_VOUCHER_LINES))
    assert row["party_name"] == "NUTRICROP BIOSCIENCES"
    assert row["payment_date"] == "2026-01-08"
    assert row["amount"] == "45000.00"
    assert row["method"] == "Cash"
    assert row["voucher_reference"] == "35"


def test_parse_voucher_page_missing_header_raises() -> None:
    with pytest.raises(ValueError, match="voucher number/date header"):
        _parse_voucher_page("nothing useful here")


def test_parse_invoice_page_receivable() -> None:
    row = _parse_invoice_page("\n".join(SALE_INVOICE_LINES), "receivable")
    assert row["invoice_number"] == "785"
    assert row["invoice_date"] == "2026-01-23"
    assert row["party_name"] == "Reliable Medical Store"
    assert row["total_amount"] == "23992.00"
    assert row["gst_amount"] == "0.00"
    assert row["subtotal"] == "23992.00"
    assert row["due_date"] == ""


def test_parse_invoice_page_receivable_with_eway_bill_no() -> None:
    row = _parse_invoice_page("\n".join(SALE_INVOICE_WITH_EWAY_LINES), "receivable")
    assert row["invoice_number"] == "834"
    assert row["invoice_date"] == "2026-03-13"
    assert row["total_amount"] == "78445.00"


def test_parse_invoice_page_with_cgst_sgst() -> None:
    row = _parse_invoice_page("\n".join(TAX_INVOICE_WITH_GST_LINES), "receivable")
    assert row["invoice_number"] == "851"
    assert row["total_amount"] == "36386.00"
    assert row["gst_amount"] == "784.08"
    assert row["subtotal"] == "35601.92"


def test_parse_invoice_page_payable_uses_supplier_bill_from() -> None:
    row = _parse_invoice_page("\n".join(PURCHASE_INVOICE_LINES), "payable")
    assert row["invoice_number"] == "900"
    assert row["party_name"] == "Shakti Traders"
    assert row["total_amount"] == "15000.00"


def test_parse_invoice_page_missing_buyer_raises() -> None:
    lines = [
        "Bill of Supply",
        "ACME AGRI SUPPLIES Invoice No. Dated",
        "1 Market Road, 785 23-Jan-26",
        "Total (cid:299) 23,992.00",
    ]
    with pytest.raises(ValueError, match="Buyer"):
        _parse_invoice_page("\n".join(lines), "receivable")


# ── Whole-file extraction (full bytes -> pdfplumber -> rows pipeline) ──────


def test_extract_invoice_rows_from_pdf_happy_path() -> None:
    contents = _pdf_bytes(SALE_INVOICE_LINES, TAX_INVOICE_WITH_GST_LINES)
    headers, rows = extract_invoice_rows_from_pdf(contents, "sale_register.pdf", "receivable")
    assert headers == INVOICE_HEADERS
    assert len(rows) == 2
    assert rows[0]["_pdf_parse_error"] == ""
    assert rows[0]["invoice_number"] == "785"
    assert rows[0]["source_file"] == "sale_register.pdf"
    assert rows[1]["invoice_number"] == "851"
    assert rows[1]["gst_amount"] == "784.08"


def test_extract_invoice_rows_from_pdf_rejects_voucher_page_with_friendly_error() -> None:
    contents = _pdf_bytes(RECEIPT_VOUCHER_LINES)
    headers, rows = extract_invoice_rows_from_pdf(contents, "mixed.pdf", "receivable")
    assert len(rows) == 1
    assert rows[0]["invoice_number"] == ""
    assert "Payments field" in rows[0]["_pdf_parse_error"]


def test_extract_payment_rows_from_pdf_happy_path() -> None:
    contents = _pdf_bytes(RECEIPT_VOUCHER_LINES, PAYMENT_VOUCHER_LINES)
    headers, rows = extract_payment_rows_from_pdf(contents, "receipts.pdf")
    assert headers == PAYMENT_HEADERS
    assert len(rows) == 2
    assert rows[0]["party_name"] == "Reliable Medical Store"
    assert rows[0]["amount"] == "40000.00"
    assert rows[1]["party_name"] == "NUTRICROP BIOSCIENCES"


def test_extract_payment_rows_from_pdf_rejects_invoice_page_with_friendly_error() -> None:
    contents = _pdf_bytes(SALE_INVOICE_LINES)
    headers, rows = extract_payment_rows_from_pdf(contents, "mixed.pdf")
    assert len(rows) == 1
    assert rows[0]["party_name"] == ""
    assert "Dealer/Supplier invoices field" in rows[0]["_pdf_parse_error"]


def test_extract_invoice_rows_rejects_corrupt_pdf() -> None:
    with pytest.raises(UnsupportedFileError):
        extract_invoice_rows_from_pdf(b"not a real pdf", "bad.pdf", "receivable")
