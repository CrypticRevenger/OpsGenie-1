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
    PRODUCT_HEADERS,
    _clean_party_name,
    _ContinuedInvoicePage,
    _extract_gst,
    _indian_date_to_iso,
    _page_kind,
    _parse_indian_amount,
    _parse_invoice_page,
    _parse_voucher_page,
    extract_invoice_rows_from_pdf,
    extract_payment_rows_from_pdf,
    extract_product_rows_from_pdf,
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


def _stock_summary_pdf_bytes(
    heading: str, rows: list[tuple[str, str, str, str]], *, page_break_after: int | None = None
) -> bytes:
    """Build a synthetic Tally "Stock Group Summary" PDF with real column
    x-positions (Particulars in a fixed-width left cell, Quantity/Rate/Value
    in fixed-width cells to its right) — a flat sequential-line PDF (like
    _pdf_bytes above) can't reproduce the column geometry
    extract_product_rows_from_pdf actually keys on, since a blank product
    name that happens to *look* like a quantity (e.g. "Safegard 5 Ltr") is
    only distinguishable from a real quantity cell by x-position, not text
    shape. Verified against pdfplumber's real word coordinates, not assumed.

    Each row is (name, quantity_and_unit, rate, value); pass "" for any cell
    that should be blank (a zero-stock/no-cost-basis product).
    """

    def _header_lines(page_label: str) -> list[str]:
        return [
            "ACME AGRI SUPPLIES",
            "1 Market Road,",
            "Sometown-560001",
            heading,
            "Stock Group Summary",
            "1-Apr-26 to 27-Jul-26",
            page_label,
        ]

    def _write_table(pdf: FPDF, page_label: str) -> None:
        for line in _header_lines(page_label):
            pdf.cell(0, 6, text=line, new_x="LMARGIN", new_y="NEXT")
        pdf.set_x(10)
        pdf.cell(70, 6, text="Particulars")
        pdf.cell(0, 6, text="Closing Balance", new_x="LMARGIN", new_y="NEXT")
        pdf.set_x(10)
        pdf.cell(70, 6, text="")
        pdf.cell(40, 6, text="Quantity")
        pdf.cell(30, 6, text="Rate")
        pdf.cell(0, 6, text="Value", new_x="LMARGIN", new_y="NEXT")

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    _write_table(pdf, "Page 1")
    for i, (name, qty, rate, value) in enumerate(rows, start=1):
        if page_break_after is not None and i == page_break_after + 1:
            pdf.add_page()
            _write_table(pdf, "Page 2")
        pdf.set_x(10)
        pdf.cell(70, 6, text=name)
        pdf.cell(40, 6, text=qty)
        pdf.cell(30, 6, text=rate)
        pdf.cell(0, 6, text=value, new_x="LMARGIN", new_y="NEXT")
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

