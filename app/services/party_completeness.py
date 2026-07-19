"""Which dealers/suppliers are missing the contact fields onboarding asks for.

A distributor who imports existing data (see app/api/onboarding.py's POST
/onboard/{id}/import) gets Dealer/Supplier rows created with only a `name` —
find_or_create_party (app/services/importer/parties.py) never sets phone or
payment_terms_days, since an invoice file names a party but never gives their
contact/credit details. This module answers "which of a company's parties are
still missing one of those" for two different callers: the WhatsApp onboarding
flow (app/services/onboarding_flow.py, needs the actual rows to ask about and
update) and the recommendation engine (app/services/snapshot.py, needs only
the count, for a "N dealers still need a phone number" briefing reminder when
a distributor picks "later" during onboarding).

Deliberately its own module rather than living in party_outstanding.py (money
math only, per that module's own docstring) or importer/parties.py (import-time
party *resolution*, not a general-purpose completeness query — and snapshot.py
has no business depending on the CSV-import subsystem for an unrelated read).
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dealer import Dealer
from app.models.supplier import Supplier

PartyModel = type[Dealer] | type[Supplier]


def _missing_fields_predicate(model: PartyModel):
    return or_(model.phone.is_(None), model.payment_terms_days.is_(None))


async def parties_missing_fields(
    db: AsyncSession, model: PartyModel, company_id: uuid.UUID
) -> list[Dealer] | list[Supplier]:
    """Every party of `model` missing phone and/or credit days, name-ordered
    (stable, human-friendly listing order — not insertion order, which would
    be the arbitrary order invoice rows happened to create parties in).
    """
    stmt = (
        select(model)
        .where(model.company_id == company_id, _missing_fields_predicate(model))
        .order_by(model.name)
    )
    return list((await db.execute(stmt)).scalars().all())


async def count_parties_missing_fields(
    db: AsyncSession, model: PartyModel, company_id: uuid.UUID
) -> int:
    """Count-only counterpart of parties_missing_fields, for a caller (the
    recommendation engine) that only needs the number, not the rows."""
    stmt = (
        select(func.count())
        .select_from(model)
        .where(model.company_id == company_id, _missing_fields_predicate(model))
    )
    return await db.scalar(stmt) or 0
