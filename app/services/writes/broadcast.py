"""Marketing broadcast to dealers — guided workflow's terminal write.

Same layering as app/services/invoice_delivery.py (own WhatsApp sends, own
NotificationLog/BusinessEvent audit trail) with one deliberate difference:
this module commits after every recipient's send, not once at the end. A
real WhatsApp send already fired for each prior dealer by the time any
mid-loop failure could happen — without incremental commits, that failure
would roll back the NotificationLog audit rows for sends that already went
out via Meta, leaving no record of what was actually delivered.
expire_on_commit=False (app/db/session.py) makes this safe: already-loaded
ORM objects (company, etc.) stay readable across these commits.

The send loop is synchronous inside one webhook request — this codebase has
no background-task infrastructure — so recipients are capped at
settings.max_broadcast_recipients to bound worst-case request latency.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.business_event import BusinessEvent, BusinessEventType
from app.models.company import Company
from app.models.dealer import Dealer
from app.models.notification_log import NotificationLog
from app.services.snapshot import build_snapshot
from app.services.whatsapp_client import (
    WhatsAppNotConfiguredError,
    WhatsAppSendError,
    send_template_message,
    send_text_message,
)

logger = logging.getLogger(__name__)

_NOTIFICATION_TYPE = "marketing_broadcast"
# A dealer inside their own 24h WhatsApp session window (has messaged the
# business number recently) can be reached with a free-form send, saving a
# template send for everyone else. Meta's own session window is 24h.
SESSION_WINDOW_HOURS = 24


@dataclass(frozen=True)
class BroadcastResult:
    attempted_count: int
    sent_count: int
    failed_count: int


async def resolve_broadcast_recipients(
    db: AsyncSession,
    company_id: uuid.UUID,
    *,
    segment: str,
    dealer_ids: list[uuid.UUID] | None = None,
) -> list[Dealer]:
    """Always filters to marketing_opt_in == True regardless of segment — the
    consent gate is never bypassed by a segment choice.
    """
    if segment == "all":
        stmt = select(Dealer).where(
            Dealer.company_id == company_id, Dealer.marketing_opt_in.is_(True)
        )
    elif segment == "overdue":
        # Reuses the same overdue-risk computation build_dealer_risk_report
        # (app/services/query_menu.py) already shows, rather than re-deriving
        # overdue logic here.
        snapshot = await build_snapshot(db, company_id)
        overdue_ids = {d.dealer_id for d in snapshot.overdue_dealers}
        # .in_(set()) compiles to an always-false clause (no special-casing
        # needed) when nothing is currently overdue.
        stmt = select(Dealer).where(
            Dealer.company_id == company_id,
            Dealer.marketing_opt_in.is_(True),
            Dealer.id.in_(overdue_ids),
        )
    elif segment == "specific":
        stmt = select(Dealer).where(
            Dealer.company_id == company_id,
            Dealer.marketing_opt_in.is_(True),
            Dealer.id.in_(dealer_ids or []),
        )
    else:
        raise ValueError(f"Unknown broadcast segment '{segment}'")
    return list((await db.scalars(stmt)).all())


async def recently_messaged(
    db: AsyncSession, company_id: uuid.UUID, phone: str, since: datetime
) -> bool:
    """Whether this dealer's phone appears as the sender of an inbound
    message within `since` — i.e. still inside WhatsApp's 24h free-form
    session window. Dealer.phone is stored E.164
    (app/services/phone.py::normalize_party_phone) and the webhook's own
    inbound handler normalizes the sender the same way
    (_normalize_to_e164) before writing payload["from"] on the
    whatsapp_message_received BusinessEvent — these compare directly.

    Shared with app/services/notifications.py's dealer-direct-reminder send
    (same free-form-vs-template decision for a dealer proactively messaged
    outside a broadcast) — kept here, not duplicated, since this module
    owns the concept first.
    """
    found = await db.scalar(
        select(BusinessEvent.id).where(
            BusinessEvent.company_id == company_id,
            BusinessEvent.event_type == BusinessEventType.whatsapp_message_received,
            BusinessEvent.payload["from"].astext == phone,
            BusinessEvent.created_at >= since,
        )
    )
    return found is not None


async def send_broadcast(
    db: AsyncSession,
    company: Company,
    *,
    segment: str,
    dealer_ids: list[uuid.UUID],
    message: str,
) -> BroadcastResult:
    settings = get_settings()
    dealers = await resolve_broadcast_recipients(
        db, company.id, segment=segment, dealer_ids=dealer_ids
    )
    dealers = [d for d in dealers if d.phone][: settings.max_broadcast_recipients]
    since = datetime.now(UTC) - timedelta(hours=SESSION_WINDOW_HOURS)

    sent = 0
    failed = 0
    for dealer in dealers:
        message_id: str | None = None
        try:
            if await recently_messaged(db, company.id, dealer.phone, since):
                result = await send_text_message(dealer.phone, message)
            elif not settings.broadcast_template_name:
                raise WhatsAppNotConfiguredError("BROADCAST_TEMPLATE_NAME not configured")
            else:
                result = await send_template_message(
                    dealer.phone,
                    settings.broadcast_template_name,
                    settings.broadcast_template_language,
                    body_params=[message],
                )
            message_id = result.message_id
            sent += 1
        except (WhatsAppNotConfiguredError, WhatsAppSendError) as exc:
            logger.warning(
                "Broadcast send to dealer %s (%s) failed: %s", dealer.id, dealer.phone, exc
            )
            failed += 1

        db.add(
            NotificationLog(
                company_id=company.id,
                notification_type=_NOTIFICATION_TYPE,
                recipient_whatsapp=dealer.phone,
                message_text=message,
                whatsapp_message_id=message_id,
                delivery_status="sent" if message_id else "failed_to_send",
            )
        )
        # Commit per-dealer, not once at the end — see module docstring.
        await db.commit()

    db.add(
        BusinessEvent(
            company_id=company.id,
            event_type=BusinessEventType.marketing_broadcast_sent,
            entity_type="company",
            entity_id=company.id,
            payload={"segment": segment, "attempted": len(dealers), "sent": sent, "failed": failed},
            created_by="broadcast",
        )
    )
    await db.commit()
    return BroadcastResult(attempted_count=len(dealers), sent_count=sent, failed_count=failed)


async def bulk_opt_in_all_dealers(db: AsyncSession, company: Company) -> int:
    """Single bulk UPDATE — no payload inputs that could go stale, so this
    trivially satisfies the "re-derive fresh at confirm time" rule every
    PendingOperation branch follows.
    """
    result = await db.execute(
        update(Dealer)
        .where(Dealer.company_id == company.id, Dealer.marketing_opt_in.is_(False))
        .values(marketing_opt_in=True)
    )
    return result.rowcount
