"""Party (Dealer/Supplier) resolution shared by invoice and payment import."""

from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dealer import Dealer
from app.models.supplier import Supplier

Direction = Literal["receivable", "payable"]

_PARTY_MODEL: dict[str, type[Dealer] | type[Supplier]] = {
    "receivable": Dealer,
    "payable": Supplier,
}


async def find_or_create_party(
    db: AsyncSession, company_id: uuid.UUID, direction: Direction, name: str
) -> Dealer | Supplier:
    """Case-insensitive exact match on name, scoped to the company; create if absent.

    Uses func.lower() equality rather than ilike() — ilike treats '%' and '_'
    in *name* as wildcards, which would silently mismatch/merge real party
    names containing those literal characters (e.g. "100% Organic Traders").
    """
    model = _PARTY_MODEL[direction]
    existing = await db.scalar(
        select(model).where(
            model.company_id == company_id, func.lower(model.name) == name.lower()
        )
    )
    if existing is not None:
        return existing
    party = model(company_id=company_id, name=name)
    db.add(party)
    await db.flush()
    return party
