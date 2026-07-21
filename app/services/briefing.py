"""BriefingService — per SPEC.md TDD. The only AI component in this project.

"LLMs only understand language and generate natural responses. Everything
else belongs to deterministic code... If you replace the LLM provider with
any other model tomorrow, every number and every recommendation must remain
identical. Only phrasing may change."

Everything here except the call into app.services.llm's fallback chain is a
pure function — the payload the model receives, the confidence indicator
appended after narration, and the traceability check are all deterministic
and unit-testable without touching the network. Narration goes through
generate_with_fallback(), which tries a configurable, ordered chain of LLM
providers (LLM_PROVIDER + LLM_FALLBACKS) and returns whichever one actually
served the request — this module never imports a specific provider SDK.

Not in scope here (later phases): APScheduler daily dispatch and WhatsApp
delivery — both require infrastructure that doesn't exist yet. This service
generates a briefing on demand and stores it; delivery is a separate phase.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import date
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import Locale, resolve_locale, t
from app.models.company import Company
from app.models.morning_briefing import MorningBriefing
from app.services.llm import (
    AllProvidersExhaustedError,
    NoApiKeyConfiguredError,
    generate_with_fallback,
)
from app.services.money_format import format_inr
from app.services.notifications import (
    _PREDUE_NUDGE_DAYS_BEFORE,
    _STOCK_OUT_DAYS_OF_COVER_THRESHOLD,
)
from app.services.priority_actions import get_priority_actions
from app.services.recommendations import _STALE_DATA_THRESHOLD_HOURS, ActionItem
from app.services.snapshot import Snapshot, build_snapshot, business_now
from app.services.stock_forecast import StockOutForecast, build_stock_out_forecasts

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = (
    "You are a WhatsApp financial assistant for a B2B distributor. Convert the "
    "following structured business data into a brief, friendly, sectioned WhatsApp "
    "morning briefing in {language}. Sections: Cash Position, Attention Required, "
    "Today's Actions. Every number comes from the data provided — do not add, "
    "estimate, or modify any figure. Always write every money amount with a ₹ "
    "prefix (e.g. ₹90,000.00) — never a bare number and never $. Keep each section "
    "to 3 to 5 lines. Use simple language readable in 30 seconds on a phone screen."
)

_AMOUNT_RE = re.compile(r"₹\s?([\d,]+(?:\.\d+)?)")


def assemble_briefing_payload(snapshot: Snapshot, recommendations: list[ActionItem]) -> dict:
    """The exact structured JSON the model receives. Every field traces directly
    to the Snapshot/ActionItem objects already built and tested in Phase 5A —
    no reshaping beyond what's needed to serialize Decimal/UUID/date as JSON.
    """
    return {
        "cash_position": {
            "available_today": str(snapshot.cash_available_today),
            "expected_in_7_days": str(snapshot.expected_collections_7d_total),
            "expected_out_7_days": str(snapshot.expected_payments_7d_total),
            "net_position": str(snapshot.net_cash_position),
            "shortage_expected": snapshot.cash_deficit,
        },
        "recommendations": [
            {
                "priority": item.priority,
                "action_type": item.action_type,
                "entity_name": item.entity_name,
                "amount": str(item.amount) if item.amount is not None else None,
                "reason": item.reason,
                "days_overdue": item.days_overdue,
            }
            for item in recommendations
        ],
    }


def confidence_indicator(confidence_score: float, data_freshness_hours: float | None) -> str:
    """Deterministic, Python-generated — never asked of the model. The
    confidence figure is arithmetic already done in snapshot.py, not something
    the model reports on itself. Mirrors the WhatsApp spec's
    "Data updated: yesterday 9:14pm — confidence 94%" style, simplified to
    hours-based phrasing since we don't track a human-readable "yesterday
    9:14pm" style timestamp.
    """
    if data_freshness_hours is None:
        freshness = "no data has ever been imported"
    elif data_freshness_hours < 1:
        freshness = "data updated less than an hour ago"
    else:
        freshness = f"data updated {data_freshness_hours:.0f} hour(s) ago"
    return f"({freshness} — confidence {confidence_score:.0f}%)"


def stale_data_banner(data_freshness_hours: float | None) -> str | None:
    """Deterministic, Python-generated warning prepended above the whole
    briefing when data is stale (SPEC's "Stale Data Briefing" example) —
    distinct from the confidence indicator footer, which appears on every
    briefing regardless of freshness. Returns None when data is fresh so the
    caller can prepend nothing. Reuses RecommendationEngine's own staleness
    threshold so the banner and the stale_data_warning recommendation can
    never disagree about what "stale" means.
    """
    if data_freshness_hours is None:
        return (
            "⚠ No data has been received yet. This briefing cannot reflect your "
            "actual position. Please ask your operator to send today's Tally export."
        )
    if data_freshness_hours <= _STALE_DATA_THRESHOLD_HOURS:
        return None
    days = int(data_freshness_hours // 24)
    if days >= 1:
        age = f"{days} day(s) ago"
    else:
        age = f"{int(round(data_freshness_hours))} hour(s) ago"
    return (
        f"⚠ Data last received {age}. This briefing may not reflect today's actual "
        "position. Please ask your operator to send today's Tally export."
    )


def find_unverified_amounts(generated_text: str, payload: dict) -> list[str]:
    """Regex-extracts every ₹-prefixed amount in the model's narration and
    checks each one appears somewhere in the payload sent. A non-empty return
    means the model added, estimated, or altered a figure — a direct,
    automatable check of "every number must be traceable to a real invoice or
    payment record." Not a hard failure gate here (the manual real-data
    verification is the actual gate per SPEC Step 8) — callers decide what to
    do with it.
    """
    # Compare as Decimal values, not strings — "184000" and "184000.00" are
    # the same amount but different strings, so string comparison would
    # falsely flag every whole-rupee figure the model writes without paise.
    known_amounts: set[Decimal] = set()
    for value in _flatten(payload):
        if isinstance(value, str):
            cleaned = value.replace(",", "")
            try:
                known_amounts.add(Decimal(cleaned))
            except Exception:  # noqa: BLE001 - not every string is a number, that's fine
                continue

    mentioned = _AMOUNT_RE.findall(generated_text)
    unverified = []
    for raw in mentioned:
        cleaned = raw.replace(",", "")
        try:
            normalised = Decimal(cleaned)
        except Exception:  # noqa: BLE001
            unverified.append(raw)
            continue
        if normalised not in known_amounts:
            unverified.append(raw)
    return unverified


def _flatten(value: object) -> list[object]:
    """Yield every leaf value in a nested dict/list payload. Dict keys
    starting with "_" (e.g. the "_llm_metadata" block added when a briefing
    is stored) are skipped — they're bookkeeping, not traceable business
    figures, so they must never be counted as a "known amount."
    """
    if isinstance(value, dict):
        result = []
        for key, v in value.items():
            if isinstance(key, str) and key.startswith("_"):
                continue
            result.extend(_flatten(v))
        return result
    if isinstance(value, list):
        result = []
        for v in value:
            result.extend(_flatten(v))
        return result
    return [value]


def build_watch_this_week(
    snapshot: Snapshot,
    stock_out_forecasts: list[StockOutForecast],
    loc: Locale,
) -> str | None:
    """Deterministic "Watch this week" section — cash-shortage day count +
    trigger payment, stock-out risk, invoices due soon. Built the same way as
    evening_brief.py's _compose_text (plain t()-rendered lines joined in
    Python) and never fed to the LLM, so the highest-priority operational
    risks are never subject to narration drift. Returns None when there's
    nothing to show, so the caller can prepend nothing.

    Reuses notifications.py's own thresholds (_STOCK_OUT_DAYS_OF_COVER_THRESHOLD,
    _PREDUE_NUDGE_DAYS_BEFORE) so this section and the standalone alerts can
    never disagree about what counts as "worth watching" — same reason this
    module already imports recommendations._STALE_DATA_THRESHOLD_HOURS.
    """
    lines = []
    forecast = snapshot.cash_deficit_forecast
    if forecast is not None and forecast.trigger_payment is not None:
        lines.append(
            t(
                "briefing.watch.cash_shortage",
                loc,
                days=forecast.days_until,
                supplier=forecast.trigger_payment.supplier_name,
                amount=format_inr(forecast.trigger_payment.amount),
            )
        )

    for stock_forecast in stock_out_forecasts:
        if stock_forecast.days_of_cover <= _STOCK_OUT_DAYS_OF_COVER_THRESHOLD:
            lines.append(
                t(
                    "briefing.watch.stock_out",
                    loc,
                    product=stock_forecast.product_name,
                    days=stock_forecast.days_of_cover,
                )
            )

    today = snapshot.generated_at.date()
    for collection in snapshot.expected_collections_7d:
        days_out = (collection.due_date - today).days
        if 1 <= days_out <= _PREDUE_NUDGE_DAYS_BEFORE:
            lines.append(
                t("briefing.watch.predue", loc, dealer=collection.dealer_name, days=days_out)
            )

    if not lines:
        return None
    return t("briefing.watch.header", loc) + "\n" + "\n".join(lines)


async def latest_briefing_today(
    db: AsyncSession, company: Company, business_date: date | None = None
) -> MorningBriefing | None:
    """Most recent briefing whose creation falls on the given business-local
    date (defaults to the company's current business-local date). created_at
    is stored in UTC, so it must be converted into the company's own timezone
    before taking .date() — comparing a raw UTC date to a business-local date
    would misfire for far-eastern zones (e.g. an 8am briefing in a UTC+13 zone
    has a UTC date of "yesterday"), causing a duplicate briefing. Filtered in
    Python after ordering — cheap at pilot scale (a company has at most a
    handful of briefings per day).

    Shared by the scheduler (dedup check before generating) and the on-demand
    "give me my briefing" instant command (reuse today's already-generated
    briefing instead of paying for a second LLM call) — one lookup, one
    definition of "today's briefing" for both callers.
    """
    if business_date is None:
        business_date = business_now(company.timezone).date()
    briefing = await db.scalar(
        select(MorningBriefing)
        .where(MorningBriefing.company_id == company.id)
        .order_by(MorningBriefing.created_at.desc())
        .limit(1)
    )
    if briefing is None or briefing.created_at is None:
        return None
    local_created = briefing.created_at.astimezone(ZoneInfo(company.timezone))
    return briefing if local_created.date() == business_date else None


async def generate_briefing(db: AsyncSession, company_id: uuid.UUID) -> MorningBriefing:
    """build_snapshot -> get_priority_actions -> assemble payload ->
    generate_with_fallback -> append confidence indicator -> check
    traceability -> persist (with provider/model metadata) -> return.
    """
    company = await db.get(Company, company_id)
    if company is None:
        raise ValueError(f"Company {company_id} not found")

    snapshot = await build_snapshot(db, company_id)
    recommendations = await get_priority_actions(db, company_id, snapshot=snapshot)
    stock_out_forecasts = await build_stock_out_forecasts(
        db, company_id, snapshot.generated_at.date()
    )
    payload = assemble_briefing_payload(snapshot, recommendations)

    result = await generate_with_fallback(
        system_prompt=SYSTEM_PROMPT_TEMPLATE.format(
            language=resolve_locale(company).narration_instruction
        ),
        user_content=json.dumps(payload),
    )
    indicator = confidence_indicator(snapshot.confidence_score, snapshot.data_freshness_hours)
    banner = stale_data_banner(snapshot.data_freshness_hours)
    watch = build_watch_this_week(snapshot, stock_out_forecasts, resolve_locale(company))
    # Order: stale-data caveat (qualifies trust in everything below) -> Watch
    # this week (highest-priority operational risks, read first) -> LLM
    # narrative -> confidence footer -> menu prompt.
    body = "\n\n".join(part for part in (banner, watch, result.text) if part)
    generated_text = f"{body}\n\n{indicator}\n\n{t('menu.prompt', resolve_locale(company))}"

    unverified = find_unverified_amounts(result.text, payload)
    if unverified:
        logger.warning(
            "Briefing for company %s mentions amounts not found in the source payload: %s",
            company_id,
            unverified,
        )

    # Provider/model metadata is stored inside snapshot_json rather than as a
    # new column — avoids a schema migration for observability data that
    # isn't part of the traceable business payload (see _flatten's "_"-prefix
    # skip above, which keeps it out of the traceability check).
    stored_snapshot = {
        **payload,
        "_llm_metadata": {
            "provider": result.provider,
            "model": result.model,
            "latency_seconds": result.latency_seconds,
        },
    }

    briefing = MorningBriefing(
        company_id=company_id,
        generated_text=generated_text,
        snapshot_json=_json_safe(stored_snapshot),
        confidence_score=Decimal(str(round(snapshot.confidence_score, 2))),
        data_freshness_hours=(
            round(snapshot.data_freshness_hours)
            if snapshot.data_freshness_hours is not None
            else None
        ),
    )
    db.add(briefing)
    await db.commit()
    await db.refresh(briefing)
    return briefing


def _json_safe(payload: dict) -> dict:
    """assemble_briefing_payload already stringifies Decimals, so this is a
    no-op passthrough today — kept as an explicit step so snapshot_json is
    never silently handed non-JSON-safe types if the payload shape changes.
    """
    return json.loads(json.dumps(payload))


__all__ = [
    "SYSTEM_PROMPT_TEMPLATE",
    "AllProvidersExhaustedError",
    "NoApiKeyConfiguredError",
    "assemble_briefing_payload",
    "build_watch_this_week",
    "confidence_indicator",
    "find_unverified_amounts",
    "generate_briefing",
    "latest_briefing_today",
    "stale_data_banner",
]
