"""APScheduler dispatch — V0.1 Step 15.

"APScheduler inside FastAPI lifespan for 8am briefing and notification
schedules." One recurring poll job (every SCHEDULER_POLL_INTERVAL_MINUTES)
iterates every subscription-active company and acts when *that company's own*
business-local clock (business_now(company.timezone)) hits a configured hour.
A single poll-and-dispatch job is simpler to reason about and test than one
APScheduler trigger per company per concern, and correct for pilot scale.

Per company, per tick — each in its own AsyncSession with its own commit, so
one company's failure never rolls back another's:
  - BRIEFING_HOUR         → generate + send today's morning briefing (once)
  - BRIEFING_RETRY_HOUR   → retry a failed briefing send once; founder alert
                            if it still fails
  - FOLLOWUP_HOUR         → send_due_today_follow_up (Phase 9, idempotent)
  - every tick            → run NotificationEngine rules (they dedup internally)

run_scheduled_tick takes an optional `now` override so the dispatch decisions
are testable without waiting for real wall-clock hours.

Deployment note: APScheduler runs inside the web process, so on a host that
spins the process down when idle (e.g. a free-tier PaaS), ticks only fire
while the process is awake. For a real pilot, run the web service on an
always-on instance or move this loop to a dedicated worker.
"""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.models.company import Company
from app.models.morning_briefing import MorningBriefing
from app.services.briefing import generate_briefing, latest_briefing_today
from app.services.evening_brief import evening_brief_delivered_today, send_evening_brief
from app.services.followup import send_due_today_follow_up
from app.services.notifications import (
    notify_briefing_failed,
    notify_briefing_generation_failed,
    notify_evening_brief_failed,
    run_notification_checks,
    send_stale_data_digest,
)
from app.services.snapshot import business_now
from app.services.whatsapp_client import (
    WhatsAppNotConfiguredError,
    WhatsAppSendError,
    send_text_message,
)

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None

# Postgres session-level advisory-lock key identifying "a scheduled tick is in
# progress." run_scheduled_tick can now be driven from more than one place at
# once — the in-process APScheduler poll job (start_scheduler) AND the external
# GitHub-cron POST /admin/scheduler/tick (see app/api/admin/scheduler.py), plus
# a manual admin retry. Each briefing/evening-brief send dedups with an
# unlocked SELECT-then-send, so two ticks overlapping at the same business hour
# could both observe "not sent yet" and each fire a real duplicate WhatsApp
# message. This lock serializes the whole pass across every process/connection:
# whoever grabs it runs; any concurrent tick sees it held and skips (a no-op —
# the running pass already covers every company). The value is arbitrary but
# must stay stable so all callers contend on the same lock.
_TICK_ADVISORY_LOCK_KEY = 728113


async def _deliver_briefing(db: AsyncSession, company: Company, briefing: MorningBriefing) -> bool:
    """Send an already-generated briefing and record the outcome on the row.
    Returns True on a successful send.

    Claims delivery atomically first via MorningBriefing.delivery_claimed_at
    (same shape as evening_brief's delivered_at claim on
    DailyBusinessSnapshot) — closes the send-side duplicate race for two
    overlapping dispatch attempts (e.g. two overlapping scheduler ticks, the
    same real-world shape as the evening brief's 3x-send production bug)
    both reaching this same undelivered row at once. Postgres's row lock on
    the exact briefing row serializes them by construction.

    A lost claim refreshes `briefing` from the DB and returns whether the
    row is now actually "sent" — so a caller checking *why* this returned
    False can distinguish "another attempt is delivering/just delivered
    this" (delivery_status now "sent", not a real failure — don't alert the
    founder) from "this row is genuinely undelivered" (still None/
    failed_to_send). There's an inherent narrow window where a concurrent
    winner has claimed but not yet resolved — this call reports that as a
    failure too, same accepted tradeoff evening_brief's own analogous check
    (evening_brief_delivered_today) already makes.
    """
    claim = await db.execute(
        update(MorningBriefing)
        .where(
            MorningBriefing.id == briefing.id,
            MorningBriefing.delivery_claimed_at.is_(None),
        )
        .values(delivery_claimed_at=business_now(company.timezone))
    )
    if claim.rowcount == 0:
        await db.refresh(briefing)
        logger.info(
            "Briefing %s already claimed for delivery by another attempt (status=%s), skipping.",
            briefing.id,
            briefing.delivery_status,
        )
        return briefing.delivery_status == "sent"

    try:
        result = await send_text_message(company.whatsapp_number, briefing.generated_text)
    except (WhatsAppNotConfiguredError, WhatsAppSendError) as exc:
        logger.warning("Briefing delivery to %s failed: %s", company.whatsapp_number, exc)
        briefing.delivery_status = "failed_to_send"
        # Release the claim so a later tick can retry — matches the existing
        # "keeps retrying" contract instead of wedging this row behind a
        # claim nothing will ever release.
        briefing.delivery_claimed_at = None
        return False
    briefing.sent_at = business_now(company.timezone)
    briefing.delivery_status = "sent"
    logger.info("Briefing %s delivered to company %s", briefing.id, company.id)
    return bool(result)


