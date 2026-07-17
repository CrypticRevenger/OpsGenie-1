"""update_gst — Phase 2C deterministic write service.

Called only from app/services/writes/pending_operation.py's
execute_pending_operation, at confirm time. Mirrors create_order/
record_payment's shape: the guided flow
(app/services/workflows/gst_flow.py) only collects and previews raw user
input; this module re-resolves the product (for scope="product") fresh
against current DB state and performs the actual write.

Never commits — the caller (execute_pending_operation) commits once, same
contract as every other write-touching service in this codebase.

Only ever changes Company.gst_rate or Product.gst_rate going forward — it
never touches an existing InvoiceItem's gst_rate/gst_amount snapshot, so past
invoices keep showing whatever rate actually applied when they were created.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.product import Product


@dataclass(frozen=True)
class UpdateGstResult:
    scope: str
    product_name: str | None
    gst_rate: Decimal | None


async def update_gst(
    db: AsyncSession,
    company: Company,
    *,
    scope: str,
    gst_rate: Decimal | None,
    product_name: str | None = None,
) -> UpdateGstResult:
    """Set the company-wide default GST rate, or a single product's
    override.

    Raises ValueError if scope="product" and the product is no longer on
    file (e.g. deleted between preview and confirm) — the caller turns this
    into a friendly reply rather than committing bad data.
    """
    if scope == "all":
        if gst_rate is None:
            raise ValueError("A company-wide GST update needs a rate")
        company.gst_rate = gst_rate
        return UpdateGstResult(scope="all", product_name=None, gst_rate=gst_rate)

    if scope == "product":
        if not product_name:
            raise ValueError("A product-level GST update needs a product name")
        product = await db.scalar(
            select(Product).where(
                Product.company_id == company.id,
                func.lower(Product.name) == product_name.lower(),
            )
        )
        if product is None:
            raise ValueError(f"'{product_name}' is no longer in your catalogue")
        product.gst_rate = gst_rate
        return UpdateGstResult(scope="product", product_name=product.name, gst_rate=gst_rate)

    raise ValueError(f"Unknown GST update scope: {scope}")
