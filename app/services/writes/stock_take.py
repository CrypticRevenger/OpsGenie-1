"""apply_stock_take — correction-workflow deterministic write service.

Called only from app/services/workflows/stock_take_flow.py, once the
distributor has confirmed the whole batch with an inline YES (this write is
in the "attribute edit" tier, same as update_stock/delete_product — not a
PendingOperation, since it's inventory counts, not a ledger figure). Never
commits (the caller commits once).

Applies every line in order, re-fetching each Product fresh — so if the same
product appears twice in one session (e.g. a correction to an earlier line),
the second line compounds on top of the first's already-applied result
rather than overwriting it blindly.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business_event import BusinessEvent, BusinessEventType
from app.models.company import Company
from app.models.product import Product


@dataclass(frozen=True)
class StockTakeLineResult:
    product_name: str
    old_quantity: Decimal
    new_quantity: Decimal


async def apply_stock_take(
    db: AsyncSession,
    company: Company,
    *,
    adjustments: list[dict],
    reason: str | None,
) -> list[StockTakeLineResult]:
    """Raises ValueError if a product from the session is no longer on file
    (e.g. deleted mid-session) — the caller turns this into a friendly
    reply rather than committing a partial batch silently.

    Negative stock is a flag, not a block — same convention
    app/services/writes/orders.py's negative_stock_warnings already uses.
    """
    results: list[StockTakeLineResult] = []
    for item in adjustments:
        product = await db.get(Product, uuid.UUID(item["product_id"]))
        if product is None or product.company_id != company.id:
            raise ValueError(f"'{item['product_name']}' is no longer in your catalogue")

        old_quantity = product.stock_quantity
        if item["mode"] == "delta":
            new_quantity = old_quantity + Decimal(item["value"])
        else:
            new_quantity = Decimal(item["value"])
        product.stock_quantity = new_quantity

        db.add(
            BusinessEvent(
                company_id=company.id,
                event_type=BusinessEventType.stock_adjusted,
                entity_type="product",
                entity_id=product.id,
                payload={
                    "product_name": product.name,
                    "old": str(old_quantity),
                    "new": str(new_quantity),
                    "mode": item["mode"],
                    "reason": reason,
                },
                created_by="whatsapp",
            )
        )
        results.append(
            StockTakeLineResult(
                product_name=product.name, old_quantity=old_quantity, new_quantity=new_quantity
            )
        )
    return results
