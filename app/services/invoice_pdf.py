"""Invoice PDF generation — V0.2 (SPEC.md's "PDF generated -> sent to
Ram Traders" step of the WhatsApp invoice creation flow).

Pure function: takes the same CreateOrderResult app/services/writes/orders.py
already computed (no re-derivation, no DB access) and a Company for
business-identity fields, returns raw PDF bytes. Callers (currently
app/services/invoice_delivery.py) own uploading/sending it.

Uses fpdf2's core Helvetica font, which only supports Latin-1 — so amounts
use "Rs." instead of format_inr's "₹" glyph (Indian Rupee sign is outside
Latin-1 and would need a bundled Unicode TTF to render otherwise).
"""

from __future__ import annotations

from decimal import Decimal

from fpdf import FPDF

from app.models.company import Company
from app.services.money_format import format_inr
from app.services.writes.orders import CreateOrderResult


def _rs(amount: Decimal) -> str:
    return format_inr(amount).replace("₹", "Rs. ")


def generate_invoice_pdf(company: Company, result: CreateOrderResult) -> bytes:
    pdf = FPDF(format="A4")
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, company.business_name, new_x="LMARGIN", new_y="NEXT")
    if company.gst_number:
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, f"GSTIN: {company.gst_number}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, f"Invoice {result.invoice_number}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(
        0, 6, f"Invoice date: {result.invoice_date.isoformat()}", new_x="LMARGIN", new_y="NEXT"
    )
    pdf.cell(0, 6, f"Due date: {result.due_date.isoformat()}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, "Bill To", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, result.dealer_name, new_x="LMARGIN", new_y="NEXT")
    if result.dealer_phone:
        pdf.cell(0, 6, result.dealer_phone, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    col_widths = (80, 30, 35, 35)
    pdf.set_font("Helvetica", "B", 10)
    for header, width in zip(("Item", "Qty", "Unit Price", "Line Total"), col_widths, strict=True):
        pdf.cell(width, 8, header, border="B")
    pdf.ln()

    pdf.set_font("Helvetica", "", 10)
    for line in result.lines:
        pdf.cell(col_widths[0], 8, line.product_name)
        pdf.cell(col_widths[1], 8, str(line.quantity))
        pdf.cell(col_widths[2], 8, _rs(line.unit_price))
        pdf.cell(col_widths[3], 8, _rs(line.line_total))
        pdf.ln()
    pdf.ln(4)

    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Subtotal: {_rs(result.subtotal)}", new_x="LMARGIN", new_y="NEXT", align="R")
    pdf.cell(
        0,
        6,
        f"GST ({company.gst_rate}%): {_rs(result.gst_amount)}",
        new_x="LMARGIN",
        new_y="NEXT",
        align="R",
    )
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, f"Total: {_rs(result.total_amount)}", new_x="LMARGIN", new_y="NEXT", align="R")

    return bytes(pdf.output())
