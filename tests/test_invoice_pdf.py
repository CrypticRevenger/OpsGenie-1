"""Invoice PDF generation.

Two guarantees:
1. It never raises on names the core Helvetica font can't encode — Indian
   distributors routinely have dealer/product/business names in Odia/Hindi, so
   a crash here would 500 the WhatsApp order-confirmation before commit and
   wedge the distributor on Meta's retry loop (see writes/pending_operation.py).
2. When the bundled Noto fonts are present, those regional names + the real ₹
   glyph render (Unicode font embedded, no missing-glyph fallout); when they're
   absent, it still produces a valid PDF via the core-font path.

No DB — a pure function over a CreateOrderResult.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import app.services.invoice_pdf as invoice_pdf
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


def test_pdf_embeds_unicode_fonts_for_regional_names(caplog) -> None:
    """With the bundled Noto fonts, a Devanagari business name + Odia dealer/
    product names embed the Unicode font (not the core Helvetica fallback) and
    every glyph resolves — per-cell script selection must leave nothing unrendered.
    """
    company = SimpleNamespace(business_name="श्री बायोकेयर", gst_number="21ABCDE1234F1Z5")
    with caplog.at_level(logging.WARNING, logger="fpdf"):
        out = generate_invoice_pdf(
            company, _result(dealer_name="ଶ୍ରୀ ଟ୍ରେଡର୍ସ", product_name="ଚାଉଳ")
        )
    assert out[:4] == b"%PDF"
    assert b"NotoSans" in out  # a Noto subset is embedded …
    assert b"Helvetica" not in out  # … i.e. we're NOT on the core-font fallback
    # No character rendered as a missing/notdef box (the fpdf2 fallback bug the
    # per-cell font selection specifically avoids).
    assert not any("missing the following glyphs" in r.getMessage() for r in caplog.records)


def test_pdf_falls_back_to_core_font_when_bundled_fonts_absent(monkeypatch, tmp_path) -> None:
    """If the font files aren't on disk (stripped checkout / not-yet-dropped-in),
    the PDF still generates via core Helvetica — regional characters downgrade
    rather than crashing.
    """
    monkeypatch.setattr(invoice_pdf, "_FONT_DIR", tmp_path)  # empty dir → no fonts load
    company = SimpleNamespace(business_name="श्री बायोकेयर", gst_number="21ABCDE1234F1Z5")
    out = generate_invoice_pdf(company, _result(dealer_name="ଶ୍ରୀ", product_name="ଚାଉଳ"))
    assert out[:4] == b"%PDF"
    assert b"Helvetica" in out
    assert b"NotoSans" not in out
