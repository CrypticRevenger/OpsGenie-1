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

Plus three proactive early-warning forecasts (7 days ahead), same shape as
rules 1-2 (stateless, per-company/per-entity dedup, no LLM, no new
conversation state):

5. Cash-shortage forecast — cumulative day-by-day walk of the 7-day window
   projects a negative cash position → distributor alert naming the day and
   the single biggest payment behind it.
6. Stock-out forecast — sales velocity (InvoiceItem history) vs current
   stock_quantity projects a product running out soon → distributor alert.
7. Pre-due invoice nudge — a receivable invoice is due in 1-2 days (not yet
   overdue; that stays rule 2/followup.py's job) → distributor heads-up.

Same layering as app/services/followup.py: reuses send_text_message, writes
NotificationLog + BusinessEvent + ActivityTimeline, and never commits
internally — the caller (the scheduler, one commit per company) owns the
transaction, so a mid-sequence failure never leaves partial state.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.i18n import resolve_locale, t
from app.models.activity_timeline import ActivityEntityType, ActivityEventType, ActivityTimeline
from app.models.business_event import BusinessEvent, BusinessEventType
from app.models.company import Company, OnboardingState
from app.models.notification_log import NotificationLog
from app.services.money_format import format_inr
from app.services.snapshot import (
    Snapshot,
    build_snapshot,
    business_now,
    data_freshness_hours,
    is_cash_sufficient,
)
from app.services.stock_forecast import StockOutForecast, build_stock_out_forecasts
from app.services.whatsapp_client import (
    WhatsAppNotConfiguredError,
    WhatsAppSendError,
    send_template_message,
    send_text_message,
)
from app.services.workflows.payment_reminder_confirm import start_reminder_confirm
from app.services.writes.broadcast import SESSION_WINDOW_HOURS, recently_messaged

logger = logging.getLogger(__name__)

# "within 24h" — since invoices carry dates, not times, this means due today
# or tomorrow (0 or 1 whole days out).
_SUPPLIER_REMINDER_DAYS = 1
_DEALER_ALERT_QUIET_DAYS = 3  # "no follow-up recorded in 3 days"
_SUPPLIER_REMINDER_QUIET_HOURS = 24
_STALE_DATA_HOURS = 24

_STALE_DATA_REASON = "stale_data"
_BRIEFING_FAILED_REASON = "briefing_failed"
_EVENING_BRIEF_FAILED_REASON = "evening_brief_failed"

# Dealer-direct overdue reminder (see check_dealer_overdue_alerts) — a
# separate NotificationLog notification_type from "dealer_overdue_alert"
# above since that one goes to the distributor's own number and this one
# goes straight to the dealer. Deliberately not one of the two types
# instant_reports.delivery_status_reply surfaces: like
# supplier_payment_reminder/dealer_overdue_alert, this is an automated
# background nudge the distributor only ever enabled (once, per dealer),
# never a message they personally triggered.
_DEALER_DIRECT_REMINDER_TYPE = "dealer_direct_reminder"

# Cap how many company names are itemised in a single founder digest so the
# WhatsApp message stays readable; any beyond this are summarised as a count.
_DIGEST_MAX_LISTED = 25

# Proactive early-warning forecasts (rules 5-7) — same per-entity/per-company
# quiet-window dedup shape as rules 1-2 above.
_CASH_FORECAST_QUIET_DAYS = 3  # matches _DEALER_ALERT_QUIET_DAYS cadence
_STOCK_OUT_QUIET_DAYS = 3
# briefing.py imports these two directly (same reuse pattern as its existing
# import of recommendations._STALE_DATA_THRESHOLD_HOURS) so the "Watch this
# week" section and the standalone alert can never disagree about a threshold.
_STOCK_OUT_DAYS_OF_COVER_THRESHOLD = 7
_PREDUE_NUDGE_DAYS_BEFORE = 2
_PREDUE_NUDGE_QUIET_HOURS = 24

# Hard global ceiling: at most ONE founder stale-data digest per this many hours,
# across ALL companies, on top of the per-company/per-day dedup below. The
# per-company dedup only stops a company being *re-listed* the same day — it does
# nothing to stop a *fresh* batch of newly-stale companies (an accidental bulk
# insert, a mass import outage, or test fixtures leaking into prod) from firing a
# brand-new digest on every tick. This ceiling makes that impossible: whatever
# appears, the founder can receive at most one stale digest per interval. ~20h
# (not 24) so a genuine once-a-day pattern is never skipped by clock drift.
_STALE_DIGEST_MIN_INTERVAL_HOURS = 20


@dataclass(frozen=True)
class NotificationRunResult:
    supplier_reminders: int
    dealer_alerts: int
    cash_shortage_forecasts: int
    stock_out_forecasts: int
    predue_nudges: int


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


async def _send_and_log_with_id(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    recipient: str,
    notification_type: str,
    message: str,
) -> str | None:
    """Same contract as _send_and_log, but returns the real WhatsApp message
    id (wamid) on success instead of a bare bool — needed by
    check_supplier_payment_reminders so a later native quote-reply to this
    exact message can be matched back to which bill it was about (see
    app/services/workflows/payment_reminder_confirm.py::promote_queued_
    reminder). Kept separate from _send_and_log rather than changing that
    function's return type — the other four notification rules that call it
    have no use for the id, so there's nothing to gain by touching them too.
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
    return send_result.message_id if send_result else None


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


async def _recent_business_event_exists(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    event_type: BusinessEventType,
    since: datetime,
) -> bool:
    """Company-level analogue of _recent_activity_exists, for alerts that
    aren't about one specific dealer/supplier/product — e.g. the cash-
    shortage forecast, which is a statement about the company as a whole.
    Unlike _founder_alert_sent_since, no payload["reason"] filter is needed:
    each caller passes its own dedicated event_type, so the type alone
    disambiguates.
    """
    found = await db.scalar(
        select(BusinessEvent.id).where(
            BusinessEvent.company_id == company_id,
            BusinessEvent.event_type == event_type,
            BusinessEvent.created_at >= since,
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

    due_payments = []
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
        due_payments.append(payment)

    # Only the first bill this tick becomes an interactive "did you pay
    # this?" confirmation — Company.active_workflow/active_pending_operation_id
    # /pending_follow_up_invoice_id are single pointers, so anything else due
    # the same tick queues behind it (see
    # app/services/workflows/payment_reminder_confirm.py) and gets its own
    # question once this one is answered. If the founder is already mid some
    # other guided flow, none of today's bills interrupt it — they stay purely
    # informational this cycle and get a fresh interactive question next time
    # this rule runs (the 24h dedup below means that's tomorrow at the
    # earliest).
    #
    # pending_follow_up_invoice_id is included for the same reason
    # followup.py::send_due_today_follow_up checks the other two: a live
    # follow-up asks "Has INV-100 been paid? 1 = paid in full" about a
    # *receivable*, and active_workflow outranks it in the webhook's dispatch
    # chain — so starting this confirm on top would make the founder's
    # unchanged "1" answer a question about a *payable* instead. A directional
    # money mix-up from a reply they never reconsidered.
    #
    # onboarding_state is included too: the website import step can seed
    # payable invoices (and this rule/scheduler poll every
    # subscription_active company regardless of onboarding progress — see
    # onboarding.py's activate route) before the WhatsApp onboarding chat
    # itself has finished. onboarding_state outranks active_workflow in the
    # webhook's dispatch chain, so starting this confirm mid-onboarding would
    # wedge it until onboarding completes, then hijack the founder's first
    # post-onboarding reply instead of the menu they'd expect.
    can_start_confirm = (
        company.onboarding_state == OnboardingState.completed
        and company.active_workflow is None
        and company.active_pending_operation_id is None
        and company.pending_follow_up_invoice_id is None
    )

    def _queue_item(p) -> dict:
        return {
            "supplier_id": str(p.supplier_id),
            "supplier_name": p.supplier_name,
            "amount": str(p.amount),
            "invoice_id": str(p.invoice_id),
            "invoice_number": p.invoice_number,
        }

    for index, payment in enumerate(due_payments):
        loc = resolve_locale(company)
        if payment.due_date < today:
            # expected_payments_7d now includes already-overdue payables (see
            # snapshot.py::_expected_payments_7d) — without this branch every
            # one of them would wrongly say "due tomorrow".
            when = t("notify.when_overdue", loc, days=(today - payment.due_date).days)
        elif payment.due_date == today:
            when = t("notify.when_today", loc)
        else:
            when = t("notify.when_tomorrow", loc)
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
        if index == 0 and can_start_confirm:
            question = start_reminder_confirm(
                company,
                _queue_item(payment),
                [_queue_item(p) for p in due_payments[1:]],
            )
            message = f"{message}\n\n{question}"

        message_id = await _send_and_log_with_id(
            db,
            company_id=company.id,
            recipient=company.whatsapp_number,
            notification_type="supplier_payment_reminder",
            message=message,
        )
        if can_start_confirm and message_id is not None:
            # Attach this bill's own wamid to its scratch entry — either the
            # just-started active conversation (index 0) or its still-queued
            # entry (index > 0, matched by invoice_id — its own message is
            # only sent now, this same iteration, so this is the earliest
            # point its id can be known) — so a later native quote-reply to
            # *this specific* WhatsApp message can be recognized and jump
            # the queue (see payment_reminder_confirm.py::
            # promote_queued_reminder). A company mid some other flow
            # (can_start_confirm is False) never got a queue started at all,
            # so there's nothing to attach this to.
            scratch = dict(company.workflow_scratch or {})
            if index == 0:
                scratch["whatsapp_message_id"] = message_id
            else:
                queue = scratch.get("queue", [])
                for queued_item in queue:
                    if queued_item.get("invoice_id") == str(payment.invoice_id):
                        queued_item["whatsapp_message_id"] = message_id
                        break
                scratch["queue"] = queue
            company.workflow_scratch = scratch

        if not message_id:
            # Send failed — leave this bill undeduped so the next tick
            # retries it, instead of silently suppressing a same-day
            # reminder for the rest of the quiet window (see
            # run_notification_checks' docstring on why this rule now
            # checks the send result before marking dedup).
            continue
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


async def _send_dealer_direct_reminder(
    db: AsyncSession,
    company: Company,
    dealer_phone: str,
    message: str,
    *,
    dealer_name: str,
    amount_display: str,
    days_overdue: int,
) -> bool:
    """Proactively message a dealer's own WhatsApp — same free-form-vs-
    template branch as app/services/writes/broadcast.py's send loop (a
    dealer flagged overdue has typically never messaged the distributor's
    number first, so outside their own 24h session window this needs a
    Meta-approved template), reused rather than duplicated. Never raises —
    same fail-open contract as _send_and_log.

    The template branch (dealer_payment_reminder_v2, confirmed Active in
    WhatsApp Manager 2026-07-25) has 4 variables — dealer name, business
    name, amount, days overdue, in that order, matching notify.
    dealer_direct_reminder's own wording — so it needs each field passed
    discretely, not the single pre-composed `message` string. That string is
    still used for the free-form within-session-window branch above (a
    plain text message, no template needed there) and for the
    NotificationLog's stored text either way.
    """
    settings = get_settings()
    since = datetime.now(UTC) - timedelta(hours=SESSION_WINDOW_HOURS)
    send_result = None
    try:
        if await recently_messaged(db, company.id, dealer_phone, since):
            send_result = await send_text_message(dealer_phone, message)
        elif not settings.dealer_reminder_template_name:
            raise WhatsAppNotConfiguredError("DEALER_REMINDER_TEMPLATE_NAME not configured")
        else:
            send_result = await send_template_message(
                dealer_phone,
                settings.dealer_reminder_template_name,
                settings.dealer_reminder_template_language,
                body_params=[dealer_name, company.business_name, amount_display, str(days_overdue)],
            )
    except (WhatsAppNotConfiguredError, WhatsAppSendError) as exc:
        logger.warning("Dealer direct reminder to %s not sent: %s", dealer_phone, exc)

    db.add(
        NotificationLog(
            company_id=company.id,
            notification_type=_DEALER_DIRECT_REMINDER_TYPE,
            recipient_whatsapp=dealer_phone,
            message_text=message,
            whatsapp_message_id=send_result.message_id if send_result else None,
            delivery_status="sent" if send_result else "failed_to_send",
        )
    )
    return send_result is not None


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
        delivered = await _send_and_log(
            db,
            company_id=company.id,
            recipient=company.whatsapp_number,
            notification_type="dealer_overdue_alert",
            message=message,
        )

        # Direct-to-dealer reminder — only when the distributor has
        # explicitly consented to this dealer (see Dealer.direct_reminders_
        # enabled's docstring) and a phone is actually on file. Shares this
        # same dedup window/gate as the founder-facing alert above rather
        # than tracking its own — both are triggered by the exact same
        # "still overdue, no recent contact" fact about this one dealer.
        dealer_reminder_sent = False
        if dealer.direct_reminders_enabled and dealer.dealer_phone:
            dealer_message = t(
                "notify.dealer_direct_reminder",
                resolve_locale(company),
                dealer=dealer.dealer_name,
                business=company.business_name,
                amount=format_inr(dealer.outstanding),
                days=dealer.days_overdue,
            )
            dealer_reminder_sent = await _send_dealer_direct_reminder(
                db,
                company,
                dealer.dealer_phone,
                dealer_message,
                dealer_name=dealer.dealer_name,
                amount_display=format_inr(dealer.outstanding),
                days_overdue=dealer.days_overdue,
            )

        if not delivered:
            # Founder-facing alert failed to send — leave this dealer
            # undeduped so the next tick retries, instead of silently
            # suppressing a High-Risk overdue alert for 3 days. The
            # direct-to-dealer reminder above (if any) already recorded its
            # own independent NotificationLog row regardless.
            continue
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
                    "dealer_direct_reminder_sent": dealer_reminder_sent,
                },
                created_by="notification_engine",
            )
        )
        sent += 1
    return sent


# ── Rule 5: cash-shortage forecast (7-day window, company-level) ───────────


async def check_cash_shortage_forecast(
    db: AsyncSession, company: Company, snapshot: Snapshot, now: datetime
) -> int:
    """Fires when forecast_cash_deficit (app/services/snapshot.py) projects a
    negative cash position within the 7-day window. Company-level, not
    per-entity, so dedup is a BusinessEvent lookback rather than
    ActivityTimeline. Skips (returns 0) if a trigger_payment can't be
    identified — provably can't happen given the deficit can only be caused
    by a payment's delta, but the alert must never invent a cause it doesn't
    have.

    Future refinement (not built — not essential for V1, confirmed with the
    user): suppress this standalone push when today's briefing already
    included the same warning via build_watch_this_week. Today it can
    double-surface, same as rules 1-2 already do against the briefing's
    recommendations.
    """
    forecast = snapshot.cash_deficit_forecast
    if forecast is None or forecast.trigger_payment is None:
        return 0

    since = now - timedelta(days=_CASH_FORECAST_QUIET_DAYS)
    if await _recent_business_event_exists(
        db,
        company_id=company.id,
        event_type=BusinessEventType.cash_shortage_forecast_sent,
        since=since,
    ):
        return 0

    trigger = forecast.trigger_payment
    today = now.date()
    # expected_payments_7d can now include an already-overdue payable (see
    # snapshot.py::_expected_payments_7d), which the trigger payment could be
    # — clamp at 0 rather than showing a negative "due in -3 day(s)".
    trigger_days = max((trigger.due_date - today).days, 0)
    message = t(
        "notify.cash_shortage_forecast",
        resolve_locale(company),
        days=forecast.days_until,
        supplier=trigger.supplier_name,
        amount=format_inr(trigger.amount),
        trigger_days=trigger_days,
        expected_out=format_inr(snapshot.expected_payments_7d_total),
        expected_in=format_inr(
            snapshot.cash_available_today + snapshot.expected_collections_7d_total
        ),
    )
    delivered = await _send_and_log(
        db,
        company_id=company.id,
        recipient=company.whatsapp_number,
        notification_type="cash_shortage_forecast",
        message=message,
    )
    if not delivered:
        # Leave undeduped so the next tick retries — a cash-shortage warning
        # that never actually reached the founder shouldn't go quiet for
        # _CASH_FORECAST_QUIET_DAYS.
        return 0
    db.add(
        BusinessEvent(
            company_id=company.id,
            event_type=BusinessEventType.cash_shortage_forecast_sent,
            entity_type="company",
            entity_id=company.id,
            payload={
                "days_until": forecast.days_until,
                "trigger_supplier_name": trigger.supplier_name,
                "trigger_amount": str(trigger.amount),
            },
            created_by="notification_engine",
        )
    )
    return 1


# ── Rule 6: stock-out forecast (sales velocity vs stock) ───────────────────


async def check_stock_out_forecasts(
    db: AsyncSession, company: Company, snapshot: Snapshot, now: datetime
) -> int:
    today = now.date()
    forecasts: list[StockOutForecast] = await build_stock_out_forecasts(db, company.id, today)
    since = now - timedelta(days=_STOCK_OUT_QUIET_DAYS)
    sent = 0
    for forecast in forecasts:
        if forecast.days_of_cover > _STOCK_OUT_DAYS_OF_COVER_THRESHOLD:
            continue
        if await _recent_activity_exists(
            db,
            company_id=company.id,
            entity_type=ActivityEntityType.product,
            entity_id=forecast.product_id,
            event_types=(ActivityEventType.stock_out_forecast_sent,),
            since=since,
        ):
            continue

        message = t(
            "notify.stock_out_forecast",
            resolve_locale(company),
            product=forecast.product_name,
            days=forecast.days_of_cover,
        )
        delivered = await _send_and_log(
            db,
            company_id=company.id,
            recipient=company.whatsapp_number,
            notification_type="stock_out_forecast",
            message=message,
        )
        if not delivered:
            # Leave undeduped so the next tick retries this product.
            continue
        db.add(
            ActivityTimeline(
                company_id=company.id,
                entity_type=ActivityEntityType.product,
                entity_id=forecast.product_id,
                event_type=ActivityEventType.stock_out_forecast_sent,
                notes=(
                    f"Stock-out forecast: {forecast.product_name}, "
                    f"~{forecast.days_of_cover}d cover"
                ),
            )
        )
        db.add(
            BusinessEvent(
                company_id=company.id,
                event_type=BusinessEventType.stock_out_forecast_sent,
                entity_type="product",
                entity_id=forecast.product_id,
                payload={
                    "product_name": forecast.product_name,
                    "days_of_cover": forecast.days_of_cover,
                    "stock_quantity": str(forecast.stock_quantity),
                },
                created_by="notification_engine",
            )
        )
        sent += 1
    return sent


# ── Rule 7: pre-due invoice nudge (due soon, not yet overdue) ──────────────


async def check_predue_invoice_nudges(
    db: AsyncSession, company: Company, snapshot: Snapshot, now: datetime
) -> int:
    today = now.date()
    since = now - timedelta(hours=_PREDUE_NUDGE_QUIET_HOURS)
    sent = 0
    for collection in snapshot.expected_collections_7d:
        days_out = (collection.due_date - today).days
        # Due today/overdue stays followup.py's job (rule 2 covers High-Risk
        # overdue dealers separately) — this rule only covers the days
        # strictly before that.
        if not (1 <= days_out <= _PREDUE_NUDGE_DAYS_BEFORE):
            continue
        if await _recent_activity_exists(
            db,
            company_id=company.id,
            entity_type=ActivityEntityType.dealer,
            entity_id=collection.dealer_id,
            event_types=(ActivityEventType.predue_nudge_sent,),
            since=since,
        ):
            continue

        message = t(
            "notify.predue_nudge",
            resolve_locale(company),
            dealer=collection.dealer_name,
            amount=format_inr(collection.amount),
            days=days_out,
        )
        delivered = await _send_and_log(
            db,
            company_id=company.id,
            recipient=company.whatsapp_number,
            notification_type="predue_invoice_nudge",
            message=message,
        )
        if not delivered:
            # Leave undeduped so the next tick retries this dealer.
            continue
        db.add(
            ActivityTimeline(
                company_id=company.id,
                entity_type=ActivityEntityType.dealer,
                entity_id=collection.dealer_id,
                event_type=ActivityEventType.predue_nudge_sent,
                amount=collection.amount,
                notes=f"Pre-due nudge: {collection.dealer_name} due in {days_out}d",
            )
        )
        db.add(
            BusinessEvent(
                company_id=company.id,
                event_type=BusinessEventType.predue_nudge_sent,
                entity_type="dealer",
                entity_id=collection.dealer_id,
                payload={
                    "dealer_name": collection.dealer_name,
                    "amount": str(collection.amount),
                    "days_out": days_out,
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


async def _stale_digest_sent_within(db: AsyncSession, interval: timedelta) -> bool:
    """True if ANY founder stale-data digest was recorded within `interval` of
    now (real wall-clock). Reads the same durable founder_alert_sent /
    stale_data BusinessEvent marker the per-company dedup writes, but ignores
    which company it belonged to — it is the *global* rate limiter that caps the
    founder to one stale digest per interval regardless of how many companies
    are flagged. Uses the server clock (created_at), not the caller's `now`
    override, because it is a guard on real outbound cadence, not on business
    logic timing.
    """
    since = datetime.now(UTC) - interval
    found = await db.scalar(
        select(BusinessEvent.id).where(
            BusinessEvent.event_type == BusinessEventType.founder_alert_sent,
            BusinessEvent.payload["reason"].astext == _STALE_DATA_REASON,
            BusinessEvent.created_at >= since,
        )
    )
    return found is not None


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

    # Hard global ceiling (see _STALE_DIGEST_MIN_INTERVAL_HOURS): if a digest
    # already went out within the interval, suppress this one entirely — even
    # though `stale` here is a *new* batch the per-company dedup wouldn't catch.
    # These companies are simply reported in the next interval's digest, so
    # nothing is lost, but the founder can never be streamed digest after digest
    # by a sudden mass of flagged companies.
    if await _stale_digest_sent_within(
        db, timedelta(hours=_STALE_DIGEST_MIN_INTERVAL_HOURS)
    ):
        logger.info(
            "Stale-data digest suppressed by global %dh ceiling — %d newly-flagged "
            "company(ies) will roll into the next digest.",
            _STALE_DIGEST_MIN_INTERVAL_HOURS,
            len(stale),
        )
        return StaleDataDigestResult(companies_flagged=len(stale), sent=False)

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


async def notify_evening_brief_failed(db: AsyncSession, company: Company) -> bool:
    """Founder alert when the evening brief still hasn't been delivered a
    while after its scheduled hour — the evening-brief analogue of
    notify_briefing_failed. Unlike the morning briefing (a single retry_hour
    attempt), app/core/scheduler.py now retries the evening brief send on
    every tick from evening_brief_hour onward (see
    evening_brief.evening_brief_delivered_today), so this alert exists purely
    for founder visibility when the underlying problem (Meta down, bad token)
    persists — it never gates the retry itself.

    Dedups once per company per business day via the shared founder_alert_sent
    reason, same shape as notify_briefing_failed/notify_briefing_generation_
    failed.
    """
    day_start = business_now(company.timezone).replace(hour=0, minute=0, second=0, microsecond=0)
    if await _founder_alert_sent_since(db, company.id, _EVENING_BRIEF_FAILED_REASON, day_start):
        return False
    message = (
        f"🚨 Evening Brief Delivery Failed — {company.business_name}\n\n"
        f"Today's evening business summary could not be delivered to "
        f"{company.business_name}.\n"
        "Check the number/token, or send it manually."
    )
    return await send_founder_alert(
        db, company=company, reason=_EVENING_BRIEF_FAILED_REASON, message=message
    )


# ── Orchestrator ────────────────────────────────────────────────────────────


async def run_notification_checks(
    db: AsyncSession, company_id: uuid.UUID, now: datetime | None = None
) -> NotificationRunResult:
    """Build one snapshot and run every per-company (distributor-facing) rule:
    supplier payment reminders, dealer overdue alerts, and the three 7-day
    forecasts (cash shortage, stock-out, pre-due nudge). Rule 3 (stale data)
    is now a founder-facing, cross-company digest (send_stale_data_digest,
    driven once per scheduler tick) rather than a per-company send, and Rule 4
    (briefing failure) is scheduler-driven — so neither is part of this poll.
    `now` is overridable so the scheduler/tests can pin business time
    deterministically.

    Each rule is committed as soon as it returns, never batched into one
    commit at the end. Every rule performs real WhatsApp sends *before* its
    dedup marker is written, so a single trailing commit means any later
    failure — a Neon drop mid-tick, a raise inside a subsequent rule, a failed
    commit — rolls back the dedup markers for messages that already physically
    went out. The external cron re-ticks every ~10 minutes, sees no marker,
    and re-sends all of them, repeating for as long as the fault persists.
    That is the shape of the July 2026 founder-flood incident, and it is the
    same reason app/services/writes/broadcast.py commits per recipient rather
    than once at the end of its send loop. app/core/scheduler.py's
    _dispatch_for_company docstring states this principle for the four
    top-level concerns; it applies just as much *within* this pass.

    The five distributor-facing rules (1, 2, 5, 6, 7) also only write their
    dedup marker (ActivityTimeline/BusinessEvent) when _send_and_log actually
    reported success — a send that failed leaves the entity undeduped so the
    next tick retries it, rather than being marked "reminded" for the rest of
    the quiet window despite the founder never receiving it. Rules 3/4
    (send_stale_data_digest, notify_briefing_failed,
    notify_briefing_generation_failed) deliberately keep the opposite,
    fail-open behavior for founder-facing meta-alerts — see their own
    docstrings.
    """
    company = await db.get(Company, company_id)
    if company is None:
        raise ValueError(f"Company {company_id} not found")
    if now is None:
        now = business_now(company.timezone)

    snapshot = await build_snapshot(db, company_id)

    supplier = await check_supplier_payment_reminders(db, company, snapshot, now)
    await db.commit()
    dealer = await check_dealer_overdue_alerts(db, company, snapshot, now)
    await db.commit()
    cash_forecast = await check_cash_shortage_forecast(db, company, snapshot, now)
    await db.commit()
    stock_out = await check_stock_out_forecasts(db, company, snapshot, now)
    await db.commit()
    predue = await check_predue_invoice_nudges(db, company, snapshot, now)
    await db.commit()

    return NotificationRunResult(
        supplier_reminders=supplier,
        dealer_alerts=dealer,
        cash_shortage_forecasts=cash_forecast,
        stock_out_forecasts=stock_out,
        predue_nudges=predue,
    )
