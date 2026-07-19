"""Shared PDF rendering primitives — Unicode font handling (extracted from
app/services/invoice_pdf.py, byte-identical behavior there) plus a small
tabular-report helper for the new report PDFs (ledger, aging).

**Unicode rendering (multilingual):** when the bundled Noto fonts are present
under app/assets/fonts/, PDFs use NotoSans for Latin/₹ and switch to Noto Sans
Devanagari / Oriya per field for regional-script names — chosen *per cell* by
detecting the script of that cell's text (fpdf2's set_fallback_fonts
state-leaks the fallback onto later Latin cells and blanks their glyphs).
When a font file is missing, everything falls back to fpdf2's core Helvetica
(Latin-1 only) — non-Latin-1 characters degrade to `?` (`latin1`) and ₹ to
`Rs.` (`rs`) — so a valid PDF is always produced rather than raising.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path

from fpdf import FPDF

from app.services.money_format import format_inr

_FONT_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "fonts"
BASE_FONT = "NotoSans"
# (family, style, filename). Both weights per family so a bold cell (e.g. a
# header) renders in-script instead of a blank notdef box.
_FONT_FILES: tuple[tuple[str, str, str], ...] = (
    ("NotoSans", "", "NotoSans-Regular.ttf"),
    ("NotoSans", "B", "NotoSans-Bold.ttf"),
    ("NotoSansDevanagari", "", "NotoSansDevanagari-Regular.ttf"),
    ("NotoSansDevanagari", "B", "NotoSansDevanagari-Bold.ttf"),
    ("NotoSansOriya", "", "NotoSansOriya-Regular.ttf"),
    ("NotoSansOriya", "B", "NotoSansOriya-Bold.ttf"),
)
# Unicode block → font family for the per-cell script pick.
_SCRIPT_FONTS: tuple[tuple[int, int, str], ...] = (
    (0x0900, 0x097F, "NotoSansDevanagari"),  # Devanagari (Hindi)
    (0x0B00, 0x0B7F, "NotoSansOriya"),  # Oriya (Odia)
)


def rs(amount: Decimal) -> str:
    """₹ -> 'Rs. ' for the core-font fallback (₹ is outside Latin-1)."""
    return format_inr(amount).replace("₹", "Rs. ")


def latin1(text: str) -> str:
    """Downgrade characters fpdf2's core Helvetica can't encode (any non-Latin-1
    — e.g. Odia/Hindi names) to '?' so the fallback path never raises. Only used
    when the bundled Unicode fonts aren't available.
    """
    return text.encode("latin-1", "replace").decode("latin-1")


def try_load_unicode_fonts(pdf: FPDF) -> bool:
    """Register the bundled Noto fonts. Returns True when every font loaded (→
    regional-script names + real ₹ render), False if any file is missing or
    unreadable, so the caller uses the core-Helvetica + `latin1`/`rs` path and
    a PDF is still produced.
    """
    try:
        for family, style, filename in _FONT_FILES:
            path = _FONT_DIR / filename
            if not path.is_file():
                return False
            pdf.add_font(family, style, str(path))
    except Exception:  # noqa: BLE001 - any font-load error degrades to ASCII, never fails
        return False
    return True


def font_for(text: str, *, unicode_ok: bool) -> str:
    """The font family to render ``text`` in: a regional script font if the
    text contains that script, else the Latin base (or core Helvetica when the
    Unicode fonts aren't loaded)."""
    if not unicode_ok:
        return "Helvetica"
    for ch in text:
        code = ord(ch)
        for lo, hi, family in _SCRIPT_FONTS:
            if lo <= code <= hi:
                return family
    return BASE_FONT


def write_meta_header(
    pdf: FPDF,
    *,
    report_name: str,
    company_name: str,
    period_label: str,
    generated_at: datetime,
    unicode_ok: bool,
) -> None:
    """Company name + report title + period + generated-at, at the top of
    page 1 — same purpose as xlsx_common.write_meta_block for the Excel
    reports: confirms which report/period a reader is looking at.
    """

    def line(text: str, *, size: int, style: str = "", height: float = 6) -> None:
        render = text if unicode_ok else latin1(text)
        pdf.set_font(font_for(text, unicode_ok=unicode_ok), style, size)
        pdf.cell(0, height, render, new_x="LMARGIN", new_y="NEXT")

    line(company_name, size=14, style="B", height=8)
    line(report_name, size=12, style="B", height=7)
    latin = BASE_FONT if unicode_ok else "Helvetica"
    pdf.set_font(latin, "", 9)
    pdf.cell(0, 5, f"Period: {period_label}", new_x="LMARGIN", new_y="NEXT")
    generated_label = f"Generated: {generated_at.strftime('%d-%b-%Y %H:%M')}"
    pdf.cell(0, 5, generated_label, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)


def write_table(
    pdf: FPDF,
    *,
    headers: tuple[str, ...],
    col_widths: tuple[float, ...],
    rows: list[tuple[object, ...]],
    unicode_ok: bool,
    row_height: float = 7,
    header_size: int = 9,
    body_size: int = 9,
    bold_rows: set[int] = frozenset(),
) -> None:
    """A simple header + data-row grid — cells are already-formatted strings
    (₹ amounts, dates) the caller produced, this only lays them out.
    `bold_rows` (0-indexed into `rows`) is for total/closing-balance lines.
    fpdf2's default auto-page-break applies row by row; a repeating header on
    each new page isn't implemented — out of scope for typical report sizes.
    """
    latin = BASE_FONT if unicode_ok else "Helvetica"
    pdf.set_font(latin, "B", header_size)
    for header, width in zip(headers, col_widths, strict=True):
        pdf.cell(width, row_height, header, border="B")
    pdf.ln(row_height)

    for idx, values in enumerate(rows):
        style = "B" if idx in bold_rows else ""
        for value, width in zip(values, col_widths, strict=True):
            text = "" if value is None else str(value)
            rendered = text if unicode_ok else latin1(text)
            pdf.set_font(font_for(text, unicode_ok=unicode_ok), style, body_size)
            pdf.cell(width, row_height, rendered)
        pdf.ln(row_height)
