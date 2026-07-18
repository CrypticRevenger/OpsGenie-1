"""Evening Business Summary — a new scheduled WhatsApp send, distinct from
the existing 8am morning briefing (app/services/briefing.py).

Deterministic text only, no LLM — same reasoning as the numbered query menu
and follow-up conversation: every figure here is a real, already-computed
number (app/services/daily_snapshot.py), not something worth risking an LLM
rephrasing incorrectly. Separate, clearly-labeled metrics throughout (Sales,
Margin, Collections, Payments, Net Cash Movement, Outstanding) — never a
blended "profit/loss" figure, see app/services/daily_snapshot.py's own
docstring for why.

Same layering as app/services/notifications.py: performs its own WhatsApp
send, writes NotificationLog + BusinessEvent, never commits internally (the
caller — the scheduler, or the manual admin trigger — commits once).
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import Locale, resolve_locale, t
from app.models.business_event import BusinessEvent, BusinessEventType
from app.models.company import Company
from app.models.daily_business_snapshot import DailyBusinessSnapshot
from app.models.notification_log import NotificationLog
from app.services.daily_snapshot import finalize_daily_snapshot
from app.services.money_format import format_inr, format_signed_inr
from app.services.priority_actions import get_priority_actions
from app.services.recommendations import ActionItem
from app.services.snapshot import business_now
from app.services.whatsapp_client import (
    WhatsAppNotConfiguredError,
    WhatsAppSendError,
    WhatsAppSendResult,
    send_text_message,
)

logger = logging.getLogger(__name__)

_NOTIFICATION_TYPE = "evening_brief"


async def _already_finalized_today(db: AsyncSession, company: Company, business_date) -> bool:
    row = await db.scalar(
        select(DailyBusinessSnapshot.id).where(
            DailyBusinessSnapshot.company_id == company.id,
            DailyBusinessSnapshot.business_date == business_date,
        )
    )
    return row is not None


def _compose_text(
    snapshot: DailyBusinessSnapshot, priority_actions: list[ActionItem], loc: Locale
) -> str:
    lines = [
        t("evening.header", loc),
        t(
            "evening.counts",
            loc,
            invoices=snapshot.invoices_created,
            orders=snapshot.orders_created,
            payments=snapshot.payments_recorded,
        ),
        "",
        t("evening.sales", loc, amount=format_inr(snapshot.sales_amount)),
    ]

    margin_line = t("evening.margin", loc, amount=format_inr(snapshot.sales_margin))
    if snapshot.items_missing_cost_data > 0:
        margin_line += t(
            "evening.margin_excluded",
            loc,
            items=snapshot.items_missing_cost_data,
            amount=format_inr(snapshot.revenue_excluded_no_cost_data),
        )
    lines.append(margin_line)

    lines.extend(
        [
            t("evening.collections", loc, amount=format_inr(snapshot.collections_amount)),
            t(
                "evening.supplier_payments",
                loc,
                amount=format_inr(snapshot.supplier_payments_amount),
            ),
            t("evening.net_cash", loc, amount=format_signed_inr(snapshot.net_cash_movement)),
            t("evening.outstanding", loc, amount=format_inr(snapshot.outstanding_receivables)),
        ]
    )

    if priority_actions:
        lines.append("")
        lines.append(t("evening.priority_header", loc))
        for action in priority_actions:
            amount_part = f" ({format_inr(action.amount)})" if action.amount is not None else ""
            lines.append(f"- {action.reason}{amount_part}")

    return "\n".join(lines)


async def send_evening_brief(db: AsyncSession, company: Company) -> bool:
    """Finalizes today's snapshot and sends the summary. Returns False
    (no-op) when today was already finalized — the same dedup shape as
    app/core/scheduler.py::_latest_briefing_today, so a retried scheduler
    tick or a repeated manual trigger never sends a duplicate real message.
    """
    today = business_now(company.timezone).date()
    if await _already_finalized_today(db, company, today):
        logger.info(
            "Evening brief for company %s: %s already finalized, skipping.", company.id, today
        )
        return False

    snapshot = await finalize_daily_snapshot(db, company, today)
    priority_actions = await get_priority_actions(db, company.id)
    text = _compose_text(snapshot, priority_actions, resolve_locale(company))

    send_result: WhatsAppSendResult | None
    try:
        send_result = await send_text_message(company.whatsapp_number, text)
    except (WhatsAppNotConfiguredError, WhatsAppSendError) as exc:
        logger.warning("Evening brief to %s not sent: %s", company.whatsapp_number, exc)
        send_result = None

    db.add(
        NotificationLog(
            company_id=company.id,
            notification_type=_NOTIFICATION_TYPE,
            recipient_whatsapp=company.whatsapp_number,
            message_text=text,
            whatsapp_message_id=send_result.message_id if send_result else None,
            delivery_status="sent" if send_result else "failed_to_send",
        )
    )
    db.add(
        BusinessEvent(
            company_id=company.id,
            event_type=BusinessEventType.evening_brief_sent,
            entity_type="company",
            entity_id=company.id,
            payload={
                "business_date": today.isoformat(),
                "whatsapp_message_id": send_result.message_id if send_result else None,
            },
            created_by="evening_brief",
        )
    )
    return send_result is not None
