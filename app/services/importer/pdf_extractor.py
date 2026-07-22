"""PDF importer — extracts invoice/payment rows out of Tally-style voucher
and invoice PDF printouts.

Some distributors don't have (or don't know how to produce) a Tally/Vyapar
CSV or Excel export — what they have is a folder of PDFs: "Multi Voucher
Print" style Receipt/Payment Vouchers (one voucher per page) and Bill of
Supply / Tax Invoice printouts (one invoice per page, with a full line-item
table). This module turns pages of either shape into the same canonical row
dicts the CSV/Excel importer already understands, so everything downstream
(``ImportEngine``, FIFO payment allocation, dedup) is reused unchanged.

Design notes
------------
* Detection and field extraction key off Tally's own generic template labels
  ("Invoice No.", "Buyer (Bill to)", "Supplier (Bill from)", "No. :",
  "Account :", "Through :", "CGST"/"SGST"/"IGST") — never a specific
  business's name or address. Verified against a real, ledger-reconciled
  dataset (see ``scripts/convert_phase3_dataset.py``, a one-off data-prep
  tool this module generalises into a product feature).
* One page failing to parse never fails the whole file. A page that doesn't
  match the expected content type (e.g. a payment voucher uploaded via the
  invoices field) gets a specific, actionable ``_pdf_parse_error`` message
  instead of a generic "row failed" — surfaced through the same per-row
  error plumbing csv/xlsx imports already use (see engine.py/payment_row.py's
  ``_pdf_parse_error`` check).
* Only line-items totals are extracted, never per-line detail — the
  Invoice/Payment models (and every canonical/Tally/Vyapar CSV path) only
  ever needed invoice-level totals, not line items.
* due_date is always left blank, same as every other format: none of these
  PDFs state one, and ImportEngine already falls back to the party's real
  payment_terms_days (never a guessed default) when it's blank.
"""

from __future__ import annotations

import io
import re
from decimal import Decimal
from typing import Literal

import pdfplumber

from app.services.importer.errors import UnsupportedFileError

Direction = Literal["receivable", "payable"]

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_AMOUNT_RE = r"[\d,]+\.\d{2}"
_DATE_RE = r"\d{1,2}-[A-Za-z]{3}-\d{2}"

INVOICE_HEADERS = [
    "invoice_number", "party_name", "invoice_date", "due_date",
    "subtotal", "gst_amount", "total_amount",
    "voucher_reference", "source_file", "_pdf_parse_error",
]

PAYMENT_HEADERS = [
    "party_name", "payment_date", "amount", "method",
    "voucher_reference", "source_file", "_pdf_parse_error",
]


# ── Small parsing helpers ───────────────────────────────────────────────────


def _indian_date_to_iso(raw: str) -> str:
    """'23-Jan-26' -> '2026-01-23'. 2-digit year assumed 2000+YY."""
    m = re.match(r"^(\d{1,2})-([A-Za-z]{3})-(\d{2})$", raw.strip())
    if not m:
        raise ValueError(f"unrecognised date '{raw}'")
    day, mon, yy = m.groups()
    month = _MONTHS.get(mon.lower())
    if month is None:
        raise ValueError(f"unrecognised month in date '{raw}'")
    return f"{2000 + int(yy):04d}-{month:02d}-{int(day):02d}"


def _parse_indian_amount(raw: str) -> Decimal:
    """'1,00,000.00' -> Decimal('100000.00'). Comma grouping is stripped, not parsed."""
    return Decimal(raw.replace(",", "").strip())


def _clean_party_name(raw: str) -> str:
    name = raw.strip()
    name = re.sub(r"^M/s\.?\s*", "", name, flags=re.IGNORECASE)
    return name.strip()


def _extract_gst(text: str) -> Decimal:
    cgst = re.search(rf"CGST\s+({_AMOUNT_RE})", text)
    sgst = re.search(rf"SGST\s+({_AMOUNT_RE})", text)
    if cgst and sgst:
        return _parse_indian_amount(cgst.group(1)) + _parse_indian_amount(sgst.group(1))
    igst = re.search(rf"IGST\s+({_AMOUNT_RE})", text)
    if igst:
        return _parse_indian_amount(igst.group(1))
    return Decimal("0.00")


def _page_kind(text: str) -> str:
    """Classify a page's content — never based on any specific business's name."""
    if re.search(r"Receipt\s+Voucher", text, re.IGNORECASE):
        return "receipt_voucher"
    if re.search(r"Payment\s+Voucher", text, re.IGNORECASE):
        return "payment_voucher"
    if re.search(r"Invoice\s*No\.", text, re.IGNORECASE) and re.search(
        r"Buyer\s*\(Bill\s*to\)|Supplier\s*\(Bill\s*from\)", text, re.IGNORECASE
    ):
        return "invoice"
    return "unknown"


# ── Per-page parsers ─────────────────────────────────────────────────────────


def _parse_voucher_page(text: str) -> dict[str, str]:
    """Parse one Receipt Voucher / Payment Voucher page.

    Labels ("No. :", "Dated :", "Account :", "Through :") are Tally's own
    generic voucher-print template — the same across every business.
    """
    header = re.search(rf"No\.\s*:\s*(\S+)\s+Dated\s*:\s*({_DATE_RE})", text)
    if not header:
        raise ValueError("could not find the voucher number/date header ('No. : ... Dated : ...')")
    voucher_no, raw_date = header.groups()

    account = re.search(rf"Account\s*:\s*\n(.+?)\s+({_AMOUNT_RE})\s*\n", text)
    if not account:
        raise ValueError("could not find the party name/amount under 'Account :'")
    party_raw, amount_raw = account.groups()

    method_match = re.search(r"Through\s*:\s*\n(.+?)\n", text)
    method = method_match.group(1).strip() if method_match else ""

    return {
        "party_name": _clean_party_name(party_raw),
        "payment_date": _indian_date_to_iso(raw_date),
        "amount": str(_parse_indian_amount(amount_raw)),
        "method": method,
        "voucher_reference": voucher_no,
    }


