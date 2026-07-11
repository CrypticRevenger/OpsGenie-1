"""Invoice PDF delivery to a dealer's WhatsApp — V0.2.

Same layering as app/services/notifications.py: performs its own WhatsApp
send, writes NotificationLog + BusinessEvent, never commits internally (the
caller — app/services/writes/pending_operation.py's create_order branch —
commits once). Called after create_order() has already written the Invoice;
this module never re-derives money or stock, only delivers what was already
computed.

Skips gracefully (returns False, no exception) whenever delivery isn't
possible — a missing dealer phone number or an unconfigured
INVOICE_DOCUMENT_TEMPLATE_NAME must never block the invoice itself from being
created, matching the fail-open convention already used for
founder_whatsapp_number.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.business_event import BusinessEvent, BusinessEventType
from app.models.company import Company
from app.models.notification_log import NotificationLog
from app.services.whatsapp_client import (
    WhatsAppNotConfiguredError,
    WhatsAppSendError,
    send_template_message,
    upload_media,
)
from app.services.writes.orders import CreateOrderResult

logger = logging.getLogger(__name__)

_NOTIFICATION_TYPE = "invoice_document"


async def send_invoice_document(
    db: AsyncSession, company: Company, result: CreateOrderResult, pdf_bytes: bytes
) -> bool:
    """Best-effort: uploads the PDF and sends it via the configured document
    template. Returns whether it was actually sent (False for every skip or
    failure reason — callers only need to know whether to mention it).
    """
    settings = get_settings()
    if not result.dealer_phone:
        logger.info(
            "Invoice %s: dealer %s has no phone on file, skipping PDF delivery.",
            result.invoice_number,
            result.dealer_name,
        )
        return False
    if not settings.invoice_document_template_name:
        logger.info(
            "Invoice %s: INVOICE_DOCUMENT_TEMPLATE_NAME not configured, skipping PDF delivery.",
            result.invoice_number,
        )
        return False

    filename = f"{result.invoice_number}.pdf"
    whatsapp_message_id: str | None = None
    try:
        media_id = await upload_media(pdf_bytes, filename, "application/pdf")
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
        whatsapp_message_id = send_result.message_id
    except (WhatsAppNotConfiguredError, WhatsAppSendError) as exc:
        logger.warning(
            "Invoice %s: PDF delivery to %s failed: %s",
            result.invoice_number,
            result.dealer_phone,
            exc,
        )

    db.add(
        NotificationLog(
            company_id=company.id,
            notification_type=_NOTIFICATION_TYPE,
            recipient_whatsapp=result.dealer_phone,
            message_text=f"Invoice {result.invoice_number} PDF",
            whatsapp_message_id=whatsapp_message_id,
            delivery_status="sent" if whatsapp_message_id else "failed_to_send",
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
                "whatsapp_message_id": whatsapp_message_id,
            },
            created_by="invoice_delivery",
        )
    )
    return whatsapp_message_id is not None
