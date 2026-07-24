"""Shared subscription-activation logic.

Used by the founder-only admin endpoint (app/api/admin/companies.py's
activate-subscription) and the public self-serve /onboard wizard's final step
(app/api/onboarding.py). Extracting this means the public route can't drift
from the admin route's commit-then-best-effort-send choreography: the
activation flag is committed first (that's the durable, important part), then
the welcome template is sent best-effort in a second transaction — a commit
failure after a successful send can't leave the flag False (which would
re-send the welcome on retry), since a retry sees subscription_active=True
and no-ops.
"""

from __future__ import annotations

import logging

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.company import Company
from app.models.notification_log import NotificationLog
from app.services.whatsapp_client import (
    WhatsAppNotConfiguredError,
    WhatsAppSendError,
    send_template_message,
)

logger = logging.getLogger(__name__)


async def send_welcome_template(db: AsyncSession, company: Company) -> bool:
    """Send the approved welcome template to a newly-activated company and log
    it. Fail-open like every other send — a missing template or a Meta error
    is logged, never raised, so activation still succeeds. Returns whether the
    welcome actually went out.
    """
    settings = get_settings()
    if not settings.welcome_template_name:
        logger.info("Welcome not sent to %s — WELCOME_TEMPLATE_NAME unset.", company.id)
        return False
    send_result = None
    try:
        send_result = await send_template_message(
            company.whatsapp_number,
            settings.welcome_template_name,
            settings.welcome_template_language,
            # Fills the template's {{1}} body variable. The approved
            # `opsgenie_welcome` template must have exactly one body variable;
            # a variable-less template (e.g. Meta's stock "hello_world" sample,
            # used as a stand-in while opsgenie_welcome is pending approval)
            # must get body_params=None — sending a parameter to a template
            # that declares none is rejected by Meta, and vice-versa.
            body_params=[company.business_name] if settings.welcome_template_has_variable else None,
        )
    except (WhatsAppNotConfiguredError, WhatsAppSendError) as exc:
        logger.warning("Welcome template to %s not sent: %s", company.whatsapp_number, exc)
    db.add(
        NotificationLog(
            company_id=company.id,
            notification_type="welcome",
            recipient_whatsapp=company.whatsapp_number,
            message_text=f"welcome template: {settings.welcome_template_name}",
            whatsapp_message_id=send_result.message_id if send_result else None,
            delivery_status="sent" if send_result else "failed_to_send",
        )
    )
    return send_result is not None


async def activate_company(db: AsyncSession, company: Company) -> tuple[str, bool]:
    """Flip a company's subscription live and send its welcome template.

    Idempotent: a company that's already active is left alone and the welcome
    is not re-sent. Returns (status, welcome_sent) where status is
    "already_active" or "activated".

    The activation flip itself is claimed atomically — a plain "read
    company.subscription_active, then decide, then write" here has the same
    race shape as the evening brief's 3x-send bug (see
    app/services/evening_brief.py::send_evening_brief): two overlapping
    callers (a founder double-tapping "Activate" in the admin dashboard
    before the page updates, or a retried request after a slow response —
    both admin/companies.py's activate-subscription route and the public
    /onboard wizard's final step call this same function, neither behind any
    lock) could both read subscription_active=False, both flip it True, and
    both send a real duplicate welcome template. The conditional UPDATE
    (WHERE subscription_active IS FALSE) makes only one of them actually
    flip the row — Postgres's row lock serializes the two attempts, so the
    loser's UPDATE simply matches zero rows once the winner commits.
    """
    claim = await db.execute(
        update(Company)
        .where(Company.id == company.id, Company.subscription_active.is_(False))
        .values(subscription_active=True)
    )
    if claim.rowcount == 0:
        return "already_active", False
    company.subscription_active = True
    await db.commit()
    welcome_sent = await send_welcome_template(db, company)
    await db.commit()
    logger.info("Activated subscription for %s (welcome_sent=%s)", company.id, welcome_sent)
    return "activated", welcome_sent
