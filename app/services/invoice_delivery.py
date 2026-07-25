"""Invoice PDF delivery to a dealer's WhatsApp — V0.2.

Same layering as app/services/notifications.py: performs its own WhatsApp
send, writes NotificationLog + BusinessEvent, never commits internally (the
caller — app/services/writes/pending_operation.py's create_order branch —
commits once). Called after create_order() has already written the Invoice;
this module never re-derives money or stock, only delivers what was already
computed.

Never blocks invoice creation: every failure mode below degrades to a
friendly "not sent" note rather than an exception. The PDF always goes to
the founder's own chat (company.whatsapp_number, the number this whole
conversation is already happening on, safely inside its own session window)
— by explicit request, not just as a fallback — and, independently,
*additionally* to the dealer directly whenever they have a phone on file and
INVOICE_DOCUMENT_TEMPLATE_NAME is configured. (Earlier behavior sent the
founder a copy only when the dealer send failed/wasn't possible; the founder
now always gets one regardless, so they have a copy of every invoice even
when the dealer is also reachable.) Only a total upload failure (WhatsApp
not configured at all) leaves nobody with the PDF.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.business_event import BusinessEvent, BusinessEventType
from app.models.company import Company
from app.models.notification_log import NotificationLog
from app.services.whatsapp_client import (
    WhatsAppNotConfiguredError,
    WhatsAppSendError,
    send_document_message,
    send_template_message,
    upload_media,
)
from app.services.writes.orders import CreateOrderResult

logger = logging.getLogger(__name__)

_NOTIFICATION_TYPE = "invoice_document"
# Historical name/value kept as-is (predates the always-send-to-founder
# change) — NotificationLog rows already use this string, and nothing about
# founder delivery becoming unconditional changes what a "founder copy of
# this invoice" log entry means.
_FOUNDER_NOTIFICATION_TYPE = "invoice_document_founder_fallback"


@dataclass(frozen=True)
class InvoiceDeliveryResult:
    """Which recipient(s) actually received the PDF. Both can be True (the
    common case — founder always gets a copy, dealer gets one too when
    reachable) or both False (the PDF upload itself failed).
    pending_operation.py words the confirmation reply differently for each
    combination.
    """

    sent_to_dealer: bool
    sent_to_founder: bool


async def send_invoice_document(
    db: AsyncSession, company: Company, result: CreateOrderResult, pdf_bytes: bytes
) -> InvoiceDeliveryResult:
    """Upload the PDF once, then attempt both deliveries independently: the
    dealer's document template (only when reachable) and the founder's own
    chat (always) — neither attempt's outcome gates the other.
    """
    settings = get_settings()
    filename = f"{result.invoice_number}.pdf"

    try:
        media_id = await upload_media(pdf_bytes, filename, "application/pdf")
    except (WhatsAppNotConfiguredError, WhatsAppSendError) as exc:
        logger.warning(
            "Invoice %s: PDF upload failed, cannot deliver anywhere: %s",
            result.invoice_number,
            exc,
        )
        return InvoiceDeliveryResult(sent_to_dealer=False, sent_to_founder=False)

    dealer_message_id: str | None = None
    if not result.dealer_phone:
        logger.info(
            "Invoice %s: dealer %s has no phone on file, skipping direct PDF delivery.",
            result.invoice_number,
            result.dealer_name,
        )
    elif not settings.invoice_document_template_name:
        logger.info(
            "Invoice %s: INVOICE_DOCUMENT_TEMPLATE_NAME not configured, skipping direct "
            "PDF delivery.",
            result.invoice_number,
        )
    else:
        try:
            send_result = await send_template_message(
                result.dealer_phone,
                settings.invoice_document_template_name,
                settings.invoice_document_template_language,
                body_params=[
                    result.invoice_number,
                    str(result.total_amount),
                    result.due_date.isoformat(),
                ],
                header_media_id=media_id,
                header_filename=filename,
            )
            dealer_message_id = send_result.message_id
        except (WhatsAppNotConfiguredError, WhatsAppSendError) as exc:
            logger.warning(
                "Invoice %s: PDF delivery to %s failed: %s",
                result.invoice_number,
                result.dealer_phone,
                exc,
            )

    if result.dealer_phone:
        # recipient_whatsapp is NOT NULL — with no phone on file there's no
        # recipient identity to log an attempt against, so this row is only
        # written when one actually exists (whether the send then succeeded,
        # failed, or was skipped for a missing template).
        db.add(
            NotificationLog(
                company_id=company.id,
                notification_type=_NOTIFICATION_TYPE,
                recipient_whatsapp=result.dealer_phone,
                message_text=f"Invoice {result.invoice_number} PDF",
                whatsapp_message_id=dealer_message_id,
                delivery_status="sent" if dealer_message_id else "failed_to_send",
            )
        )
    db.add(
        BusinessEvent(
            company_id=company.id,
            event_type=BusinessEventType.invoice_document_sent,
            entity_type="invoice",
            entity_id=result.invoice_id,
            payload={
                "dealer_id": str(result.dealer_id),
                "whatsapp_message_id": dealer_message_id,
            },
            created_by="invoice_delivery",
        )
    )

    # Always attempted, independent of whether the dealer send above
    # succeeded — the founder gets their own copy of every invoice either
    # way, not only when the dealer couldn't be reached.
    founder_message_id: str | None = None
    caption = f"Invoice {result.invoice_number} for {result.dealer_name}"
    if not dealer_message_id:
        caption += " — couldn't reach them directly, please forward this to them."
    try:
        send_result = await send_document_message(
            company.whatsapp_number,
            media_id,
            filename,
            caption=caption,
        )
        founder_message_id = send_result.message_id
    except (WhatsAppNotConfiguredError, WhatsAppSendError) as exc:
        logger.warning(
            "Invoice %s: founder PDF delivery failed: %s",
            result.invoice_number,
            exc,
        )

    db.add(
        NotificationLog(
            company_id=company.id,
            notification_type=_FOUNDER_NOTIFICATION_TYPE,
            recipient_whatsapp=company.whatsapp_number,
            message_text=f"Invoice {result.invoice_number} PDF (founder copy)",
            whatsapp_message_id=founder_message_id,
            delivery_status="sent" if founder_message_id else "failed_to_send",
        )
    )
    return InvoiceDeliveryResult(
        sent_to_dealer=bool(dealer_message_id), sent_to_founder=bool(founder_message_id)
    )
