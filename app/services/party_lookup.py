"""Party name resolution — the dealer-then-supplier case-insensitive
substring match shared by app/services/agent/read_tools.py's
`_get_party_balance` (LLM tool + "balance <name>" deterministic command) and
the new "ledger <name>" WhatsApp command, so both resolve a name through the
exact same query instead of two independently-drifting copies of it.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dealer import Dealer
from app.models.supplier import Supplier
from app.services.party_outstanding import Direction


async def find_party(
    db: AsyncSession, company_id: uuid.UUID, name: str
) -> tuple[Dealer | Supplier, Direction] | None:
    """A Dealer match wins over a Supplier match on the same substring.
    `.limit(1)` means an ambiguous multi-match silently returns whichever
    row the DB orders first — same behavior this query already had inline
    in `_get_party_balance`, just centralized rather than changed.
    """
    like = f"%{name.strip().lower()}%"
    dealer = await db.scalar(
        select(Dealer)
        .where(Dealer.company_id == company_id, func.lower(Dealer.name).like(like))
        .limit(1)
    )
    if dealer is not None:
        return dealer, "receivable"
    supplier = await db.scalar(
        select(Supplier)
        .where(Supplier.company_id == company_id, func.lower(Supplier.name).like(like))
        .limit(1)
    )
    if supplier is not None:
        return supplier, "payable"
    return None


async def get_party_by_id(
    db: AsyncSession, company_id: uuid.UUID, party_id: uuid.UUID
) -> tuple[Dealer | Supplier, Direction] | None:
    """Same dealer-then-supplier check as find_party, but by exact id — for
    resolving a `party` query param a link was generated with back to the
    real row + its direction, company-scoped so one company can never fetch
    another's party by guessing an id.
    """
    dealer = await db.get(Dealer, party_id)
    if dealer is not None and dealer.company_id == company_id:
        return dealer, "receivable"
    supplier = await db.get(Supplier, party_id)
    if supplier is not None and supplier.company_id == company_id:
        return supplier, "payable"
    return None
