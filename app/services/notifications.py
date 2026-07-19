"""NotificationEngine — SPEC.md V0.1 Step 14.

"Pure Python rules. No LLM. Runs on schedule and on event triggers." Four
proactive alert rules, each independently checkable and safe to re-run every
scheduler tick because each dedups against its own recent-activity window:

1. Supplier payment due within 24h  → reminder to the distributor.
2. Dealer flagged High Risk with no follow-up in 3 days → prompt to the
   distributor.
3. No data received in 24h → internal ops alert to the *founder's* number.
   Aggregated: every stale company is collapsed into ONE founder digest per
   scheduler tick (send_stale_data_digest) rather than one WhatsApp per
   company — a founder with many clients must never get 30 separate nudges in
   one pass. Still deduped once per company per business day.
4. Morning briefing delivery failed after retry → founder alert (this one is
   driven by the scheduler's retry path, which calls send_founder_alert
   directly rather than going through run_notification_checks).

Same layering as app/services/followup.py: reuses send_text_message, writes
NotificationLog + BusinessEvent + ActivityTimeline, and never commits
internally — the caller (the scheduler, one commit per company) owns the
transaction, so a mid-sequence failure never leaves partial state.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.i18n import resolve_locale, t
from app.models.activity_timeline import ActivityEntityType, ActivityEventType, ActivityTimeline
from app.models.business_event import BusinessEvent, BusinessEventType
from app.models.company import Company
from app.models.notification_log import NotificationLog
from app.services.money_format import format_inr
from app.services.snapshot import (
    Snapshot,
    build_snapshot,
    business_now,
    data_freshness_hours,
    is_cash_sufficient,
)
from app.services.whatsapp_client import (
    WhatsAppNotConfiguredError,
    WhatsAppSendError,
    send_text_message,
)

logger = logging.getLogger(__name__)

# "within 24h" — since invoices carry dates, not times, this means due today
# or tomorrow (0 or 1 whole days out).
_SUPPLIER_REMINDER_DAYS = 1
_DEALER_ALERT_QUIET_DAYS = 3  # "no follow-up recorded in 3 days"
_SUPPLIER_REMINDER_QUIET_HOURS = 24
_STALE_DATA_HOURS = 24

_STALE_DATA_REASON = "stale_data"
_BRIEFING_FAILED_REASON = "briefing_failed"

# Cap how many company names are itemised in a single founder digest so the
# WhatsApp message stays readable; any beyond this are summarised as a count.
_DIGEST_MAX_LISTED = 25


@dataclass(frozen=True)
class NotificationRunResult:
    supplier_reminders: int
    dealer_alerts: int


@dataclass(frozen=True)
class StaleCompany:
    company_id: uuid.UUID
    business_name: str
    freshness_hours: float | None  # None = never imported


@dataclass(frozen=True)
class StaleDataDigestResult:
    companies_flagged: int  # newly-stale companies this pass (before send)
    sent: bool  # whether the single founder digest message actually went out


async def _send_and_log(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    recipient: str,
    notification_type: str,
    message: str,
) -> bool:
    """Send `message`, record a NotificationLog row, return whether the send
    succeeded. Never raises on a send failure — logged and recorded as
    failed_to_send, same fail-open rule as everywhere else outbound.
    """
    send_result = None
    try:
        send_result = await send_text_message(recipient, message)
    except (WhatsAppNotConfiguredError, WhatsAppSendError) as exc:
        logger.warning("Notification (%s) to %s not sent: %s", notification_type, recipient, exc)

    db.add(
        NotificationLog(
            company_id=company_id,
            notification_type=notification_type,
            recipient_whatsapp=recipient,
            message_text=message,
            whatsapp_message_id=send_result.message_id if send_result else None,
            delivery_status="sent" if send_result else "failed_to_send",
        )
    )
    return send_result is not None


async def _recent_activity_exists(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    entity_type: ActivityEntityType,
    entity_id: uuid.UUID,
    event_types: tuple[ActivityEventType, ...],
    since: datetime,
) -> bool:
    found = await db.scalar(
        select(ActivityTimeline.id).where(
            ActivityTimeline.company_id == company_id,
            ActivityTimeline.entity_type == entity_type,
            ActivityTimeline.entity_id == entity_id,
            ActivityTimeline.event_type.in_(event_types),
            ActivityTimeline.event_timestamp >= since,
        )
    )
    return found is not None


# ── Rule 1: supplier payment due within 24h ─────────────────────────────────


async def check_supplier_payment_reminders(
    db: AsyncSession, company: Company, snapshot: Snapshot, now: datetime
) -> int:
    today = now.date()
    since = now - timedelta(hours=_SUPPLIER_REMINDER_QUIET_HOURS)
    sent = 0
    for payment in snapshot.expected_payments_7d:
        if (payment.due_date - today).days > _SUPPLIER_REMINDER_DAYS:
            continue
        if await _recent_activity_exists(
            db,
            company_id=company.id,
            entity_type=ActivityEntityType.supplier,
            entity_id=payment.supplier_id,
            event_types=(ActivityEventType.reminder_sent,),
            since=since,
        ):
            continue

        loc = resolve_locale(company)
        when = (
            t("notify.when_today", loc)
            if payment.due_date == today
            else t("notify.when_tomorrow", loc)
        )
        sufficient = is_cash_sufficient(snapshot.cash_available_today, payment.amount)
        sufficiency = (
            t("notify.cash_sufficient", loc) if sufficient else t("notify.cash_insufficient", loc)
        )
        cash_line = t(
            "notify.cash_line",
            loc,
            amount=format_inr(snapshot.cash_available_today),
            sufficiency=sufficiency,
        )
        message = t(
            "notify.supplier_reminder",
            loc,
            supplier=payment.supplier_name,
            amount=format_inr(payment.amount),
            when=when,
            cash_line=cash_line,
        )
        await _send_and_log(
            db,
            company_id=company.id,
            recipient=company.whatsapp_number,
            notification_type="supplier_payment_reminder",
            message=message,
        )
        db.add(
            ActivityTimeline(
                company_id=company.id,
                entity_type=ActivityEntityType.supplier,
                entity_id=payment.supplier_id,
                event_type=ActivityEventType.reminder_sent,
                amount=payment.amount,
                notes=f"Supplier payment reminder: {payment.supplier_name} due {when}",
            )
        )
        db.add(
            BusinessEvent(
                company_id=company.id,
                event_type=BusinessEventType.reminder_sent,
                entity_type="supplier",
                entity_id=payment.supplier_id,
                payload={
                    "kind": "supplier_payment_reminder",
                    "supplier_name": payment.supplier_name,
                    "amount": str(payment.amount),
                    "due_date": payment.due_date.isoformat(),
                },
                created_by="notification_engine",
            )
        )
        sent += 1
    return sent


# ── Rule 2: dealer High Risk, no follow-up in 3 days ────────────────────────


async def check_dealer_overdue_alerts(
    db: AsyncSession, company: Company, snapshot: Snapshot, now: datetime
) -> int:
    since = now - timedelta(days=_DEALER_ALERT_QUIET_DAYS)
    sent = 0
    for dealer in snapshot.overdue_dealers:
        if dealer.risk_level != "High":
            continue
        # "No follow-up recorded in 3 days" — a Phase 9 follow-up OR a prior
        # overdue alert both count as recent contact about this dealer.
        if await _recent_activity_exists(
            db,
            company_id=company.id,
            entity_type=ActivityEntityType.dealer,
            entity_id=dealer.dealer_id,
            event_types=(ActivityEventType.follow_up_sent, ActivityEventType.overdue_flagged),
            since=since,
        ):
            continue

        message = t(
            "notify.dealer_alert",
            resolve_locale(company),
            dealer=dealer.dealer_name,
            amount=format_inr(dealer.outstanding),
            days=dealer.days_overdue,
        )
        await _send_and_log(
            db,
            company_id=company.id,
            recipient=company.whatsapp_number,
            notification_type="dealer_overdue_alert",
            message=message,
        )
        db.add(
            ActivityTimeline(
                company_id=company.id,
                entity_type=ActivityEntityType.dealer,
                entity_id=dealer.dealer_id,
                event_type=ActivityEventType.overdue_flagged,
                amount=dealer.outstanding,
                notes=f"High-risk overdue alert: {dealer.dealer_name}, {dealer.days_overdue}d",
            )
        )
        db.add(
            BusinessEvent(
                company_id=company.id,
                event_type=BusinessEventType.reminder_sent,
                entity_type="dealer",
                entity_id=dealer.dealer_id,
                payload={
                    "kind": "dealer_overdue_alert",
                    "dealer_name": dealer.dealer_name,
                    "outstanding": str(dealer.outstanding),
                    "days_overdue": dealer.days_overdue,
                },
                created_by="notification_engine",
            )
        )
        sent += 1
    return sent


# ── Rules 3 & 4: founder alerts ─────────────────────────────────────────────


async def _founder_alert_sent_since(
    db: AsyncSession, company_id: uuid.UUID, reason: str, since: datetime
) -> bool:
    found = await db.scalar(
        select(BusinessEvent.id).where(
            BusinessEvent.company_id == company_id,
            BusinessEvent.event_type == BusinessEventType.founder_alert_sent,
            BusinessEvent.payload["reason"].astext == reason,
            BusinessEvent.created_at >= since,
        )
    )
    return found is not None


async def send_founder_alert(
    db: AsyncSession, *, company: Company, reason: str, message: str
) -> bool:
    """Shared primitive for both founder-facing conditions (stale data,
    briefing-delivery failure). Sends to FOUNDER_WHATSAPP_NUMBER; skips
    (returns False) when that's unset. Records a NotificationLog + a
    founder_alert_sent BusinessEvent carrying `reason` for dedup/traceability.
    """
    founder_number = get_settings().founder_whatsapp_number
    if not founder_number:
        logger.info(
            "Founder alert (%s) for company %s skipped — FOUNDER_WHATSAPP_NUMBER unset.",
            reason,
            company.id,
        )
        return False

    await _send_and_log(
        db,
        company_id=company.id,
        recipient=founder_number,
        notification_type=f"founder_alert:{reason}",
        message=message,
    )
    db.add(
        BusinessEvent(
            company_id=company.id,
            event_type=BusinessEventType.founder_alert_sent,
            entity_type="company",
            entity_id=company.id,
            payload={"reason": reason, "recipient": founder_number},
            created_by="notification_engine",
        )
    )
    return True


def _format_stale_age(freshness_hours: float | None) -> str:
    if freshness_hours is None:
        return "no export received yet"
    days = int(freshness_hours // 24)
    if days >= 1:
        return f"last export {days} day{'s' if days != 1 else ''} ago"
    return f"last export {int(round(freshness_hours))}h ago"


def _build_stale_digest_message(companies: list[StaleCompany]) -> str:
    count = len(companies)
    noun = "company" if count == 1 else "companies"
    listed = companies[:_DIGEST_MAX_LISTED]
    lines = [f"• {c.business_name} — {_format_stale_age(c.freshness_hours)}" for c in listed]
    remaining = count - len(listed)
    if remaining > 0:
        lines.append(f"…and {remaining} more")
    return (
        f"📂 Data Update Needed — {count} {noun}\n\n"
        f"No Tally export received today from {'this' if count == 1 else 'these'} {noun}, "
        "so tomorrow's briefing will be based on stale data:\n\n"
        + "\n".join(lines)
        + f"\n\nNudge {'the' if count == 1 else 'each'} operator to send today's export."
    )


async def _detect_stale_companies(
    db: AsyncSession, now: datetime | None
) -> list[StaleCompany]:
    """Every subscription-active company whose data is stale (no import within
    _STALE_DATA_HOURS, or none ever) and that hasn't already been reported to
    the founder today. Evaluated at each company's own business-local time and
    skipped while that local hour is before the company's briefing hour — the
    founder shouldn't be nudged about a company in the middle of its night
    (this preserves the pre-digest per-company gate: stale alerts only after
    the business day has started).
    """
    settings = get_settings()
    companies = (
        await db.scalars(select(Company).where(Company.subscription_active.is_(True)))
    ).all()

    stale: list[StaleCompany] = []
    for company in companies:
        local_now = now or business_now(company.timezone)
        briefing_hour = (
            company.briefing_hour if company.briefing_hour is not None else settings.briefing_hour
        )
        if local_now.hour < briefing_hour:
            continue
        hours = await data_freshness_hours(db, company.id, local_now)
        if hours is not None and hours <= _STALE_DATA_HOURS:
            continue  # fresh
        day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        if await _founder_alert_sent_since(db, company.id, _STALE_DATA_REASON, day_start):
            continue  # already in a digest today
        stale.append(StaleCompany(company.id, company.business_name, hours))
    return stale


async def send_stale_data_digest(
    db: AsyncSession, now: datetime | None = None
) -> StaleDataDigestResult:
    """Rule 3, aggregated. Collapses every newly-stale company into a SINGLE
    founder WhatsApp message per pass instead of one-per-company. Deduped once
    per company per business day (a company already in today's digest is never
    re-listed). Caller (the scheduler, once per tick) owns the commit.

    Delivery failure still records the per-company dedup markers — same
    fail-open rule as the other founder alerts, so a transient Meta error
    doesn't re-blast the founder on the next tick. An unset
    FOUNDER_WHATSAPP_NUMBER skips silently WITHOUT marking, so the digest can
    still go out if the number is configured later the same day.
    """
    stale = await _detect_stale_companies(db, now)
    if not stale:
        return StaleDataDigestResult(companies_flagged=0, sent=False)

    founder_number = get_settings().founder_whatsapp_number
    if not founder_number:
        logger.info(
            "Stale-data digest for %d company(ies) skipped — FOUNDER_WHATSAPP_NUMBER unset.",
            len(stale),
        )
        return StaleDataDigestResult(companies_flagged=len(stale), sent=False)

    message = _build_stale_digest_message(stale)
    send_result = None
    try:
        send_result = await send_text_message(founder_number, message)
    except (WhatsAppNotConfiguredError, WhatsAppSendError) as exc:
        logger.warning("Stale-data digest to %s not sent: %s", founder_number, exc)

    status = "sent" if send_result else "failed_to_send"
    for i, sc in enumerate(stale):
        db.add(
            NotificationLog(
                company_id=sc.company_id,
                notification_type=f"founder_alert:{_STALE_DATA_REASON}",
                recipient_whatsapp=founder_number,
                message_text=message,
                # One physical send → one wamid; NotificationLog.whatsapp_message_id
                # is UNIQUE, so only the first per-company row can carry it.
                whatsapp_message_id=send_result.message_id if (send_result and i == 0) else None,
                delivery_status=status,
            )
        )
        db.add(
            BusinessEvent(
                company_id=sc.company_id,
                event_type=BusinessEventType.founder_alert_sent,
                entity_type="company",
                entity_id=sc.company_id,
                payload={"reason": _STALE_DATA_REASON, "recipient": founder_number, "digest": True},
                created_by="notification_engine",
            )
        )
    return StaleDataDigestResult(companies_flagged=len(stale), sent=send_result is not None)


async def notify_briefing_failed(db: AsyncSession, company: Company) -> bool:
    """Rule 4 entry point, called by the scheduler after a briefing send has
    already failed once and its 9am retry failed too.

    Dedups once per company per business day via the shared founder_alert_sent
    reason — the retry hour is polled several times (every
    SCHEDULER_POLL_INTERVAL_MINUTES), so a briefing that keeps failing to send
    would otherwise re-alert the founder on every tick in that hour. Same guard
    notify_briefing_generation_failed and the stale-data digest already apply.
    """
    day_start = business_now(company.timezone).replace(hour=0, minute=0, second=0, microsecond=0)
    if await _founder_alert_sent_since(db, company.id, _BRIEFING_FAILED_REASON, day_start):
        return False
    message = (
        f"🚨 Briefing Delivery Failed — {company.business_name}\n\n"
        f"Today's morning briefing could not be delivered to {company.business_name} "
        "after an automatic retry.\n"
        "Check the number/token, or send it manually."
    )
    return await send_founder_alert(
        db, company=company, reason=_BRIEFING_FAILED_REASON, message=message
    )


async def notify_briefing_generation_failed(
    db: AsyncSession, company: Company, now: datetime
) -> bool:
    """Founder alert when generate_briefing() itself raises — e.g. every
    configured LLM provider failed or was misconfigured — before any
    MorningBriefing row was even created. Distinct from notify_briefing_failed,
    which only covers a send failing *after* generation already succeeded.
    Without this, a broken LLM chain silently produces zero briefings, zero
    retries (there's no row for the 9am retry hour to find), and zero
    visibility — exactly what let real production briefings go dark for days.

    Dedups once per company per business day via the shared founder_alert_sent
    reason: the scheduler tick can poll several times within the same matching
    hour, and every one of those would otherwise re-attempt generation and
    re-alert.
    """
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if await _founder_alert_sent_since(db, company.id, _BRIEFING_FAILED_REASON, day_start):
        return False
    message = (
        f"🚨 Briefing Generation Failed — {company.business_name}\n\n"
        f"Today's morning briefing could not be generated for {company.business_name} "
        "— the AI narration step errored out before anything was sent.\n"
        "Check the LLM provider configuration (API keys, model names)."
    )
    return await send_founder_alert(
        db, company=company, reason=_BRIEFING_FAILED_REASON, message=message
    )


# ── Orchestrator ────────────────────────────────────────────────────────────


async def run_notification_checks(
    db: AsyncSession, company_id: uuid.UUID, now: datetime | None = None
) -> NotificationRunResult:
    """Build one snapshot and run the two per-company (distributor-facing)
    rules for a company: supplier payment reminders and dealer overdue alerts.
    Rule 3 (stale data) is now a founder-facing, cross-company digest
    (send_stale_data_digest, driven once per scheduler tick) rather than a
    per-company send, and Rule 4 (briefing failure) is scheduler-driven — so
    neither is part of this poll. `now` is overridable so the scheduler/tests
    can pin business time deterministically.
    """
    company = await db.get(Company, company_id)
    if company is None:
        raise ValueError(f"Company {company_id} not found")
    if now is None:
        now = business_now(company.timezone)

    snapshot = await build_snapshot(db, company_id)
    supplier = await check_supplier_payment_reminders(db, company, snapshot, now)
    dealer = await check_dealer_overdue_alerts(db, company, snapshot, now)
    return NotificationRunResult(supplier_reminders=supplier, dealer_alerts=dealer)