async def _dispatch_for_company(company_id, now: datetime | None) -> dict:
    """All time-gated actions for one company, in a fresh session. `now`
    (business-local) is resolved from the company's timezone when not pinned
    by a caller/test.

    Each concern commits independently rather than as one big transaction:
    every branch below performs a real, irreversible WhatsApp send, so its
    durable record (a briefing's delivery_status, a NotificationLog row) must
    be committed before the next concern runs — otherwise a later failure
    would roll back the record of a message that already physically went out,
    breaking the 9am retry decision or causing a duplicate resend next tick.

    Returns a diagnostic dict (what hour was matched, what each concern
    decided to do) so a tick can be inspected after the fact — this is what
    POST /admin/scheduler/tick surfaces, since a silent no-op here (e.g. a
    wrong timezone, or a briefing_hour that never matches) is otherwise
    indistinguishable from "everything is fine, nothing was due yet."
    """
    settings = get_settings()
    async with async_session_factory() as db:
        company = await db.get(Company, company_id)
        if company is None or not company.subscription_active:
            return {
                "company_id": str(company_id),
                "dispatched": False,
                "reason": "company not found or subscription inactive",
            }
        local_now = now or business_now(company.timezone)
        hour = local_now.hour
        today = local_now.date()

        # Per-company briefing hour overrides the global default (collected in
        # onboarding); the retry then runs the following hour. When unset, the
        # global BRIEFING_HOUR/BRIEFING_RETRY_HOUR pair is used unchanged.
        if company.briefing_hour is not None:
            briefing_hour = company.briefing_hour
            # Wrap so hour 23 retries at 0, not a 24 that could never match.
            retry_hour = (briefing_hour + 1) % 24
        else:
            briefing_hour = settings.briefing_hour
            retry_hour = settings.briefing_retry_hour

        evening_brief_hour = (
            company.evening_brief_hour
            if company.evening_brief_hour is not None
            else settings.evening_brief_hour
        )

        diagnostics: dict = {
            "company_id": str(company.id),
            "company_name": company.business_name,
            "dispatched": True,
            "timezone": company.timezone,
            "local_time": local_now.isoformat(),
            "hour": hour,
            "briefing_hour": briefing_hour,
            "retry_hour": retry_hour,
            "followup_hour": settings.followup_hour,
            "evening_brief_hour": evening_brief_hour,
            "actions": {
                "briefing": "hour_not_matched",
                "followup": "hour_not_matched",
                "evening_brief": "hour_not_matched",
                "notifications": "skipped_before_business_hours",
            },
        }

        # >= briefing_hour, not ==: a tick that lands late (a missed poll, a
        # cold-start delay, the process being asleep through briefing_hour
        # entirely) must still catch up rather than silently skip the whole
        # day. Every branch below is itself idempotent (keyed off the real
        # MorningBriefing row's state, not the clock), so re-checking on every
        # later tick is safe — it just means "nothing to do" once delivered.
        if hour >= briefing_hour:
            existing = await latest_briefing_today(db, company, today)
            if existing is None:
                try:
                    briefing = await generate_briefing(db, company.id)
                except Exception as exc:  # noqa: BLE001 - any provider-chain failure must alert, not crash the pass
                    logger.exception("Briefing generation failed for company %s", company.id)
                    await notify_briefing_generation_failed(db, company, local_now)
                    await db.commit()
                    diagnostics["actions"]["briefing"] = (
                        f"generation_failed_founder_alerted ({exc})"
                    )
                else:
                    delivered = await _deliver_briefing(db, company, briefing)
                    await db.commit()
                    diagnostics["actions"]["briefing"] = (
                        "generated_and_sent" if delivered else "generated_but_send_failed"
                    )
            elif existing.delivery_status is None:
                # A row for today already exists but was only ever generated,
                # never delivered — e.g. a dashboard/admin preview call
                # (POST .../briefing, app/api/admin/briefing.py) that creates
                # a MorningBriefing without sending it. Treating "a row
                # exists" as "already sent" used to silently swallow the
                # scheduled push for the rest of the day; deliver this same
                # row now instead of skipping it (mirrors why
                # _morning_briefing_reply self-marks its own delivery).
                delivered = await _deliver_briefing(db, company, existing)
                await db.commit()
                diagnostics["actions"]["briefing"] = (
                    "delivered_existing_undelivered_briefing"
                    if delivered
                    else "existing_briefing_send_failed"
                )
            elif existing.delivery_status == "failed_to_send" and hour >= retry_hour:
                # Retried on every tick from retry_hour onward (not just a
                # single retry_hour window) — a real WhatsApp-down outage now
                # gets more chances to recover over the rest of the day
                # instead of the day going dark once the one-shot retry also
                # failed. notify_briefing_failed dedups its founder alert to
                # once per business day regardless of how many times this
                # branch re-fires.
                delivered = await _deliver_briefing(db, company, existing)
                if not delivered:
                    await notify_briefing_failed(db, company)
                    diagnostics["actions"]["briefing"] = "retry_failed_founder_alerted"
                else:
                    diagnostics["actions"]["briefing"] = "retry_sent"
                await db.commit()
            else:
                diagnostics["actions"]["briefing"] = (
                    f"no_action_needed (status={existing.delivery_status})"
                )

        # >= not == (same catch-up reasoning as briefing_hour above) —
        # send_due_today_follow_up is itself idempotent (atomically claims
        # its single-slot pointer, returns "already_pending"/"none_due" once
        # there's nothing left to do), so re-checking every tick for the rest
        # of the day is safe.
        if hour >= settings.followup_hour:
            result = await send_due_today_follow_up(db, company.id)
            await db.commit()
            diagnostics["actions"]["followup"] = result.status

        if hour >= evening_brief_hour:
            sent = await send_evening_brief(db, company)
            await db.commit()
            if sent:
                diagnostics["actions"]["evening_brief"] = "sent"
            elif await evening_brief_delivered_today(db, company, today):
                diagnostics["actions"]["evening_brief"] = "already_delivered_today"
            else:
                # Distinguishable from "already delivered" above — this
                # attempt just failed. Alert the founder once we're at least
                # an hour past the scheduled hour (same one-tick grace period
                # the morning briefing's retry_hour gives before alerting),
                # deduped to once/day; the send itself keeps retrying on every
                # later tick regardless of whether the alert already fired.
                diagnostics["actions"]["evening_brief"] = "send_failed"
                if hour >= evening_brief_hour + 1:
                    await notify_evening_brief_failed(db, company)
                    await db.commit()
                    diagnostics["actions"]["evening_brief"] = "send_failed_founder_alerted"

        # NotificationEngine only during business hours — the morning briefing
        # hour onward — so a payment that becomes "due tomorrow" at local
        # midnight doesn't fire a real WhatsApp alert at 00:15. Rules dedup
        # internally, so the first daytime tick is when each alert goes out.
        if hour >= briefing_hour:
            result = await run_notification_checks(db, company.id, now=local_now)
            await db.commit()
            diagnostics["actions"]["notifications"] = (
                f"checked (supplier_reminders={result.supplier_reminders}, "
                f"dealer_alerts={result.dealer_alerts}, "
                f"cash_shortage_forecasts={result.cash_shortage_forecasts}, "
                f"stock_out_forecasts={result.stock_out_forecasts}, "
                f"predue_nudges={result.predue_nudges})"
            )

        return diagnostics


