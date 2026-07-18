"""Invoice PDF generation — V0.2 (SPEC.md's "PDF generated -> sent to
Ram Traders" step of the WhatsApp invoice creation flow).

Pure function: takes the same CreateOrderResult app/services/writes/orders.py
already computed (no re-derivation, no DB access) and a Company for
business-identity fields, returns raw PDF bytes. Callers (currently
app/services/invoice_delivery.py) own uploading/sending it.

**Unicode rendering (multilingual):** when the bundled Noto fonts are present
under app/assets/fonts/, the PDF uses NotoSans for Latin/₹ and switches to
Noto Sans Devanagari / Oriya per field for regional-script dealer/product/
business names — so those names render correctly and amounts show the real ₹
glyph. The font is chosen *per cell* by detecting the script of that cell's
text (rather than fpdf2's set_fallback_fonts, which state-leaks the fallback
onto later Latin cells and blanks their glyphs). Structural labels (Invoice,
Bill To, column headers) stay English: Indian B2B invoices are conventionally
English, and this goes to the *dealer*, whose language OpsGenie doesn't track.

When a font file is missing (a stripped checkout, or before the binaries are
dropped in), it falls back to fpdf2's core Helvetica — Latin-1 only —
downgrading non-Latin-1 characters to `?` (`_latin1`) and ₹ to `Rs.` (`_rs`),
so a valid PDF is *always* produced rather than raising. The `def0c1c`
non-blocking wrapper in pending_operation.py is the outer safety net.

Known limit: a single *mixed*-script name (e.g. "ଚାଉଳ (Rice)") renders in its
first regional script's font; the Latin run inside it degrades to blank rather
than crashing — rare, and never affects the critical ASCII content (number,
dates, amounts).
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from fpdf import FPDF

from app.models.company import Company
from app.services.money_format import format_inr
from app.services.writes.orders import CreateOrderResult

_FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
_BASE_FONT = "NotoSans"
# (family, style, filename). Both weights per family so a bold cell (e.g. the
# business-name header) renders in-script instead of a blank notdef box.
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


def _rs(amount: Decimal) -> str:
    """₹ -> 'Rs. ' for the core-font fallback (₹ is outside Latin-1)."""
    return format_inr(amount).replace("₹", "Rs. ")


def _latin1(text: str) -> str:
    """Downgrade characters fpdf2's core Helvetica can't encode (any non-Latin-1
    — e.g. Odia/Hindi names) to '?' so the fallback path never raises. Only used
    when the bundled Unicode fonts aren't available.
    """
    return text.encode("latin-1", "replace").decode("latin-1")


def _try_load_unicode_fonts(pdf: FPDF) -> bool:
    """Register the bundled Noto fonts. Returns True when every font loaded (→
    regional-script names + real ₹ render), False if any file is missing or
    unreadable, so the caller uses the core-Helvetica + `_latin1`/`_rs` path and
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


def _font_for(text: str, *, unicode_ok: bool) -> str:
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
    return _BASE_FONT


def generate_invoice_pdf(company: Company, result: CreateOrderResult) -> bytes:
    pdf = FPDF(format="A4")
    pdf.add_page()

    unicode_ok = _try_load_unicode_fonts(pdf)

    def money(amount: Decimal) -> str:
        return format_inr(amount) if unicode_ok else _rs(amount)

    def line(text: str, *, size: int, style: str = "", height: float = 6, align: str = "") -> None:
        """A full-width line whose font follows the text's script (names) or
        stays Latin (labels/amounts)."""
        render = text if unicode_ok else _latin1(text)
        pdf.set_font(_font_for(text, unicode_ok=unicode_ok), style, size)
        pdf.cell(0, height, render, new_x="LMARGIN", new_y="NEXT", align=align)

    line(company.business_name, size=16, style="B", height=10)
    if company.gst_number:
        line(f"GSTIN: {company.gst_number}", size=10)
    pdf.ln(4)

    line(f"Invoice {result.invoice_number}", size=13, style="B", height=8)
    line(f"Invoice date: {result.invoice_date.isoformat()}", size=10)
    line(f"Due date: {result.due_date.isoformat()}", size=10)
    pdf.ln(4)

    line("Bill To", size=11, style="B")
    line(result.dealer_name, size=10)
    if result.dealer_phone:
        line(result.dealer_phone, size=10)
    pdf.ln(6)

    col_widths = (58, 16, 26, 28, 16, 30)
    headers = ("Item", "Qty", "Unit Price", "Line Total", "GST%", "GST Amt")
    pdf.set_font(_BASE_FONT if unicode_ok else "Helvetica", "B", 10)
    for header, width in zip(headers, col_widths, strict=True):
        pdf.cell(width, 8, header, border="B")
    pdf.ln()

    latin = _BASE_FONT if unicode_ok else "Helvetica"
    for item in result.lines:
        product = item.product_name if unicode_ok else _latin1(item.product_name)
        pdf.set_font(_font_for(item.product_name, unicode_ok=unicode_ok), "", 10)
        pdf.cell(col_widths[0], 8, product)
        pdf.set_font(latin, "", 10)  # numeric columns are always ASCII/₹
        pdf.cell(col_widths[1], 8, str(item.quantity))
        pdf.cell(col_widths[2], 8, money(item.unit_price))
        pdf.cell(col_widths[3], 8, money(item.line_total))
        pdf.cell(col_widths[4], 8, f"{item.gst_rate}%")
        pdf.cell(col_widths[5], 8, money(item.gst_amount))
        pdf.ln()
    pdf.ln(4)

    pdf.set_font(latin, "", 10)
    pdf.cell(0, 6, f"Subtotal: {money(result.subtotal)}", new_x="LMARGIN", new_y="NEXT", align="R")
    # No single "(X%)" label here — lines can carry different GST rates (see
    # the per-line GST% column above), so a lone percentage would mislead.
    pdf.cell(0, 6, f"GST: {money(result.gst_amount)}", new_x="LMARGIN", new_y="NEXT", align="R")
    pdf.set_font(latin, "B", 12)
    pdf.cell(0, 8, f"Total: {money(result.total_amount)}", new_x="LMARGIN", new_y="NEXT", align="R")

    return bytes(pdf.output())
