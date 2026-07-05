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
            # a variable-less template would be rejected by Meta for having a
            # parameter, and vice-versa — the two must match.
            body_params=[company.business_name],
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
    """
    if company.subscription_active:
        return "already_active", False
    company.subscription_active = True
    await db.commit()
    welcome_sent = await send_welcome_template(db, company)
    await db.commit()
    logger.info("Activated subscription for %s (welcome_sent=%s)", company.id, welcome_sent)
    return "activated", welcome_sent
