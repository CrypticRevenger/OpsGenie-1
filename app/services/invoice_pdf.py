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

from fpdf import FPDF

from app.models.company import Company
from app.services.money_format import format_inr
from app.services.reports.pdf_common import BASE_FONT as _BASE_FONT
from app.services.reports.pdf_common import font_for as _font_for
from app.services.reports.pdf_common import latin1 as _latin1
from app.services.reports.pdf_common import rs as _rs
from app.services.reports.pdf_common import try_load_unicode_fonts as _try_load_unicode_fonts
from app.services.writes.orders import CreateOrderResult


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
