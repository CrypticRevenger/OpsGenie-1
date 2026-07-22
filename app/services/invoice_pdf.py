"""Invoice PDF generation — V0.2 (SPEC.md's "PDF generated -> sent to
Ram Traders" step of the WhatsApp invoice creation flow).

Pure function: takes the same CreateOrderResult app/services/writes/orders.py
already computed (no re-derivation, no DB access) and a Company for
business-identity fields, returns raw PDF bytes. Callers (currently
app/services/invoice_delivery.py) own uploading/sending it.

Layout is a branded letterhead-style invoice (company block + "INVOICE"
title + amount-due badge, Bill To + dates, a dark-header item table, a
totals block with a highlighted Total row, and a footer disclaimer) using
OpsGenie's own brand palette (the same emerald/dark-green tokens as the
marketing site and dashboard CSS) rather than a bare text dump.

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

# OpsGenie brand palette (same hex tokens as app/static/css/*.css's --brand
# custom properties) — kept as one RGB source here so the invoice never
# drifts from the site/dashboard's colors.
_BRAND_DARK = (6, 78, 59)  # #064e3b
_BRAND = (16, 185, 129)  # #10b981
_BRAND_TINT = (220, 252, 231)  # light emerald wash, for row striping / the Total row
_GRAY_TEXT = (107, 114, 128)  # #6b7280 — secondary text (address, dates)
_GRAY_LINE = (229, 231, 235)  # #e5e7eb — hairline rules
_INK = (17, 24, 39)  # #111827 — body text
_WHITE = (255, 255, 255)
_PAID = (185, 28, 28)  # #b91c1c — muted red, for the Payment Made (-) deduction

_MARGIN = 15
_PAGE_WIDTH = 210
_USABLE_WIDTH = _PAGE_WIDTH - 2 * _MARGIN  # 180mm

_COL_WIDTHS = (8, 68, 14, 24, 26, 14, 26)  # #, Item, Qty, Rate, Line Total, GST%, GST Amt
_COL_HEADERS = ("#", "Item", "Qty", "Rate", "Line Total", "GST%", "GST Amt")
_COL_ALIGN = ("L", "L", "R", "R", "R", "R", "R")


def _fit_to_width(pdf: FPDF, text: str, max_width: float) -> str:
    """Truncate `text` with a trailing "..." so it fits within `max_width` at
    whatever font/size is currently set on `pdf` — fpdf2's cell() doesn't wrap
    or shrink text to fit, so an unusually long product/dealer/business name
    would otherwise silently overlap whatever comes after it (a real product
    name like "Amoxicillin 500mg Veterinary Capsules (Strip of 10)" collided
    with the Qty column before this existed) instead of just being cut off
    cleanly. ASCII "..." rather than "…" so this degrades safely under the
    core-Helvetica/Latin-1 fallback path too. Must be called after the target
    font/size is already set on `pdf` — width measurement depends on it.
    """
    if pdf.get_string_width(text) <= max_width:
        return text
    truncated = text
    while truncated and pdf.get_string_width(truncated + "...") > max_width:
        truncated = truncated[:-1]
    return f"{truncated}..." if truncated else "..."


def generate_invoice_pdf(company: Company, result: CreateOrderResult) -> bytes:
    pdf = FPDF(format="A4")
    pdf.set_margins(_MARGIN, _MARGIN, _MARGIN)
    pdf.set_auto_page_break(auto=True, margin=_MARGIN)
    pdf.add_page()

    unicode_ok = _try_load_unicode_fonts(pdf)
    latin = _BASE_FONT if unicode_ok else "Helvetica"

    def money(amount: Decimal) -> str:
        return format_inr(amount) if unicode_ok else _rs(amount)

    def styled_cell(
        text: str,
        *,
        x: float,
        w: float,
        size: int,
        style: str = "",
        height: float = 6,
        align: str = "L",
        color: tuple[int, int, int] = _INK,
        script_aware: bool = False,
        fill: tuple[int, int, int] | None = None,
    ) -> None:
        """One cell of a manually-positioned two-column block: stays at `x`
        (so repeated calls build a vertical column) and advances y by
        `height`. `script_aware` selects a regional-script font for names
        (business/dealer/product); everything else stays on the Latin/base
        font, matching this module's existing per-cell rendering contract.
        """
        render = text if unicode_ok else _latin1(text)
        font = _font_for(text, unicode_ok=unicode_ok) if script_aware else latin
        pdf.set_xy(x, pdf.get_y())
        pdf.set_font(font, style, size)
        render = _fit_to_width(pdf, render, w - 2)
        pdf.set_text_color(*color)
        if fill is not None:
            pdf.set_fill_color(*fill)
        pdf.cell(w, height, render, align=align, fill=fill is not None, new_x="LEFT", new_y="NEXT")

    # ── Header: business identity (left) + INVOICE title/amount due (right) ──
    left_x, left_w = _MARGIN, 110
    right_x, right_w = _MARGIN + 110, _USABLE_WIDTH - 110
    top_y = pdf.get_y()

    pdf.set_y(top_y)
    styled_cell(
        company.business_name, x=left_x, w=left_w, size=17, style="B", height=8,
        color=_BRAND_DARK, script_aware=True,
    )
    if company.gst_number:
        styled_cell(f"GSTIN: {company.gst_number}", x=left_x, w=left_w, size=9, color=_GRAY_TEXT)
    if company.city:
        styled_cell(company.city, x=left_x, w=left_w, size=9, color=_GRAY_TEXT, script_aware=True)
    styled_cell(company.whatsapp_number, x=left_x, w=left_w, size=9, color=_GRAY_TEXT)
    left_bottom_y = pdf.get_y()

    pdf.set_y(top_y)
    styled_cell(
        "INVOICE", x=right_x, w=right_w, size=20, style="B", height=9,
        align="R", color=_BRAND_DARK,
    )
    styled_cell(
        f"# {result.invoice_number}", x=right_x, w=right_w, size=11, style="B",
        height=6, align="R", color=_INK,
    )
    pdf.ln(3)
    styled_cell(
        "AMOUNT DUE", x=right_x, w=right_w, size=8, style="B", height=6,
        align="C", color=_WHITE, fill=_BRAND,
    )
    styled_cell(
        money(result.balance_due), x=right_x, w=right_w, size=14, style="B",
        height=9, align="C", color=_WHITE, fill=_BRAND,
    )
    right_bottom_y = pdf.get_y()

    pdf.set_y(max(left_bottom_y, right_bottom_y) + 3)
    pdf.set_draw_color(*_BRAND)
    pdf.set_line_width(0.6)
    pdf.line(_MARGIN, pdf.get_y(), _PAGE_WIDTH - _MARGIN, pdf.get_y())
    pdf.ln(6)

    # ── Bill To (left) + Invoice/Due dates (right) ──────────────────────────
    top_y = pdf.get_y()

    pdf.set_y(top_y)
    styled_cell("Bill To", x=left_x, w=left_w, size=10, style="B", color=_BRAND_DARK)
    styled_cell(result.dealer_name, x=left_x, w=left_w, size=10, script_aware=True)
    if result.dealer_phone:
        styled_cell(result.dealer_phone, x=left_x, w=left_w, size=9, color=_GRAY_TEXT)
    left_bottom_y = pdf.get_y()

    pdf.set_y(top_y)
    styled_cell(
        f"Invoice Date: {result.invoice_date.isoformat()}", x=right_x, w=right_w,
        size=9, align="R",
    )
    styled_cell(
        f"Due Date: {result.due_date.isoformat()}", x=right_x, w=right_w, size=9, align="R",
    )
    right_bottom_y = pdf.get_y()

    pdf.set_y(max(left_bottom_y, right_bottom_y) + 6)

    # ── Item table ───────────────────────────────────────────────────────────
    pdf.set_x(_MARGIN)
    pdf.set_fill_color(*_BRAND_DARK)
    pdf.set_text_color(*_WHITE)
    pdf.set_font(latin, "B", 9)
    for header, width, align in zip(_COL_HEADERS, _COL_WIDTHS, _COL_ALIGN, strict=True):
        pdf.cell(width, 8, header, align=align, fill=True)
    pdf.ln(8)
    pdf.set_text_color(*_INK)

    for idx, item in enumerate(result.lines, start=1):
        pdf.set_x(_MARGIN)
        striped = idx % 2 == 0
        if striped:
            pdf.set_fill_color(*_BRAND_TINT)
        row_cells = (
            str(idx),
            item.product_name,
            str(item.quantity),
            money(item.unit_price),
            money(item.line_total),
            f"{item.gst_rate}%",
            money(item.gst_amount),
        )
        for col_idx, (text, width, align) in enumerate(
            zip(row_cells, _COL_WIDTHS, _COL_ALIGN, strict=True)
        ):
            script_aware = col_idx == 1  # the "Item" column only
            render = text if unicode_ok else _latin1(text)
            pdf.set_font(_font_for(text, unicode_ok=unicode_ok) if script_aware else latin, "", 9)
            if col_idx == 1:
                render = _fit_to_width(pdf, render, width - 2)
            pdf.cell(width, 7, render, align=align, fill=striped)
        pdf.ln(7)
    pdf.ln(4)

    # ── Totals ───────────────────────────────────────────────────────────────
    totals_w = 70
    totals_x = _PAGE_WIDTH - _MARGIN - totals_w
    label_w, value_w = 40, 30

    def totals_row(
        label: str,
        value: str,
        *,
        bold: bool = False,
        tint: bool = False,
        size: int = 10,
        color: tuple[int, int, int] | None = None,
    ) -> None:
        pdf.set_x(totals_x)
        pdf.set_font(latin, "B" if bold else "", size)
        pdf.set_text_color(*(color or (_BRAND_DARK if bold else _INK)))
        if tint:
            pdf.set_fill_color(*_BRAND_TINT)
        pdf.cell(label_w, 8 if bold else 7, label, align="R", fill=tint, new_x="RIGHT", new_y="TOP")
        pdf.cell(
            value_w, 8 if bold else 7, value, align="R", fill=tint, new_x="LMARGIN", new_y="NEXT"
        )
        pdf.set_text_color(*_INK)

    totals_row("Subtotal", money(result.subtotal))
    # No single "(X%)" label here — lines can carry different GST rates (see
    # the per-line GST% column above), so a lone percentage would mislead.
    totals_row("GST", money(result.gst_amount))
    if result.advance_paid > 0:
        # Only shown when a real advance was recorded — an invoice with no
        # advance keeps the single bold Total row below, matching the
        # simpler common case rather than always printing a redundant
        # "Payment Made: Rs. 0.00" line on every invoice.
        totals_row("Total", money(result.total_amount), bold=True)
        totals_row("Payment Made", f"(-) {money(result.advance_paid)}", color=_PAID)
        totals_row("Balance Due", money(result.balance_due), bold=True, tint=True, size=12)
    else:
        totals_row("Total", money(result.total_amount), bold=True, tint=True, size=12)
    pdf.ln(8)

    # ── Footer ───────────────────────────────────────────────────────────────
    pdf.set_draw_color(*_GRAY_LINE)
    pdf.set_line_width(0.2)
    pdf.line(_MARGIN, pdf.get_y(), _PAGE_WIDTH - _MARGIN, pdf.get_y())
    pdf.ln(3)
    # Not "I" (italic) — only regular/bold weights are registered for the
    # bundled Noto fonts (see pdf_common._FONT_FILES); an italic request
    # against an unregistered style raises FPDFException.
    pdf.set_font(latin, "", 8)
    pdf.set_text_color(*_GRAY_TEXT)
    pdf.cell(
        0, 5, "This is a computer-generated invoice, generated by OpsGenie.",
        align="C", new_x="LMARGIN", new_y="NEXT",
    )

    return bytes(pdf.output())