async def run_scheduled_tick(now: datetime | None = None) -> dict:
    """One poll pass over every subscription-active company. Each company is
    dispatched in its own session/transaction so a single failure is isolated
    and logged, never aborting the rest of the pass. `now` pins business-local
    time for tests; production passes None so each company uses its own zone.

    The whole pass is guarded by a Postgres advisory lock so it can never run
    concurrently with itself — see _TICK_ADVISORY_LOCK_KEY. If another tick
    already holds the lock (the in-process poller and the external cron firing
    close together), this call returns immediately without dispatching; the
    holder's pass already covers every company.

    Returns a diagnostic dict — whether the lock was acquired, the server's
    UTC time, and each company's per-concern dispatch decision (see
    _dispatch_for_company) — so a caller (POST /admin/scheduler/tick) can be
    inspected after the fact instead of trusting a silent "tick complete".
    """
    server_time_utc = (now or datetime.now(ZoneInfo("UTC"))).isoformat()
    # A dedicated session holds the connection-scoped advisory lock for the
    # whole pass. It is used ONLY for the lock — every company is dispatched in
    # its own separate session — so the lock connection is never committed or
    # returned to the pool mid-pass, which is what keeps the lock held.
    async with async_session_factory() as lock_db:
        got_lock = await lock_db.scalar(
            select(func.pg_try_advisory_lock(_TICK_ADVISORY_LOCK_KEY))
        )
        if not got_lock:
            logger.info("Scheduled tick already in progress elsewhere — skipping this pass.")
            return {
                "server_time_utc": server_time_utc,
                "lock_acquired": False,
                "companies": [],
            }
        try:
            rows = await lock_db.scalars(
                select(Company.id).where(Company.subscription_active.is_(True))
            )
            company_ids = list(rows.all())

            results = []
            for company_id in company_ids:
                try:
                    result = await _dispatch_for_company(company_id, now)
                    results.append(result or {"company_id": str(company_id)})
                except Exception as exc:  # noqa: BLE001 - one company's failure must not stop the rest
                    logger.exception("Scheduled dispatch failed for company %s", company_id)
                    results.append({"company_id": str(company_id), "error": str(exc)})

            # Founder stale-data digest runs ONCE per tick, across all companies,
            # in its own session — so N stale companies produce one founder
            # WhatsApp message, not N. Isolated in its own try so a digest
            # failure never aborts an otherwise-successful pass.
            stale_digest: dict = {"status": "skipped"}
            try:
                async with async_session_factory() as digest_db:
                    digest = await send_stale_data_digest(digest_db, now=now)
                    await digest_db.commit()
                stale_digest = {
                    "companies_flagged": digest.companies_flagged,
                    "sent": digest.sent,
                }
            except Exception as exc:  # noqa: BLE001 - digest failure must not fail the pass
                logger.exception("Stale-data digest failed")
                stale_digest = {"error": str(exc)}

            return {
                "server_time_utc": server_time_utc,
                "lock_acquired": True,
                "companies": results,
                "stale_data_digest": stale_digest,
            }
        finally:
            await lock_db.scalar(select(func.pg_advisory_unlock(_TICK_ADVISORY_LOCK_KEY)))


def start_scheduler() -> AsyncIOScheduler | None:
    """Start the single poll job inside the running event loop. No-op (returns
    None) unless SCHEDULER_ENABLED is true — it defaults False (fail-closed),
    so a plain uvicorn boot or an imported app never spins up background
    dispatch and can't fire real sends without an explicit opt-in.
    """
    global _scheduler
    settings = get_settings()
    if not settings.scheduler_enabled:
        logger.info("Scheduler disabled (SCHEDULER_ENABLED=false) — not starting.")
        return None
    if _scheduler is not None:
        return _scheduler

    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.add_job(
        run_scheduled_tick,
        trigger="interval",
        minutes=settings.scheduler_poll_interval_minutes,
        id="opsgenie_poll",
        max_instances=1,  # never overlap two ticks
        coalesce=True,  # collapse missed ticks into one
    )
    _scheduler.start()
    logger.info(
        "Scheduler started — polling every %d min.", settings.scheduler_poll_interval_minutes
    )
    return _scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Scheduler stopped.")
