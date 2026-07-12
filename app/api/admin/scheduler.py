"""Admin scheduler routes — external cron trigger.

APScheduler's interval job (app/core/scheduler.py's start_scheduler) only
ticks while this web process is awake — on a free-tier PaaS that spins the
process down when idle, a company's 8am briefing simply doesn't fire on any
day the process happens to still be asleep at 8am local time; it only
catches up once *something* (an inbound WhatsApp message, a dashboard visit,
a keep-alive ping) wakes the process back up. This endpoint lets an external
scheduler (see .github/workflows/keep-alive.yml) force a tick directly and
regularly, making dispatch timing independent of incidental traffic.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, status

from app.core.scheduler import run_scheduled_tick

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scheduler", tags=["admin:scheduler"])


@router.post(
    "/tick",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Run one scheduled-dispatch tick now (briefings, follow-ups, notifications)",
)
async def trigger_tick() -> dict:
    """Same dispatch APScheduler's interval job runs — per subscription-active
    company, in its own session, acting only when that company's own
    business-local clock currently matches a configured hour. Safe to call
    as often as needed: every branch inside is idempotent/deduplicated
    per company per business day.
    """
    await run_scheduled_tick()
    return {"status": "tick complete"}