def _parse_invoice_page(text: str, direction: Direction) -> dict[str, str]:
    """Parse one Bill of Supply / Tax Invoice page.

    The invoice number/date always sit on the text line directly below the
    'Invoice No. ... Dated' label line, as the first (digits, date) pair on
    that line — regardless of what letterhead text precedes them, so this
    works for either party's own Tally template.
    """
    header = re.search(r"Invoice\s*No\.[^\n]*Dated\s*\n(.+)", text)
    if not header:
        raise ValueError("could not find the 'Invoice No. ... Dated' header line")
    numbers = re.search(rf"(\d+)\s+({_DATE_RE})", header.group(1))
    if not numbers:
        raise ValueError("could not find an invoice number/date pair on the header's value line")
    invoice_no, raw_date = numbers.groups()

    if direction == "receivable":
        party = re.search(
            r"Buyer\s*\(Bill\s*to\)\s*\n(.+?)\s+Dispatched\s+through", text, re.IGNORECASE
        )
        label = "Buyer (Bill to)"
    else:
        party = re.search(r"Supplier\s*\(Bill\s*from\)\s*\n(.+?)\n", text, re.IGNORECASE)
        label = "Supplier (Bill from)"
    if not party:
        raise ValueError(f"could not find the '{label}' party name")
    party_name = _clean_party_name(party.group(1))

    total_match = re.search(rf"\bTotal\b.{{0,20}}?({_AMOUNT_RE})", text)
    if not total_match:
        raise ValueError("could not find a 'Total' amount")
    total_amount = _parse_indian_amount(total_match.group(1))
    gst_amount = _extract_gst(text)
    subtotal = total_amount - gst_amount

    return {
        "invoice_number": invoice_no,
        "party_name": party_name,
        "invoice_date": _indian_date_to_iso(raw_date),
        "due_date": "",
        "subtotal": str(subtotal),
        "gst_amount": str(gst_amount),
        "total_amount": str(total_amount),
        "voucher_reference": invoice_no,
    }


# ── Whole-file extraction ────────────────────────────────────────────────────


def _open_pdf(contents: bytes, filename: str) -> pdfplumber.PDF:
    try:
        pdf = pdfplumber.open(io.BytesIO(contents))
    except Exception as exc:
        raise UnsupportedFileError(f"{filename!r} is not a valid PDF file.") from exc
    if len(pdf.pages) == 0:
        pdf.close()
        raise UnsupportedFileError(f"{filename!r} has no pages.")
    return pdf


def extract_invoice_rows_from_pdf(
    contents: bytes, filename: str, direction: Direction
) -> tuple[list[str], list[dict[str, str]]]:
    """Extract Bill of Supply / Tax Invoice pages into canonical invoice rows.

    A page that isn't a recognisable invoice (e.g. a Receipt/Payment Voucher,
    or a layout this parser doesn't understand) produces a row carrying only
    `_pdf_parse_error` — the caller's per-row loop turns that into a normal
    row-level failure, same as any other bad CSV row.
    """
    rows: list[dict[str, str]] = []
    with _open_pdf(contents, filename) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            kind = _page_kind(text)
            row = dict.fromkeys(INVOICE_HEADERS, "")
            row["source_file"] = filename
            if kind != "invoice":
                if kind in ("receipt_voucher", "payment_voucher"):
                    row["_pdf_parse_error"] = (
                        f"page {i} looks like a payment/receipt voucher, not an "
                        "invoice — upload it via the Payments field instead."
                    )
                else:
                    row["_pdf_parse_error"] = f"page {i}: unrecognised page layout"
                rows.append(row)
                continue
            try:
                row.update(_parse_invoice_page(text, direction))
                row["source_file"] = filename
            except ValueError as exc:
                row["_pdf_parse_error"] = f"page {i}: {exc}"
            rows.append(row)
    return INVOICE_HEADERS, rows


def extract_payment_rows_from_pdf(
    contents: bytes, filename: str
) -> tuple[list[str], list[dict[str, str]]]:
    """Extract Receipt Voucher / Payment Voucher pages into canonical payment rows."""
    rows: list[dict[str, str]] = []
    with _open_pdf(contents, filename) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            kind = _page_kind(text)
            row = dict.fromkeys(PAYMENT_HEADERS, "")
            row["source_file"] = filename
            if kind not in ("receipt_voucher", "payment_voucher"):
                if kind == "invoice":
                    row["_pdf_parse_error"] = (
                        f"page {i} looks like an invoice, not a payment/receipt "
                        "voucher — upload it via the Dealer/Supplier invoices field instead."
                    )
                else:
                    row["_pdf_parse_error"] = f"page {i}: unrecognised page layout"
                rows.append(row)
                continue
            try:
                row.update(_parse_voucher_page(text))
                row["source_file"] = filename
            except ValueError as exc:
                row["_pdf_parse_error"] = f"page {i}: {exc}"
            rows.append(row)
    return PAYMENT_HEADERS, rows
