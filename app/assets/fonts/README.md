# Bundled fonts — invoice PDF (Unicode rendering)

`app/services/invoice_pdf.py` embeds these to render regional-script dealer/
product/business names (Devanagari, Odia) and the real ₹ (U+20B9) glyph on
invoice PDFs. Without them the PDF still generates, but non-Latin-1 characters
downgrade to `?` and ₹ becomes `Rs.` (the graceful `_latin1` fallback path).

| File | Coverage |
|---|---|
| `NotoSans-Regular.ttf` / `NotoSans-Bold.ttf` | Latin + ₹ (base font) |
| `NotoSansDevanagari-Regular.ttf` | Hindi (Devanagari) — fpdf2 fallback |
| `NotoSansOriya-Regular.ttf` | Odia (Oriya) — fpdf2 fallback |

**Source:** Google Noto fonts (github.com/notofonts). **License:** SIL Open Font
License 1.1 (`OFL.txt`) — freely redistributable, so committing them here is
allowed. To refresh, re-download the same static hinted TTFs from the notofonts
project.