SALE_INVOICE_FISCAL_YEAR_INVOICE_NUMBER_LINES = [
    "Bill of Supply",
    "ACME AGRI SUPPLIES Invoice No. Dated",
    "1 Market Road, AP/BOS/12/26-27 23-Jan-26",
    "Sometown-560001",
    "Buyer (Bill to)",
    "M/s.Reliable Medical Store Dispatched through Destination",
    "Soro, Baleswar",
    "Total (cid:299) 23,992.00",
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

# Real Tally shape (see app/services/importer/pdf_extractor.py's
# _ContinuedInvoicePage docstring): item list too long for one page, so it
# spills onto a "(Page 2)" continuation that re-prints the full header and
# carries the running subtotal — only the final page has the real "Total".
SALE_INVOICE_MULTIPAGE_PAGE1_LINES = [
    "Bill of Supply",
    "ACME AGRI SUPPLIES Invoice No. Dated",
    "1 Market Road, 785 23-Jan-26",
    "Sometown-560001",
    "Buyer (Bill to)",
    "M/s.Reliable Medical Store Dispatched through Destination",
    "Soro, Baleswar",
    "Sl Description of Goods HSN/SAC GST Quantity Rate Amount",
    "1 Widget 2309 0 % 8 Btl 831.00 6,648.00",
    "continued ...",
]

SALE_INVOICE_MULTIPAGE_PAGE2_LINES = [
    "Bill of Supply(Page 2)",
    "ACME AGRI SUPPLIES Invoice No. Dated",
    "1 Market Road, 785 23-Jan-26",
    "Sometown-560001",
    "Buyer (Bill to)",
    "M/s.Reliable Medical Store Dispatched through Destination",
    "Soro, Baleswar",
    "Sl Description of Goods HSN/SAC GST Quantity Rate Amount",
    "2 Gadget 2309 0 % 2 Btl 500.00 1,000.00",
    "Total (cid:299) 7,648.00",
]

# A 3-page invoice: pages 1 and 2 both "continue", only page 3 has Total.
SALE_INVOICE_3PAGE_PAGE2_LINES = [
    "Bill of Supply(Page 2)",
    "ACME AGRI SUPPLIES Invoice No. Dated",
    "1 Market Road, 785 23-Jan-26",
    "Sometown-560001",
    "Buyer (Bill to)",
    "M/s.Reliable Medical Store Dispatched through Destination",
    "Soro, Baleswar",
    "Sl Description of Goods HSN/SAC GST Quantity Rate Amount",
    "2 Gadget 2309 0 % 2 Btl 500.00 1,000.00",
    "continued ...",
]

SALE_INVOICE_3PAGE_PAGE3_LINES = [
    "Bill of Supply(Page 3)",
    "ACME AGRI SUPPLIES Invoice No. Dated",
    "1 Market Road, 785 23-Jan-26",
    "Sometown-560001",
    "Buyer (Bill to)",
    "M/s.Reliable Medical Store Dispatched through Destination",
    "Soro, Baleswar",
    "Sl Description of Goods HSN/SAC GST Quantity Rate Amount",
    "3 Gizmo 2309 0 % 1 Btl 250.00 250.00",
    "Total (cid:299) 7,898.00",
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


def test_parse_invoice_page_invoice_number_with_fiscal_year_suffix() -> None:
    """Regression test: a prior version captured only the trailing digit run
    before the date ("(\\d+)\\s+(date)"), which truncated an invoice number
    like "AP/BOS/12/26-27" (a fiscal-year suffix — the Indian-Tally norm,
    real in AP BIOCARE's own export) down to bare "27". Taking the value
    line's last two whitespace tokens instead gets the full number, even with
    unrelated address text from the left column glued onto the same line.
    """
    row = _parse_invoice_page(
        "\n".join(SALE_INVOICE_FISCAL_YEAR_INVOICE_NUMBER_LINES), "receivable"
    )
    assert row["invoice_number"] == "AP/BOS/12/26-27"
    assert row["invoice_date"] == "2026-01-23"
    assert row["party_name"] == "Reliable Medical Store"


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


def test_parse_invoice_page_continued_page_raises_continued_invoice_page() -> None:
    """A page with no Total but a "continued ..." footer is a distinct case
    from a genuine parse failure — see _ContinuedInvoicePage's docstring."""
    with pytest.raises(_ContinuedInvoicePage, match="785"):
        _parse_invoice_page("\n".join(SALE_INVOICE_MULTIPAGE_PAGE1_LINES), "receivable")


def test_parse_invoice_page_no_total_and_no_continued_marker_raises_plain_valueerror() -> None:
    """Confirms the distinction is keyed on the "continued" marker, not just
    "no Total found" — a genuinely broken/blank invoice still raises the
    ordinary ValueError, not _ContinuedInvoicePage."""
    lines = [
        "Bill of Supply",
        "ACME AGRI SUPPLIES Invoice No. Dated",
        "1 Market Road, 785 23-Jan-26",
        "Sometown-560001",
        "Buyer (Bill to)",
        "M/s.Reliable Medical Store Dispatched through Destination",
        "Soro, Baleswar",
    ]
    with pytest.raises(ValueError) as exc_info:
        _parse_invoice_page("\n".join(lines), "receivable")
    assert not isinstance(exc_info.value, _ContinuedInvoicePage)
    assert "Total" in str(exc_info.value)


def test_parse_invoice_page_continued_mid_line_is_not_mistaken_for_footer() -> None:
    """The continuation footer match is anchored to line start — a totally
    different company's product catalogue could genuinely have a name like
    "Continued Care Formula" appear later in a line (never as a business's
    own name, generically any real product description), and that must
    still raise a plain parse failure, not be silently skipped as if it
    were Tally's own multi-page footer."""
    lines = [
        "Bill of Supply",
        "SOME OTHER COMPANY Invoice No. Dated",
        "9 Other Road, 42 01-Feb-26",
        "Othertown-560099",
        "Buyer (Bill to)",
        "Some Buyer Dispatched through Destination",
        "Elsewhere",
        "1 Continued Care Formula 500ml 2 Btl 100.00 200.00",
    ]
    with pytest.raises(ValueError) as exc_info:
        _parse_invoice_page("\n".join(lines), "receivable")
    assert not isinstance(exc_info.value, _ContinuedInvoicePage)
    assert "Total" in str(exc_info.value)


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


def test_extract_invoice_rows_from_pdf_multipage_invoice_skips_first_page() -> None:
    """The first page of a multi-page invoice is skipped (not failed) — its
    complete data (correct running total across every item on every page,
    per real Tally behaviour) is captured from the final page instead."""
    contents = _pdf_bytes(SALE_INVOICE_MULTIPAGE_PAGE1_LINES, SALE_INVOICE_MULTIPAGE_PAGE2_LINES)
    headers, rows = extract_invoice_rows_from_pdf(contents, "multipage.pdf", "receivable")
    assert headers == INVOICE_HEADERS
    assert len(rows) == 2

    assert rows[0]["_pdf_parse_error"] == ""
    assert rows[0]["_pdf_skip_reason"] != ""
    assert "785" in rows[0]["_pdf_skip_reason"]
    assert rows[0]["invoice_number"] == ""  # nothing parsed from the skipped page

    assert rows[1]["_pdf_parse_error"] == ""
    assert rows[1]["_pdf_skip_reason"] == ""
    assert rows[1]["invoice_number"] == "785"
    assert rows[1]["party_name"] == "Reliable Medical Store"
    assert rows[1]["total_amount"] == "7648.00"


def test_extract_invoice_rows_from_pdf_3page_invoice_only_last_page_succeeds() -> None:
    contents = _pdf_bytes(
        SALE_INVOICE_MULTIPAGE_PAGE1_LINES,
        SALE_INVOICE_3PAGE_PAGE2_LINES,
        SALE_INVOICE_3PAGE_PAGE3_LINES,
    )
    headers, rows = extract_invoice_rows_from_pdf(contents, "multipage3.pdf", "receivable")
    assert len(rows) == 3
    assert rows[0]["_pdf_skip_reason"] != ""
    assert rows[1]["_pdf_skip_reason"] != ""
    assert rows[2]["_pdf_skip_reason"] == ""
    assert rows[2]["_pdf_parse_error"] == ""
    assert rows[2]["invoice_number"] == "785"
    assert rows[2]["total_amount"] == "7898.00"


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


# ── Stock Group Summary (product/stock) extraction ─────────────────────────


def test_extract_product_rows_happy_path() -> None:
    contents = _stock_summary_pdf_bytes(
        "Goods@12%",
        [("Adult Feeder", "3 Pcs", "233.75", "701.25")],
    )
    headers, rows = extract_product_rows_from_pdf(contents, "12pct.pdf")
    assert headers == PRODUCT_HEADERS
    assert len(rows) == 1
    row = rows[0]
    assert row["_pdf_parse_error"] == ""
    assert row["name"] == "Adult Feeder"
    assert row["unit"] == "Pcs"
    assert row["stock_quantity"] == "3"
    assert row["purchase_price"] == "233.75"
    assert row["gst_rate"] == "12"
    assert row["source_file"] == "12pct.pdf"


def test_extract_product_rows_blank_row_is_zero_stock_not_a_failure() -> None:
    contents = _stock_summary_pdf_bytes("Goods@18%", [("Bell Drinker", "", "", "")])
    _headers, rows = extract_product_rows_from_pdf(contents, "18pct.pdf")
    assert len(rows) == 1
    assert rows[0]["_pdf_parse_error"] == ""
    assert rows[0]["name"] == "Bell Drinker"
    assert rows[0]["stock_quantity"] == ""
    assert rows[0]["gst_rate"] == "18"


def test_extract_product_rows_name_that_looks_like_a_quantity_stays_a_blank_product() -> None:
    """"Safegard 5 Ltr" is the product's whole *name* (a real Tally blank
    row) — text-only parsing can't tell this apart from a genuine "5 Ltr"
    quantity next to a shorter-named product; only the real column
    x-position can, which is exactly what this asserts.
    """
    contents = _stock_summary_pdf_bytes("Goods@18%", [("Safegard 5 Ltr", "", "", "")])
    _headers, rows = extract_product_rows_from_pdf(contents, "18pct.pdf")
    assert len(rows) == 1
    assert rows[0]["name"] == "Safegard 5 Ltr"
    assert rows[0]["unit"] == ""
    assert rows[0]["stock_quantity"] == ""


def test_extract_product_rows_imports_negative_quantity_qty_only_row_as_is() -> None:
    """A "(-)" closing quantity is real data (units sold with no matching
    purchase on file) — imported with the negative sign intact, never
    dropped or coerced to 0."""
    contents = _stock_summary_pdf_bytes(
        "12% Goods", [("Adult Feeder Stick", "(-)160 Nos", "", "")]
    )
    _headers, rows = extract_product_rows_from_pdf(contents, "neg.pdf")
    assert len(rows) == 1
    assert rows[0]["stock_quantity"] == "-160"
    assert rows[0]["unit"] == "Nos"
    assert rows[0]["_pdf_parse_error"] == ""


def test_extract_product_rows_imports_negative_quantity_full_row_as_is() -> None:
    contents = _stock_summary_pdf_bytes(
        "Exempted Goods", [("CHLROTAB-G 100g", "(-)53 Btl", "39.62", "2,100.00")]
    )
    _headers, rows = extract_product_rows_from_pdf(contents, "exempt.pdf")
    assert len(rows) == 1
    assert rows[0]["gst_rate"] == "0"
    assert rows[0]["stock_quantity"] == "-53"
    assert rows[0]["purchase_price"] == "39.62"
    assert rows[0]["_pdf_parse_error"] == ""


def test_extract_product_rows_excludes_grand_total_footer() -> None:
    contents = _stock_summary_pdf_bytes(
        "Tax Free Goods",
        [
            ("Gitacid-FS 1ltr", "12 Nos", "195.00", "2,340.00"),
            ("Grand Total", "", "", "2,340.00"),
        ],
    )
    _headers, rows = extract_product_rows_from_pdf(contents, "taxfree.pdf")
    assert len(rows) == 1
    assert rows[0]["name"] == "Gitacid-FS 1ltr"


@pytest.mark.parametrize(
    ("heading", "expected_rate"),
    [
        ("Goods@12%", "12"),
        ("Goods @ 18%", "18"),
        ("12% Goods", "12"),
        ("Exempted Goods", "0"),
        ("Tax Free Goods", "0"),
    ],
)
def test_extract_product_rows_gst_rate_heading_variants(heading: str, expected_rate: str) -> None:
    contents = _stock_summary_pdf_bytes(heading, [("Widget", "1 Pcs", "10.00", "10.00")])
    _headers, rows = extract_product_rows_from_pdf(contents, "variant.pdf")
    assert rows[0]["gst_rate"] == expected_rate


def test_extract_product_rows_continuation_page_repeats_column_header() -> None:
    """Tally's own continuation-page convention: every page of a multi-page
    group repeats the "Quantity Rate Value" column header, so the column
    x-position (and hence the name/data split) must be recomputed per page,
    not carried over from page 1.
    """
    contents = _stock_summary_pdf_bytes(
        "Goods@5%",
        [
            ("Amoclox Forte 250gm", "1 Pcs", "378.00", "378.00"),
            ("BIG FEEDER SET", "180 Pcs", "131.11", "23,600.00"),
        ],
        page_break_after=1,
    )
    _headers, rows = extract_product_rows_from_pdf(contents, "5pct.pdf")
    names = {r["name"] for r in rows}
    assert names == {"Amoclox Forte 250gm", "BIG FEEDER SET"}
    assert all(r["gst_rate"] == "5" for r in rows)


def test_extract_product_rows_rejects_file_with_no_gst_rate_heading() -> None:
    contents = _pdf_bytes(["Just some unrelated page content, not a stock report."])
    with pytest.raises(UnsupportedFileError):
        extract_product_rows_from_pdf(contents, "not_a_stock_report.pdf")
