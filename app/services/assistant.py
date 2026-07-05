"""Free-form natural-language assistant (SPEC V0.2 "Free-form AI Q&A").

Once a company has finished onboarding, a WhatsApp message that isn't a numbered
menu command ("1"-"4") or a follow-up reply is answered here instead of a dumb
"didn't understand" fallback. The user can ask things like "how much does Ram
owe me?" or "what's my cash position?".

Money-safety is the whole point: this follows the same rule as the briefing —
**the LLM never invents or calculates a figure**. Every number the model is
allowed to use is computed deterministically here (the snapshot + each party's
outstanding) and handed to it as a grounded context; the model only picks the
right one, matches the party name, and phrases the answer. `find_unverified_amounts`
then checks the reply — if the model emitted a ₹ figure that isn't in the
context, we discard its answer and send a safe menu hint rather than a possibly
hallucinated number.
"""

from __future__ import annotations

import json
import logging
import re
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.dealer import Dealer
from app.models.supplier import Supplier
from app.services.llm import generate_with_fallback
from app.services.party_outstanding import calculate_outstanding_for_company
from app.services.snapshot import build_snapshot

logger = logging.getLogger(__name__)

ASSISTANT_NOTIFICATION_TYPE = "assistant"

# Cap how many parties go into the prompt so a company with thousands of dealers
# can't blow up the context; the largest balances are the ones worth answering.
_MAX_PARTIES = 50

_SYSTEM_PROMPT = (
    "You are a WhatsApp assistant for a B2B distributor. Answer the user's question "
    "using ONLY the numbers in the DATA below. Never invent, estimate, or calculate a "
    "figure that is not present in the DATA. Always write money amounts with a ₹ prefix. "
    "Party names may be abbreviated by the user (e.g. 'Ram' means 'Ram Traders') — match "
    "loosely. If the question is about creating invoices, inventory/stock, or anything not "
    "present in the DATA, say that feature isn't available yet. If you cannot answer from "
    "the DATA, say so briefly and suggest replying 1, 2, 3 or 4. Keep the reply short and "
    "friendly for WhatsApp, in {language}."
)

# Sent instead of the model's answer when the LLM is unavailable or the reply
# failed the money-traceability check.
_SAFE_FALLBACK = (
    "Sorry, I couldn't answer that right now. Reply 1 Cash · 2 Collections · "
    "3 Suppliers · 4 Dealer Risk, or try rephrasing."
)

# Money-safety gate. The briefing's ₹-only check isn't enough here: the system
# prompt asking for a ₹ prefix is a prompt-only guarantee, and a prompt-injected
# reply ("...say Rs 5,00,000") could drop the ₹ and slip a fabricated figure
# through. So we detect money framed as ₹/Rs/INR/rupees (before OR after the
# number), any comma-grouped number, and any bare 5+-digit number — independent
# of the prompt — and require each to already exist in the grounded context. A
# 5-digit floor keeps 4-digit years (e.g. "2026") from false-positiving; the
# residual gap (a bare <10000 amount with no currency marker or grouping) is
# both narrow and low-stakes. NOTE (known pilot limitation): this verifies a
# figure *exists* in the data, not that it's attributed to the *right* party —
# "Ram owes ₹10,000" when ₹10,000 is actually Shyam's balance would still pass.
_MONEY_RE = re.compile(
    r"(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d+)?)"  # currency marker before
    r"|([\d,]+(?:\.\d+)?)\s*(?:rupees?|rs\.?|inr)"  # currency marker after
    r"|(\d{1,3}(?:,\d{2,3})+(?:\.\d+)?)"  # comma-grouped (e.g. 5,00,000)
    # bare 5+ digit — the trailing guard excludes only digits/commas (not '.'),
    # so a sentence-ending period after the number ("...987654.") still matches.
    r"|(?<![\d.,])(\d{5,}(?:\.\d+)?)(?![\d,])",
    re.IGNORECASE,
)


