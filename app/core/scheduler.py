"""APScheduler dispatch — SPEC.md V0.1 Step 15.

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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.models.company import Company
from app.models.morning_briefing import MorningBriefing
from app.services.briefing import generate_briefing
from app.services.followup import send_due_today_follow_up
from app.services.notifications import notify_briefing_failed, run_notification_checks
from app.services.snapshot import business_now
from app.services.whatsapp_client import (
    WhatsAppNotConfiguredError,
    WhatsAppSendError,
    send_text_message,
)

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def _latest_briefing_today(
    db: AsyncSession, company: Company, business_date
) -> MorningBriefing | None:
    """Most recent briefing whose creation falls on the given business-local
    date. created_at is stored in UTC, so it must be converted into the
    company's own timezone before taking .date() — comparing a raw UTC date
    to a business-local date would misfire for far-eastern zones (e.g. an 8am
    briefing in a UTC+13 zone has a UTC date of "yesterday"), causing a
    duplicate briefing. Filtered in Python after ordering — cheap at pilot
    scale (a company has at most a handful of briefings per day).
    """
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


async def _deliver_briefing(db: AsyncSession, company: Company, briefing: MorningBriefing) -> bool:
    """Send an already-generated briefing and record the outcome on the row.
    Returns True on a successful send.
    """
    try:
        result = await send_text_message(company.whatsapp_number, briefing.generated_text)
    except (WhatsAppNotConfiguredError, WhatsAppSendError) as exc:
        logger.warning("Briefing delivery to %s failed: %s", company.whatsapp_number, exc)
        briefing.delivery_status = "failed_to_send"
        return False
    briefing.sent_at = business_now(company.timezone)
    briefing.delivery_status = "sent"
    logger.info("Briefing %s delivered to company %s", briefing.id, company.id)
    return bool(result)


async def _dispatch_for_company(company_id, now: datetime | None) -> None:
    """All time-gated actions for one company, in a fresh session. `now`
    (business-local) is resolved from the company's timezone when not pinned
    by a caller/test.

    Each concern commits independently rather than as one big transaction:
    every branch below performs a real, irreversible WhatsApp send, so its
    durable record (a briefing's delivery_status, a NotificationLog row) must
    be committed before the next concern runs — otherwise a later failure
    would roll back the record of a message that already physically went out,
    breaking the 9am retry decision or causing a duplicate resend next tick.
    """
    settings = get_settings()
    async with async_session_factory() as db:
        company = await db.get(Company, company_id)
        if company is None or not company.subscription_active:
            return
        local_now = now or business_now(company.timezone)
        hour = local_now.hour
        today = local_now.date()

        if hour == settings.briefing_hour:
            existing = await _latest_briefing_today(db, company, today)
            if existing is None:
                briefing = await generate_briefing(db, company.id)
                await _deliver_briefing(db, company, briefing)
                await db.commit()
        elif hour == settings.briefing_retry_hour:
            briefing = await _latest_briefing_today(db, company, today)
            if briefing is not None and briefing.delivery_status == "failed_to_send":
                delivered = await _deliver_briefing(db, company, briefing)
                if not delivered:
                    await notify_briefing_failed(db, company)
                await db.commit()

        if hour == settings.followup_hour:
            await send_due_today_follow_up(db, company.id)
            await db.commit()

        # NotificationEngine only during business hours — the morning briefing
        # hour onward — so a payment that becomes "due tomorrow" at local
        # midnight doesn't fire a real WhatsApp alert at 00:15. Rules dedup
        # internally, so the first daytime tick is when each alert goes out.
        if hour >= settings.briefing_hour:
            await run_notification_checks(db, company.id, now=local_now)
            await db.commit()


async def run_scheduled_tick(now: datetime | None = None) -> None:
    """One poll pass over every subscription-active company. Each company is
    dispatched in its own session/transaction so a single failure is isolated
    and logged, never aborting the rest of the pass. `now` pins business-local
    time for tests; production passes None so each company uses its own zone.
    """
    async with async_session_factory() as db:
        rows = await db.scalars(select(Company.id).where(Company.subscription_active.is_(True)))
        company_ids = list(rows.all())

    for company_id in company_ids:
        try:
            await _dispatch_for_company(company_id, now)
        except Exception:  # noqa: BLE001 - one company's failure must not stop the rest
            logger.exception("Scheduled dispatch failed for company %s", company_id)


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
