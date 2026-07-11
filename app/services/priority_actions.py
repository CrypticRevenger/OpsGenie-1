"""Single shared entrypoint for "what should the distributor prioritize
right now" — the two-step build_snapshot -> build_recommendations sequence
that app/services/briefing.py and app/api/admin/cashflow.py each used to
duplicate independently.

Deliberately its own tiny module rather than living inside
app/services/recommendations.py: that module's own docstring states it is
"deliberately a pure function of a Snapshot — no DB access here," which this
wrapper's build_snapshot call would violate if added there directly.

Every consumer — Morning Brief, Evening Business Summary, the dashboard
cashflow card, and the AI Assistant's read tools — calls this one function
instead of re-deriving the same two-step sequence.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.recommendations import ActionItem, build_recommendations
from app.services.snapshot import Snapshot, build_snapshot


async def get_priority_actions(
    db: AsyncSession, company_id: uuid.UUID, *, snapshot: Snapshot | None = None
) -> list[ActionItem]:
    """`snapshot` lets a caller that already built one for its own purposes
    (briefing.py, cashflow.py — both need the raw Snapshot for other fields,
    not just recommendations) pass it through instead of paying for a second
    build_snapshot query. Callers with no snapshot in hand (evening_brief.py,
    the AI Assistant's read tool) build one internally.
    """
    snapshot = snapshot or await build_snapshot(db, company_id)
    return build_recommendations(snapshot)
