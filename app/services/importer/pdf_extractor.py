"""PDF importer — extracts invoice/payment/product rows out of Tally-style
voucher, invoice, and stock-report PDF printouts.

Some distributors don't have (or don't know how to produce) a Tally/Vyapar
CSV or Excel export — what they have is a folder of PDFs: "Multi Voucher
Print" style Receipt/Payment Vouchers (one voucher per page), Bill of
Supply / Tax Invoice printouts (one invoice per page, with a full line-item
table), and a "Stock Group Summary" report (one GST-rate group per file —
e.g. "Goods@12%", "Exempted Goods" — each listing every product's closing
quantity/rate/value). This module turns pages of any of these shapes into
the same canonical row dicts the CSV/Excel importer already understands, so
everything downstream (``ImportEngine``, FIFO payment allocation, dedup,
``run_product_import``) is reused unchanged.

Design notes
------------
* Detection and field extraction key off Tally's own generic template labels
  ("Invoice No.", "Buyer (Bill to)", "Supplier (Bill from)", "No. :",
  "Account :", "Through :", "CGST"/"SGST"/"IGST", "Stock Group Summary") —
  never a specific business's name or address. Verified against a real,
  ledger-reconciled dataset (see ``scripts/convert_phase3_dataset.py``, a
  one-off data-prep tool this module generalises into a product feature).
* One page failing to parse never fails the whole file. A page that doesn't
  match the expected content type (e.g. a payment voucher uploaded via the
  invoices field) gets a specific, actionable ``_pdf_parse_error`` message
  instead of a generic "row failed" — surfaced through the same per-row
  error plumbing csv/xlsx imports already use (see engine.py/payment_row.py/
  product_row.py's ``_pdf_parse_error`` check).
* Only line-items totals are extracted from invoices, never per-line detail
  — the Invoice/Payment models (and every canonical/Tally/Vyapar CSV path)
  only ever needed invoice-level totals, not line items. The stock report is
  the exception: it *is* a per-product line-item table, so that's exactly
  what ``extract_product_rows_from_pdf`` extracts.
* due_date is always left blank on invoices, same as every other format:
  none of these PDFs state one, and ImportEngine already falls back to the
  party's real payment_terms_days (never a guessed default) when it's blank.
* The stock report's Particulars/Quantity/Rate/Value table has no per-row
  labels the way vouchers/invoices do — it's pure column position. Some
  "blank" (zero-stock) product names happen to *look* like a quantity cell
  in plain text (e.g. a product literally named "Safegard 5 Ltr" prints
  identically, character-for-character-with-whitespace, to a real "5 Ltr"
  quantity next to a differently-named product) — apparent only once you
  extract actual word coordinates from a real file, not from eyeballing
  reconstructed table text. Text-only regexes over ``extract_text()`` can't
  tell these apart; ``extract_product_rows_from_pdf`` therefore reads
  ``page.extract_words()`` and splits each row at the real x-position of the
  "Quantity" column header instead, the same way a human reads the table.
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
_QTY_RE = r"[\d,]+(?:\.\d+)?"
_UNIT_RE = r"[A-Za-z][A-Za-z./]*"

INVOICE_HEADERS = [
    "invoice_number", "party_name", "invoice_date", "due_date",
    "subtotal", "gst_amount", "total_amount",
    "voucher_reference", "source_file", "_pdf_parse_error", "_pdf_skip_reason",
]

PAYMENT_HEADERS = [
    "party_name", "payment_date", "amount", "method",
    "voucher_reference", "source_file", "_pdf_parse_error",
]

# Column names chosen to match product_row.py's own alias tuples
# (_NAME_KEYS/_UNIT_KEYS/_STOCK_KEYS/_PURCHASE_KEYS/_GST_KEYS) exactly, so
# run_product_import needs no PDF-specific branch — it just sees a row shaped
# like any other product import.
PRODUCT_HEADERS = [
    "name", "unit", "stock_quantity", "purchase_price", "gst_rate",
    "source_file", "_pdf_parse_error",
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


class _ContinuedInvoicePage(ValueError):
    """Raised by _parse_invoice_page for a page that is the non-final part
    of a multi-page invoice (Tally's own "continued ..." / "continued to
    page number N" footer, printed when an invoice's item list doesn't fit
    on one page). Deliberately a distinct exception from a genuine parse
    failure — see extract_invoice_rows_from_pdf, which turns this into a
    skip rather than a row failure. Nothing is lost: Tally always re-prints
    the full header (party/date/GSTIN) *and* the running subtotal-so-far on
    every continuation page, so the invoice's one and only "Total" line
    — the real grand total for every item across every page — always lands
    on the final page, which parses as a complete, correct, standalone
    invoice on its own. Verified against a real 2-page purchase invoice and
    a real 2-page sales Bill of Supply (see tests).
    """


def _parse_invoice_page(text: str, direction: Direction) -> dict[str, str]:
    """Parse one Bill of Supply / Tax Invoice page.

    The invoice number/date always sit on the text line directly below the
    'Invoice No. ... Dated' label line, as the last two tokens on that line
    — regardless of what letterhead text precedes them, so this works for
    either party's own Tally template.
    """
    header = re.search(r"Invoice\s*No\.[^\n]*Dated\s*\n(.+)", text)
    if not header:
        raise ValueError("could not find the 'Invoice No. ... Dated' header line")
    # The value line is "<junk from the address column, if any> <invoice_no> <date>"
    # — pdfplumber's left-to-right text flow glues the letterhead/address block
    # (same row, left column) onto this line whenever it's still running when
    # the metadata table's value row is reached (real for AP BIOCARE's own
    # Bill-of-Supply/Tax-Invoice template, not just a synthetic edge case).
    # A prior version captured "(\d+)\s+(date)" — the last *digit run* before
    # the date — which truncates any invoice number containing non-digit
    # characters right before the date, e.g. "AP/BOS/1/26-27" (a fiscal-year
    # suffix, the Tally norm) came back as bare "27". Taking the last two
    # *whitespace-delimited tokens* instead is immune to that: the invoice
    # number is always exactly one token, so junk before it (itself
    # whitespace-separated) never bleeds in. Known gap: a filled-in "e-Way
    # Bill No." column would add a third trailing token and shift this off
    # by one — not seen in any real export so far, so not guarded against.
    tokens = header.group(1).split()
    if len(tokens) < 2 or not re.fullmatch(_DATE_RE, tokens[-1]):
        raise ValueError("could not find an invoice number/date pair on the header's value line")
    invoice_no, raw_date = tokens[-2], tokens[-1]

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
        # Tally's own generic multi-page footer — never a business's product
        # name or letterhead text — always sits alone at the start of its
        # own line ("continued ...", "continued to page number N"), unlike a
        # product description that merely happens to contain the word
        # "continued" somewhere later in a longer line (a different
        # company's catalogue could genuinely have one). Anchored to line
        # start so this only ever fires on Tally's real footer, regardless
        # of which company's data it's reading.
        if re.search(r"^continued\b", text, re.IGNORECASE | re.MULTILINE):
            raise _ContinuedInvoicePage(
                f"invoice {invoice_no} continues on a following page — its complete "
                "total is captured from there instead."
            )
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


# ── Stock Group Summary (product/stock) parsing ─────────────────────────────
#
# Unlike the voucher/invoice parsers above, there's no per-row label to
# anchor on — this is a plain Particulars/Quantity/Rate/Value table, one GST
# rate group per file. See the module docstring for why this reads word
# coordinates instead of matching text.

_GOODS_AT_PCT = re.compile(r"Goods\s*@\s*(\d+(?:\.\d+)?)\s*%", re.IGNORECASE)
_PCT_GOODS = re.compile(r"^(\d+(?:\.\d+)?)\s*%\s*Goods$", re.IGNORECASE)
_EXEMPTED_GOODS = re.compile(r"^Exempted\s+Goods$", re.IGNORECASE)
_TAX_FREE_GOODS = re.compile(r"^Tax\s*Free\s+Goods$", re.IGNORECASE)

# End-of-table / page-continuation markers — never product rows.
_STOCK_NOISE_PREFIX = re.compile(
    r"^(Grand\s+Total|Carried\s+Over|Brought\s+Forward|continued\b)", re.IGNORECASE
)

# A content row's *data* half (everything at/right of the Quantity column's
# x-position), once the name half has already been split off by position —
# see _split_stock_row. No ambiguity left to resolve here: a name that merely
# looks numeric never reaches these patterns, because it was never in this
# half of the row to begin with.
_STOCK_FULL_ROW = re.compile(
    rf"^(?P<qty_sign>\(-\))?(?P<qty>{_QTY_RE})\s+(?P<unit>{_UNIT_RE})\s+"
    rf"(?P<rate>{_AMOUNT_RE})\s+(?P<val_sign>\(-\))?(?P<value>{_AMOUNT_RE})$"
)
_STOCK_QTY_ONLY_ROW = re.compile(
    rf"^(?P<qty_sign>\(-\))?(?P<qty>{_QTY_RE})\s+(?P<unit>{_UNIT_RE})$"
)
_STOCK_VALUE_ONLY_ROW = re.compile(rf"^(\(-\))?{_AMOUNT_RE}$")


def _detect_stock_group_gst_rate(pdf: pdfplumber.PDF) -> Decimal | None:
    """The file's own group heading ("Goods@12%", "12% Goods", "Exempted
    Goods", "Tax Free Goods") is the *only* place the GST rate for every
    product in the file is stated — there's no per-row rate column. Searched
    line-by-line (not the whole page as one blob) so the heading is matched
    exactly, never as a coincidental substring elsewhere on the page.
    """
    for page in pdf.pages:
        text = page.extract_text() or ""
        for line in text.splitlines():
            line = line.strip()
            m = _GOODS_AT_PCT.search(line)
            if m:
                return Decimal(m.group(1))
            m = _PCT_GOODS.match(line)
            if m:
                return Decimal(m.group(1))
            if _EXEMPTED_GOODS.match(line) or _TAX_FREE_GOODS.match(line):
                return Decimal("0")
    return None


def _split_stock_row(
    row_words: list[dict], quantity_column_x0: float
) -> tuple[str, str]:
    """Split one table row's words into (name, data) at the real x-position
    of the "Quantity" column header — the geometric equivalent of "everything
    left of this column is the product name, everything at/right of it is
    quantity/rate/value". A 15pt margin absorbs normal sub-pixel rendering
    jitter without pulling a genuine name word rightward across the boundary.
    """
    threshold = quantity_column_x0 - 15
    name_words = [w["text"] for w in row_words if w["x0"] < threshold]
    data_words = [w["text"] for w in row_words if w["x0"] >= threshold]
    return " ".join(name_words).strip(), " ".join(data_words).strip()


def _parse_stock_group_page(page: pdfplumber.page.Page, gst_rate: Decimal) -> list[dict[str, str]]:
    """Parse one Stock Group Summary page into product rows. Every page of a
    multi-page group repeats its own "Quantity Rate Value" column header
    (Tally's continuation-page convention — see the real dataset), so the
    column x-position and the "has the table started yet" state are both
    recomputed fresh per page rather than carried over from page 1.
    """
    rows: list[dict[str, str]] = []
    words = page.extract_words()
    quantity_header = next((w for w in words if w["text"] == "Quantity"), None)
    if quantity_header is None:
        return rows  # letterhead-only page, or a layout this parser doesn't recognise

    header_top = quantity_header["top"]
    lines_by_top: dict[float, list[dict]] = {}
    for word in words:
        if word["top"] <= header_top:
            continue  # letterhead / group heading / column headers themselves
        lines_by_top.setdefault(round(word["top"], 1), []).append(word)

    for top in sorted(lines_by_top):
        row_words = sorted(lines_by_top[top], key=lambda w: w["x0"])
        name, data = _split_stock_row(row_words, quantity_header["x0"])
        full_line = f"{name} {data}".strip()
        if not name or _STOCK_NOISE_PREFIX.match(full_line) or "continued" in full_line.lower():
            continue  # Grand Total / Carried Over / Brought Forward / continuation marker

        row = dict.fromkeys(PRODUCT_HEADERS, "")
        row["name"] = name
        row["gst_rate"] = str(gst_rate)

        if not data:
            rows.append(row)  # no ledger movement at all -> zero stock, no cost basis
            continue

        full_match = _STOCK_FULL_ROW.match(data)
        qty_only_match = None if full_match else _STOCK_QTY_ONLY_ROW.match(data)
        match = full_match or qty_only_match
        if match:
            # A "(-)" closing quantity is a real data artifact — units sold
            # with no matching purchase on file (an opening stock that was
            # never entered, a transfer, a sample). Imported as-is, negative
            # sign and all, same convention Product.stock_quantity already
            # documents ("allowed to go negative ... since physical counts
            # can lag digital ones") and the same thing a live WhatsApp order
            # driving stock negative already does (see orders.py's
            # negative_stock_warnings) — never silently coerced to 0 or
            # dropped, which would both be a guess about what really
            # happened.
            qty = match["qty"].replace(",", "")
            row["unit"] = match["unit"]
            row["stock_quantity"] = f"-{qty}" if match["qty_sign"] else qty
            if full_match:
                row["purchase_price"] = match["rate"]
            rows.append(row)
            continue

        if _STOCK_VALUE_ONLY_ROW.match(data):
            # A leftover valuation with no quantity/rate at all (Tally
            # costing residue) — no reliable stock or price to record, so
            # this is treated the same as a blank row, not as an error.
            rows.append(row)
            continue

        row["_pdf_parse_error"] = f"{name!r}: unrecognised Quantity/Rate/Value shape {data!r}"
        rows.append(row)

    return rows


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
    row-level failure, same as any other bad CSV row. A page that's the
    non-final part of a multi-page invoice carries `_pdf_skip_reason`
    instead — the caller turns that into a skip, not a failure, since the
    invoice's complete data is captured from its own final page (see
    _ContinuedInvoicePage's docstring).
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
            except _ContinuedInvoicePage as exc:
                row["_pdf_skip_reason"] = f"page {i}: {exc}"
            except ValueError as exc:
                row["_pdf_parse_error"] = f"page {i}: {exc}"
            rows.append(row)
    return INVOICE_HEADERS, rows


def extract_product_rows_from_pdf(
    contents: bytes, filename: str
) -> tuple[list[str], list[dict[str, str]]]:
    """Extract a Tally "Stock Group Summary" PDF into canonical product/stock
    rows. Unlike the invoice/payment extractors, this rejects the whole file
    (``UnsupportedFileError``) rather than emitting per-row errors when no
    GST-rate group heading is found at all — a file with none isn't a
    misformatted stock report, it isn't a stock report.
    """
    with _open_pdf(contents, filename) as pdf:
        gst_rate = _detect_stock_group_gst_rate(pdf)
        if gst_rate is None:
            raise UnsupportedFileError(
                f"{filename!r} doesn't look like a Tally Stock Group Summary report "
                "(expected a GST-rate group heading like 'Goods@12%' or 'Exempted Goods')."
            )
        rows: list[dict[str, str]] = []
        for page in pdf.pages:
            for row in _parse_stock_group_page(page, gst_rate):
                row["source_file"] = filename
                rows.append(row)
    return PRODUCT_HEADERS, rows


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