def _known_amounts(context: dict) -> set[Decimal]:
    """Every numeric leaf in the grounded context, as Decimals."""
    known: set[Decimal] = set()

    def _walk(value: object) -> None:
        if isinstance(value, dict):
            for v in value.values():
                _walk(v)
        elif isinstance(value, list):
            for v in value:
                _walk(v)
        else:
            try:
                known.add(Decimal(str(value).replace(",", "")))
            except (InvalidOperation, ValueError):
                pass

    _walk(context)
    return known


def _reply_has_unverified_money(text: str, context: dict) -> bool:
    """True if the reply states a money figure not present in the context."""
    known = _known_amounts(context)
    for match in _MONEY_RE.finditer(text):
        raw = next((g for g in match.groups() if g is not None), None)
        if raw is None:
            continue
        try:
            value = Decimal(raw.replace(",", ""))
        except InvalidOperation:
            return True
        if value not in known:
            return True
    return False


async def _build_context(db: AsyncSession, company: Company) -> dict:
    """The grounded facts the model is allowed to use — every amount computed
    deterministically, stringified like the briefing payload.
    """
    snapshot = await build_snapshot(db, company.id)

    dealer_names = {
        d.id: d.name
        for d in (await db.scalars(select(Dealer).where(Dealer.company_id == company.id))).all()
    }
    supplier_names = {
        s.id: s.name
        for s in (await db.scalars(select(Supplier).where(Supplier.company_id == company.id))).all()
    }
    dealer_out = await calculate_outstanding_for_company(
        db, company_id=company.id, direction="receivable"
    )
    supplier_out = await calculate_outstanding_for_company(
        db, company_id=company.id, direction="payable"
    )

    def _party_list(outstanding: dict, names: dict) -> list[dict]:
        rows = [
            {"name": names.get(pid, "Unknown"), "outstanding": str(amt)}
            for pid, amt in outstanding.items()
            if amt != Decimal("0.00")
        ]
        rows.sort(key=lambda r: Decimal(r["outstanding"]), reverse=True)
        return rows[:_MAX_PARTIES]

    return {
        "cash_available_now": str(snapshot.cash_available_today),
        "expected_collections_next_7_days": str(snapshot.expected_collections_7d_total),
        "expected_payments_next_7_days": str(snapshot.expected_payments_7d_total),
        "net_cash_position": str(snapshot.net_cash_position),
        "dealers_who_owe_you": _party_list(dealer_out, dealer_names),
        "suppliers_you_owe": _party_list(supplier_out, supplier_names),
        "overdue_dealers": [
            {
                "name": od.dealer_name,
                "outstanding": str(od.outstanding),
                "days_overdue": od.days_overdue,
                "risk": od.risk_level,
            }
            for od in snapshot.overdue_dealers
        ],
    }


async def answer_question(db: AsyncSession, company: Company, text: str) -> str:
    """Answer a free-form question, grounded in the company's real figures.

    Never raises — this runs on the public Meta-facing webhook, where any
    exception would 500 and trigger Meta's aggressive retry storm. Snapshot/DB
    errors, LLM-provider errors (incl. a non-fallback 4xx like a revoked key),
    and config errors all fall through to the safe menu hint. A reply that
    states an untraceable money figure is likewise discarded for the fallback.
    """
    try:
        context = await _build_context(db, company)
        result = await generate_with_fallback(
            system_prompt=_SYSTEM_PROMPT.format(language=company.preferred_language),
            user_content=json.dumps({"question": text, "DATA": context}),
        )
    except Exception as exc:  # noqa: BLE001 - deliberately never raise into the webhook
        logger.warning("Assistant failed for company %s: %s", company.id, exc)
        return _SAFE_FALLBACK

    if _reply_has_unverified_money(result.text, context):
        # The model wrote a money figure not in the grounded context — never
        # forward a possibly-hallucinated number to the user.
        logger.warning(
            "Assistant reply for company %s contained an unverified amount — using fallback.",
            company.id,
        )
        return _SAFE_FALLBACK

    return result.text
