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


async def find_party(
    db: AsyncSession, company_id: uuid.UUID, direction: Direction, name: str
) -> Dealer | Supplier | None:
    """Case-insensitive exact match on name, scoped to the company — the
    lookup half of find_or_create_party, exposed separately for callers that
    need to know whether a party already exists *before* deciding whether to
    create one (e.g. onboarding's new-party confirmation).

    Uses func.lower() equality rather than ilike() — ilike treats '%' and '_'
    in *name* as wildcards, which would silently mismatch/merge real party
    names containing those literal characters (e.g. "100% Organic Traders").
    """
    model = _PARTY_MODEL[direction]
    return await db.scalar(
        select(model).where(model.company_id == company_id, func.lower(model.name) == name.lower())
    )


async def find_or_create_party(
    db: AsyncSession,
    company_id: uuid.UUID,
    direction: Direction,
    name: str,
    *,
    phone: str | None = None,
) -> Dealer | Supplier:
    """find_party, creating a new row if no match exists.

    `phone` only ever applies on the create branch — an existing party found
    by name is returned completely unchanged, never overwriting a phone
    already on file. Every call site except order_flow.py's inline new-
    dealer path (via writes/orders.py::create_order) omits it and gets the
    same phone-less row this always created before.
    """
    existing = await find_party(db, company_id, direction, name)
    if existing is not None:
        return existing
    model = _PARTY_MODEL[direction]
    party = model(company_id=company_id, name=name, phone=phone)
    db.add(party)
    await db.flush()
    return party
