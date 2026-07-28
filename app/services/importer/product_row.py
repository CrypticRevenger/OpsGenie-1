"""Product/stock CSV, Excel, or Tally "Stock Group Summary" PDF import — the
"Product & Current Stock" upload on the self-serve onboarding wizard (POST
/onboard/{id}/import). Wired through ImportEngine.run_import's file_kind
dispatch (engine.py), so the founder admin route gets this for free too.

The PDF path (one GST-rate group per file — app/services/importer/
pdf_extractor.py's extract_product_rows_from_pdf) already emits rows keyed
by exactly the same canonical names this module's own alias tuples resolve
to ("name", "unit", "stock_quantity", "purchase_price", "gst_rate"), so no
PDF-specific branch is needed here beyond the `_pdf_parse_error` check below
— every other line of this module treats a PDF-derived row identically to a
CSV/Excel one.

No direction (products aren't receivable/payable) and no dedup-by-natural-
key the way invoices dedupe on invoice_number — a product's only identity
is its name within a company, and unlike an invoice number that's not
guaranteed unique in the real world (two different SKUs can share a display
name). Re-importing the same file creates duplicate Product rows; this
matches the WhatsApp bulk-paste flow's own behaviour for a repeated name
(see onboarding_flow.py's _parse_bulk_line) — a known, deliberately
deferred gap, not a new inconsistency this import path introduces.

Column headers are alias-matched (case/whitespace-insensitive, via
normalise_header) rather than fixed-position, same robustness principle as
the invoice importers' COLUMN_ALIASES — a real export's column order and
exact wording vary.
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.services.gst import parse_gst_rate
from app.services.importer.errors import UnrecognisedFormatError
from app.services.importer.normalizer import (
    normalise_header,
    parse_amount,
    parse_positive_amount,
    row_by_normalised_header,
)
from app.services.importer.result import ImportResult

logger = logging.getLogger(__name__)

_NAME_KEYS = ("name", "product_name", "product", "item", "item_name")
_PURCHASE_KEYS = ("purchase_price", "cost_price", "cost")
_SELLING_KEYS = ("selling_price", "price", "rate", "sale_price")
_UNIT_KEYS = ("unit", "uom", "units")
_STOCK_KEYS = ("stock", "quantity", "stock_quantity", "qty", "current_stock")
_GST_KEYS = ("gst", "gst_rate", "gst%", "tax_rate")


def _first_present(row: dict[str, str], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = row.get(key, "").strip()
        if value:
            return value
    return ""


async def run_product_import(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    filename: str,
    headers: list[str],
    rows: list[dict[str, str]],
    result: ImportResult,
) -> ImportResult:
    """Parse and persist a product/stock file. Raises UnrecognisedFormatError
    for a whole-file rejection (no recognisable name column); per-row
    problems are captured in the returned ImportResult, never raised — same
    contract as run_import/run_payment_import.
    """
    normalised_headers = {normalise_header(h) for h in headers}
    if not normalised_headers & set(_NAME_KEYS):
        raise UnrecognisedFormatError(
            "Couldn't find a product name column. Expected a header like 'Name' or 'Product Name'."
        )

    for row_number, raw_row in enumerate(rows, start=1):
        try:
            async with db.begin_nested():
                pdf_parse_error = raw_row.get("_pdf_parse_error", "").strip()
                if pdf_parse_error:
                    raise ValueError(pdf_parse_error)
                normalised_row = row_by_normalised_header(raw_row, headers)
                name = _first_present(normalised_row, _NAME_KEYS)
                if not name:
                    raise ValueError("product name is required")

                purchase_raw = _first_present(normalised_row, _PURCHASE_KEYS)
                selling_raw = _first_present(normalised_row, _SELLING_KEYS)
                stock_raw = _first_present(normalised_row, _STOCK_KEYS)
                gst_raw = _first_present(normalised_row, _GST_KEYS)
                unit = _first_present(normalised_row, _UNIT_KEYS) or None

                try:
                    purchase_price = parse_positive_amount(purchase_raw) if purchase_raw else None
                except ValueError as exc:
                    raise ValueError(f"'{name}': purchase price — {exc}") from exc
                try:
                    selling_price = parse_positive_amount(selling_raw) if selling_raw else None
                except ValueError as exc:
                    raise ValueError(f"'{name}': selling price — {exc}") from exc
                try:
                    # Not parse_nonnegative_amount: a negative stock figure
                    # (Tally's "(-)" closing quantity — units sold with no
                    # matching purchase on file) is real data, not something
                    # to reject at the door. Product.stock_quantity already
                    # documents "allowed to go negative ... since physical
                    # counts can lag digital ones" for the same reason a live
                    # order can drive stock negative (see orders.py).
                    stock = parse_amount(stock_raw) if stock_raw else Decimal("0")
                except ValueError as exc:
                    raise ValueError(f"'{name}': stock — {exc}") from exc
                try:
                    gst_rate = parse_gst_rate(gst_raw) if gst_raw else None
                except ValueError as exc:
                    raise ValueError(f"'{name}': GST — {exc}") from exc

                db.add(
                    Product(
                        company_id=company_id,
                        name=name,
                        unit=unit,
                        selling_price=selling_price,
                        purchase_price=purchase_price,
                        gst_rate=gst_rate,
                        stock_quantity=stock,
                    )
                )
                result.add_success()
        except Exception as exc:  # noqa: BLE001 - row-level isolation is intentional
            logger.warning("Product row %d failed in %s: %s", row_number, filename, exc)
            result.add_failure(row_number, str(exc), raw_value=str(raw_row))

    await db.commit()
    return result
