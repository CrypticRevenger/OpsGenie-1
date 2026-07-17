"""generate_invoice_pdf must never raise on names the core Helvetica font
can't encode.

fpdf2's built-in fonts are Latin-1 only and raise FPDFUnicodeEncodingException
on any character outside that range. This app's Indian distributors routinely
have dealer/product/business names in Odia/Hindi/Telugu, so the PDF builder
must downgrade those characters rather than crash — otherwise the whole
WhatsApp order-confirmation request would 500 before commit and wedge the
distributor on Meta's retry loop (see app/services/writes/pending_operation.py).
No DB needed — this is a pure function over a CreateOrderResult.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.services.invoice_pdf import generate_invoice_pdf
from app.services.writes.orders import CreateOrderResult, OrderLine


def _result(*, dealer_name: str, product_name: str) -> CreateOrderResult:
    line = OrderLine(
        product_id=None,
        product_name=product_name,
        quantity=Decimal("10"),
        unit_price=Decimal("400"),
        line_total=Decimal("4000"),
        gst_rate=Decimal("5"),
        gst_amount=Decimal("200"),
    )
    return CreateOrderResult(
        invoice_id=None,
        invoice_number="WA-abc1234567",
        invoice_date=date(2026, 7, 17),
        due_date=date(2026, 7, 31),
        dealer_id=None,
        dealer_name=dealer_name,
        dealer_phone="+919876543210",
        lines=[line],
        subtotal=Decimal("4000"),
        gst_amount=Decimal("200"),
        total_amount=Decimal("4200"),
        negative_stock_warnings=[],
    )


def test_pdf_renders_ascii_names() -> None:
    company = SimpleNamespace(business_name="AP BIOCARE", gst_number="21ABCDE1234F1Z5")
    out = generate_invoice_pdf(company, _result(dealer_name="Ram Traders", product_name="Rice"))
    assert out[:4] == b"%PDF"


def test_pdf_does_not_raise_on_devanagari_and_odia_names() -> None:
    # Hindi business/product name + Odia dealer name — all outside Latin-1.
    company = SimpleNamespace(business_name="श्री बायोकेयर", gst_number="21ABCDE1234F1Z5")
    out = generate_invoice_pdf(
        company,
        _result(dealer_name="ଶ୍ରୀ ଟ୍ରେଡର୍ସ", product_name="ଚାଉଳ (Rice)"),
    )
    assert out[:4] == b"%PDF"
    assert len(out) > 0
