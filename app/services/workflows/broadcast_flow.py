"""Guided marketing broadcast workflow — founder-only, segment -> compose ->
PendingOperation confirm. Same state-machine shape as
app/services/workflows/stock_take_flow.py: state lives in
Company.active_workflow + Company.workflow_scratch, mutated in place, never
committed here (the webhook commits once).

The terminal step hands off to create_pending_operation (same pattern
order_flow.py's create_order uses) rather than writing directly — the
payload stores raw filter criteria (segment + dealer_ids), never a resolved
recipient list, so app/services/writes/broadcast.py::send_broadcast
re-derives who's actually opted-in fresh at confirm time.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.i18n import resolve_locale, t
from app.models.company import Company
from app.models.dealer import Dealer
from app.models.pending_operation import PendingOperationType
from app.services.onboarding_flow import _is
from app.services.writes.broadcast import resolve_broadcast_recipients
from app.services.writes.pending_operation import create_pending_operation

_MAX_PREVIEW_CANDIDATES_FOR_SPECIFIC = 200  # sane upper bound for a pasted list


def start_broadcast_workflow(company: Company) -> str:
    company.active_workflow = "broadcast_dealers"
    company.workflow_scratch = {"step": "awaiting_segment"}
    return t("broadcast.segment_ask", resolve_locale(company))


def _classify_segment(text: str) -> str | None:
    normalized = text.strip().lower()
    if normalized in ("all", "all dealers", "1"):
        return "all"
    if normalized in ("overdue", "overdue dealers", "2"):
        return "overdue"
    if normalized in ("specific", "pick", "pick dealers", "choose", "choose dealers", "3"):
        return "specific"
    return None


async def _match_dealer_by_name(
    db: AsyncSession, company_id: uuid.UUID, name: str
) -> Dealer | None:
    matches = (
        await db.scalars(
            select(Dealer).where(
                Dealer.company_id == company_id, func.lower(Dealer.name) == name.lower()
            )
        )
    ).all()
    # 0 or >1 matches both count as "couldn't resolve this name" — building
    # per-name disambiguation for a pasted multi-name list is a bigger state
    # machine than this v1 needs; an ambiguous name is simply reported back
    # as unmatched, same as a typo would be.
    return matches[0] if len(matches) == 1 else None


async def handle_broadcast_workflow_message(db: AsyncSession, company: Company, text: str) -> str:
    stripped = text.strip()
    loc = resolve_locale(company)

    if _is(stripped, "cancel", "stop"):
        company.active_workflow = None
        company.workflow_scratch = None
        return t("workflow.cancelled", loc)

    scratch = dict(company.workflow_scratch or {})
    step = scratch.get("step")

    if step == "awaiting_segment":
        segment = _classify_segment(stripped)
        if segment is None:
            return t("broadcast.segment_invalid", loc)
        if segment == "specific":
            scratch = {"step": "awaiting_dealer_names", "segment": "specific"}
            company.workflow_scratch = scratch
            return t("broadcast.dealer_names_ask", loc)
        # "all"/"overdue" — preview the opted-in count before asking for the
        # message body, so the founder isn't asked to compose a message for
        # zero recipients.
        candidates = await resolve_broadcast_recipients(db, company.id, segment=segment)
        if not candidates:
            company.active_workflow = None
            company.workflow_scratch = None
            return t(
                "broadcast.no_opted_in", loc, segment=t(f"broadcast.segment.{segment}", loc)
            )
        scratch = {"step": "awaiting_message", "segment": segment, "dealer_ids": []}
        company.workflow_scratch = scratch
        return t("broadcast.message_ask", loc, count=len(candidates))

    if step == "awaiting_dealer_names":
        lines = [ln.strip() for ln in stripped.replace(",", "\n").splitlines() if ln.strip()]
        if not lines:
            return t("broadcast.dealer_names_ask", loc)
        matched_ids: list[str] = []
        unmatched: list[str] = []
        for name in lines[:_MAX_PREVIEW_CANDIDATES_FOR_SPECIFIC]:
            dealer = await _match_dealer_by_name(db, company.id, name)
            if dealer is not None:
                matched_ids.append(str(dealer.id))
            else:
                unmatched.append(name)
        if not matched_ids:
            company.active_workflow = None
            company.workflow_scratch = None
            return t("broadcast.dealer_names_none_matched", loc, names=", ".join(unmatched))

        candidates = await resolve_broadcast_recipients(
            db, company.id, segment="specific", dealer_ids=[uuid.UUID(d) for d in matched_ids]
        )
        if not candidates:
            company.active_workflow = None
            company.workflow_scratch = None
            return t(
                "broadcast.no_opted_in", loc, segment=t("broadcast.segment.specific", loc)
            )
        scratch = {"step": "awaiting_message", "segment": "specific", "dealer_ids": matched_ids}
        company.workflow_scratch = scratch
        unmatched_note = (
            t("broadcast.dealer_names_unmatched", loc, names=", ".join(unmatched))
            if unmatched
            else ""
        )
        return t("broadcast.message_ask", loc, count=len(candidates)) + unmatched_note

    if step == "awaiting_message":
        if not stripped:
            return t("broadcast.message_empty", loc)
        segment = scratch["segment"]
        dealer_ids = scratch.get("dealer_ids", [])
        # Preview count only — re-derived for real at execute time by
        # send_broadcast/resolve_broadcast_recipients from the payload's raw
        # criteria, never from this cached number.
        preview_candidates = await resolve_broadcast_recipients(
            db, company.id, segment=segment, dealer_ids=[uuid.UUID(d) for d in dealer_ids]
        )
        payload = {"segment": segment, "dealer_ids": dealer_ids, "message": stripped}
        await create_pending_operation(db, company, PendingOperationType.broadcast_dealers, payload)
        company.active_workflow = None
        company.workflow_scratch = None

        cap = get_settings().max_broadcast_recipients
        capped_note = (
            t("broadcast.confirm_capped", loc, cap=cap) if len(preview_candidates) > cap else ""
        )
        return t(
            "broadcast.confirm_prompt",
            loc,
            count=min(len(preview_candidates), cap),
            message=stripped,
            capped_note=capped_note,
        )

    # Unreachable in practice (every step above is exhaustive for this
    # flow), but never leave a company stuck on a workflow step this code
    # can't run.
    company.active_workflow = None
    company.workflow_scratch = None
    return t("workflow.error_restart", loc, trigger="broadcast")
