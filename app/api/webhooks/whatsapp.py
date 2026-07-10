"""WhatsApp inbound webhook — Phase 7 (SPEC.md V0.1 Step 11) + Phase 8
(SPEC.md V0.1 Step 12).

Not under /admin — Meta calls this endpoint directly and cannot send an
X-API-Key header. It has its own two independent security mechanisms
instead: the GET handshake's hub.verify_token, and the POST body's
X-Hub-Signature-256 HMAC.

Scope: verify the endpoint, parse Meta's payload, match the sender/recipient
to a Company, durably log every inbound message/status as a BusinessEvent,
and reply to (in priority order): guided onboarding, if the company hasn't
finished setup; else (Phase 2A) an active guided write workflow (e.g.
recording a payment), if one is in progress; else a pending write
confirmation ("YES"/"NO" awaiting an invoice/payment preview), if one
exists; else (Phase 9) a pending invoice due-date follow-up conversation, if
one is active; else (Phase 8) a numbered-menu command ("1"-"4", via
app.services.query_menu's CommandRouter); else a plain keyword that starts a
guided write workflow (e.g. "record payment"); else the free-form LLM
assistant (app.services.assistant), which answers natural-language questions
from real figures and never performs a write itself. Onboarding outranks
everything (mid-setup a "1" is an answer, not "Cash Position"); an active
write workflow and a pending confirmation both outrank the follow-up/menu
checks for the same reason the follow-up check already outranked the menu —
a bare "1"/"2"/"10" mid-flow answers the current question, not a menu
command or a follow-up reply. Every outbound reply is
traceable end-to-end: the inbound BusinessEvent's id becomes a
`correlation_id` carried on the outbound whatsapp_reply_sent BusinessEvent
and on the NotificationLog row, and Meta's own returned message id (the
"wamid") links that NotificationLog row forward to whichever later
whatsapp_status_received delivery-status webhook updates it.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db
from app.models.business_event import BusinessEvent, BusinessEventType
from app.models.company import Company, OnboardingState
from app.models.notification_log import NotificationLog
from app.services.assistant import ASSISTANT_NOTIFICATION_TYPE, answer_question
from app.services.followup import handle_follow_up_reply
from app.services.onboarding_flow import handle_onboarding_message
from app.services.query_menu import menu_router
from app.services.snapshot import build_snapshot
from app.services.whatsapp_client import (
    WhatsAppNotConfiguredError,
    WhatsAppSendError,
    WhatsAppSendResult,
    send_text_message,
)
from app.services.workflows.order_flow import (
    handle_order_workflow_message,
    start_order_workflow,
)
from app.services.workflows.payment_flow import (
    handle_payment_workflow_message,
    start_payment_workflow,
)
from app.services.workflows.product_flow import (
    handle_add_product_workflow_message,
    handle_delete_product_workflow_message,
    handle_update_price_workflow_message,
    start_add_product_workflow,
    start_delete_product_workflow,
    start_update_price_workflow,
)
from app.services.writes.pending_operation import (
    get_pending_operation,
    handle_pending_operation_reply,
)

# Phase 2A — registry of active workflow types -> their per-message handler.
# Company.active_workflow is a plain string precisely so new workflow types
# (Phase 2B's create_invoice, etc.) register here without a migration — see
# app/models/company.py's active_workflow docstring.
_WORKFLOW_HANDLERS: dict[str, Callable[[AsyncSession, Company, str], Awaitable[str]]] = {
    "record_payment": handle_payment_workflow_message,
    "create_order": handle_order_workflow_message,
    "add_product": handle_add_product_workflow_message,
    "delete_product": handle_delete_product_workflow_message,
    "update_price": handle_update_price_workflow_message,
}

# Registry: exact-match keyword -> starter that sets active_workflow and
# returns the flow's first question verbatim. Deterministic trigger,
# deliberately not agent tool-calling (see deployment.md's Phase 2A scope
# note): a tool's reply would flow through LLM narration, which can't
# guarantee the flow's exact question wording. Same deterministic spirit as
# menu_router — no fuzzy NLP, and a new workflow's triggers are just more
# entries here, not a new elif branch.
_WORKFLOW_START_TRIGGERS: dict[str, Callable[[Company], str]] = {
    "record payment": start_payment_workflow,
    "record a payment": start_payment_workflow,
    "log payment": start_payment_workflow,
    "payment received": start_payment_workflow,
    "new order": start_order_workflow,
    "create order": start_order_workflow,
    "place order": start_order_workflow,
    "record order": start_order_workflow,
    "add product": start_add_product_workflow,
    "add products": start_add_product_workflow,
    "add a product": start_add_product_workflow,
    "new product": start_add_product_workflow,
    "add item": start_add_product_workflow,
    "add items": start_add_product_workflow,
    "delete product": start_delete_product_workflow,
    "delete products": start_delete_product_workflow,
    "delete a product": start_delete_product_workflow,
    "remove product": start_delete_product_workflow,
    "remove products": start_delete_product_workflow,
    "delete item": start_delete_product_workflow,
    "remove item": start_delete_product_workflow,
    "update price": start_update_price_workflow,
    "update product price": start_update_price_workflow,
    "change price": start_update_price_workflow,
    "change product price": start_update_price_workflow,
    "edit price": start_update_price_workflow,
    "edit product price": start_update_price_workflow,
}

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["webhooks:whatsapp"])


def _normalize_to_e164(phone: str) -> str:
    """Meta sends sender/recipient numbers without a leading '+'."""
    phone = phone.strip()
    if phone and not phone.startswith("+"):
        phone = "+" + phone
    return phone


def _verify_signature(raw_body: bytes, signature_header: str | None, app_secret: str) -> bool:
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    provided = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, provided)


def _extract_text_body(message: dict) -> str:
    """Only 'text' messages have a unified body field. Other types (image,
    audio, document, button, interactive, location) are logged with `type`
    set and an empty body — parsing their specific shapes is out of scope
    until a later phase needs to act on them.
    """
    if message.get("type") == "text":
        return message.get("text", {}).get("body", "")
    return ""


async def _find_company_by_whatsapp_number(
    db: AsyncSession, whatsapp_number: str
) -> Company | None:
    return await db.scalar(select(Company).where(Company.whatsapp_number == whatsapp_number))


async def _already_processed(db: AsyncSession, company: Company, message_id: str | None) -> bool:
    """Meta's webhook delivery is at-least-once and retries aggressively on
    slow/non-2xx responses — without this check, a redelivered message would
    be re-parsed and (for a menu command) re-sent as a duplicate WhatsApp
    reply. Dedup against the whatsapp_message_received event already written
    for this exact Meta message id.
    """
    if not message_id:
        return False
    existing = await db.scalar(
        select(BusinessEvent.id).where(
            BusinessEvent.company_id == company.id,
            BusinessEvent.event_type == BusinessEventType.whatsapp_message_received,
            BusinessEvent.payload["message_id"].astext == message_id,
        )
    )
    return existing is not None


async def _record_message_event(db: AsyncSession, company: Company, message: dict) -> BusinessEvent:
    event = BusinessEvent(
        company_id=company.id,
        event_type=BusinessEventType.whatsapp_message_received,
        entity_type="company",
        entity_id=company.id,
        payload={
            "from": _normalize_to_e164(message.get("from", "")),
            "message_id": message.get("id"),
            "type": message.get("type"),
            "text": _extract_text_body(message),
            "timestamp": message.get("timestamp"),
        },
        created_by="whatsapp_webhook",
    )
    db.add(event)
    return event


async def _record_status_event(db: AsyncSession, company: Company, status_entry: dict) -> None:
    db.add(
        BusinessEvent(
            company_id=company.id,
            event_type=BusinessEventType.whatsapp_status_received,
            entity_type="company",
            entity_id=company.id,
            payload={
                "message_id": status_entry.get("id"),
                "status": status_entry.get("status"),
                "recipient": _normalize_to_e164(status_entry.get("recipient_id", "")),
                "timestamp": status_entry.get("timestamp"),
            },
            created_by="whatsapp_webhook",
        )
    )


async def _update_notification_delivery_status(db: AsyncSession, status_entry: dict) -> None:
    """Closes the trace loop: a status webhook's `id` is the same "wamid"
    send_text_message() returned when the reply was sent — match it back to
    the NotificationLog row that recorded that send.
    """
    message_id = status_entry.get("id")
    new_status = status_entry.get("status")
    if not message_id or not new_status:
        return
    log = await db.scalar(
        select(NotificationLog).where(NotificationLog.whatsapp_message_id == message_id)
    )
    if log is not None:
        log.delivery_status = new_status


async def _record_reply_sent_event(
    db: AsyncSession,
    company: Company,
    *,
    correlation_id: uuid.UUID,
    notification_log_id: uuid.UUID,
    whatsapp_message_id: str | None,
    command: str | None,
) -> None:
    db.add(
        BusinessEvent(
            company_id=company.id,
            event_type=BusinessEventType.whatsapp_reply_sent,
            entity_type="company",
            entity_id=company.id,
            payload={
                "correlation_id": str(correlation_id),
                "notification_log_id": str(notification_log_id),
                "whatsapp_message_id": whatsapp_message_id,
                "command": command,
            },
            created_by="whatsapp_webhook",
        )
    )


async def _send_reply_and_log(
    db: AsyncSession,
    company: Company,
    recipient: str,
    *,
    notification_type: str,
    reply: str,
    command: str | None,
    correlation_id: uuid.UUID,
) -> None:
    """Send `reply` over WhatsApp (best-effort — a failed or unconfigured send
    is logged, never raised, so the inbound webhook still 200s to Meta) and
    durably record the attempt: a NotificationLog row keyed by Meta's message
    id, plus a whatsapp_reply_sent BusinessEvent carrying `correlation_id`
    back to the inbound message that triggered this reply.
    """
    send_result: WhatsAppSendResult | None
    try:
        send_result = await send_text_message(recipient, reply)
    except (WhatsAppNotConfiguredError, WhatsAppSendError) as exc:
        logger.warning("WhatsApp reply to %s not sent: %s", recipient, exc)
        send_result = None

    log = NotificationLog(
        company_id=company.id,
        notification_type=notification_type,
        recipient_whatsapp=recipient,
        message_text=reply,
        whatsapp_message_id=send_result.message_id if send_result else None,
        delivery_status="sent" if send_result else "failed_to_send",
    )
    db.add(log)
    # log.id is a Python-side default (uuid.uuid4) applied at flush time, not
    # at construction — flush explicitly so it's populated before we embed it
    # in the BusinessEvent payload below.
    await db.flush()

    await _record_reply_sent_event(
        db,
        company,
        correlation_id=correlation_id,
        notification_log_id=log.id,
        whatsapp_message_id=send_result.message_id if send_result else None,
        command=command,
    )


@router.get(
    "",
    summary="Meta webhook verification handshake",
    response_class=PlainTextResponse,
)
async def verify_whatsapp_webhook(
    hub_mode: str | None = Query(None, alias="hub.mode"),
    hub_verify_token: str | None = Query(None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(None, alias="hub.challenge"),
) -> PlainTextResponse:
    settings = get_settings()
    token_ok = bool(settings.whatsapp_verify_token) and hmac.compare_digest(
        hub_verify_token or "", settings.whatsapp_verify_token or ""
    )
    if hub_mode == "subscribe" and token_ok and hub_challenge is not None:
        return PlainTextResponse(hub_challenge, status_code=status.HTTP_200_OK)
    logger.warning("WhatsApp webhook verification failed (mode=%r).", hub_mode)
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Verification failed.")


@router.post("", summary="Receive inbound WhatsApp messages and status updates")
async def receive_whatsapp_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    settings = get_settings()
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")

    if not settings.whatsapp_app_secret or not _verify_signature(
        raw_body, signature, settings.whatsapp_app_secret
    ):
        logger.warning("WhatsApp webhook signature verification failed.")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid signature.")

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed JSON body."
        ) from exc

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})

            for message in value.get("messages", []):
                sender = _normalize_to_e164(message.get("from", ""))
                company = await _find_company_by_whatsapp_number(db, sender)
                if company is None:
                    logger.warning("WhatsApp message from unknown sender %s — skipping.", sender)
                    continue
                if await _already_processed(db, company, message.get("id")):
                    logger.info(
                        "WhatsApp message %s already processed — skipping redelivery.",
                        message.get("id"),
                    )
                    continue
                inbound_event = await _record_message_event(db, company, message)
                # inbound_event.id is a Python-side default applied at flush
                # time — flush now so it's populated before use as a
                # correlation_id below, regardless of which branch follows.
                await db.flush()

                # The agent only responds for companies whose subscription is
                # active. Onboarded-but-not-yet-activated numbers are logged
                # (above) but get no reply — the subscription is what "turns on
                # the agent" for them.
                if not company.subscription_active:
                    logger.info(
                        "Inbound from %s but subscription inactive — logged, not responding.",
                        sender,
                    )
                    continue

                if message.get("type") == "text":
                    text = _extract_text_body(message)
                    command: str | None = None
                    if company.onboarding_state != OnboardingState.completed:
                        # Guided setup outranks everything else — mid-onboarding
                        # a "1" is an answer to the current question, not the
                        # "Cash Position" menu command.
                        notification_type = "onboarding"
                        reply = await handle_onboarding_message(db, company, text)
                    elif company.active_workflow is not None:
                        # A guided write workflow (Phase 2A) outranks the menu
                        # and the follow-up for the same reason follow-up
                        # already did — mid-flow, a bare "10" is the quantity/
                        # amount answer, not a menu command. Dispatch by the
                        # workflow's own value (not just its presence) so a
                        # second workflow type (Phase 2B) can register its own
                        # handler without this branch needing to change.
                        workflow_handler = _WORKFLOW_HANDLERS.get(company.active_workflow)
                        if workflow_handler is not None:
                            notification_type = "write_workflow"
                            reply = await workflow_handler(db, company, text)
                        else:
                            # An active_workflow value nothing registers a
                            # handler for (shouldn't happen) — never leave the
                            # company stuck on a workflow this code can't run.
                            company.active_workflow = None
                            company.workflow_scratch = None
                            notification_type = "write_workflow_error"
                            reply = "Something went wrong. Please try again."
                    elif company.active_pending_operation_id is not None:
                        # In-memory pointer check (no query) — mirrors
                        # pending_follow_up_invoice_id below, so companies
                        # that never use a guided write workflow pay zero
                        # extra cost on every message.
                        pending_op = await get_pending_operation(
                            db, company.active_pending_operation_id
                        )
                        if pending_op is None:
                            # Pointer stale (shouldn't happen — every deletion
                            # path clears it in the same transaction).
                            company.active_pending_operation_id = None
                            notification_type = "pending_operation_missing"
                            reply = "Something went wrong with that. Please try again."
                        elif pending_op.expires_at < datetime.now(UTC):
                            await db.delete(pending_op)
                            company.active_pending_operation_id = None
                            notification_type = "pending_operation_expired"
                            reply = "That confirmation expired. Please start again."
                        else:
                            notification_type = "pending_operation_confirm"
                            reply = await handle_pending_operation_reply(
                                db, company, pending_op, text
                            )
                    elif company.pending_follow_up_invoice_id is not None:
                        # A pending follow-up takes priority over the numbered
                        # menu — "1"/"2"/"3" here answers the follow-up
                        # question, not "Cash Position".
                        notification_type = "follow_up_reply"
                        reply = await handle_follow_up_reply(db, company, text)
                    else:
                        command = menu_router.match(text)
                        if command is not None:
                            # 1-4 stay instant deterministic shortcuts.
                            snapshot = await build_snapshot(db, company.id)
                            result = menu_router.execute(command, snapshot)
                            notification_type, reply = result.notification_type, result.reply
                        elif (
                            starter := _WORKFLOW_START_TRIGGERS.get(text.strip().lower())
                        ) is not None:
                            # Deterministic keyword trigger — works without AI,
                            # per Phase 2A's scope (see module docstring).
                            command = text.strip().lower()
                            notification_type = "write_workflow"
                            reply = starter(company)
                        else:
                            # Anything else -> the grounded LLM assistant, which
                            # answers free-form questions from real figures and
                            # never forwards an unverifiable number.
                            notification_type = ASSISTANT_NOTIFICATION_TYPE
                            reply = await answer_question(db, company, text)
                    await _send_reply_and_log(
                        db,
                        company,
                        sender,
                        notification_type=notification_type,
                        reply=reply,
                        command=command,
                        correlation_id=inbound_event.id,
                    )

            for status_entry in value.get("statuses", []):
                recipient = _normalize_to_e164(status_entry.get("recipient_id", ""))
                company = await _find_company_by_whatsapp_number(db, recipient)
                if company is None:
                    logger.warning(
                        "WhatsApp status for unknown recipient %s — skipping.", recipient
                    )
                    continue
                await _record_status_event(db, company, status_entry)
                await _update_notification_delivery_status(db, status_entry)

    # Always 200 once signature-checked and structurally valid — Meta retries
    # aggressively on non-2xx. Per-message lookup misses are logged, not
    # surfaced as HTTP errors.
    await db.commit()
    return {"status": "received"}
