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
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import async_session_factory, get_db
from app.models.business_event import BusinessEvent, BusinessEventType
from app.models.company import Company, OnboardingState
from app.models.dealer import Dealer
from app.models.invoice import Invoice
from app.models.notification_log import NotificationLog
from app.models.supplier import Supplier
from app.services.assistant import ASSISTANT_NOTIFICATION_TYPE, answer_question
from app.services.briefing import generate_briefing, latest_briefing_today
from app.services.company_export import generate_export_link
from app.services.followup import handle_follow_up_reply
from app.services.money_format import format_inr
from app.services.onboarding_flow import handle_onboarding_message
from app.services.query_menu import menu_router
from app.services.snapshot import build_snapshot, business_now
from app.services.whatsapp_client import (
    WhatsAppNotConfiguredError,
    WhatsAppSendError,
    WhatsAppSendResult,
    send_interactive_list_message,
    send_text_message,
)
from app.services.workflows.gst_flow import (
    handle_update_gst_workflow_message,
    start_update_gst_workflow,
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
    handle_update_product_workflow_message,
    start_add_product_workflow,
    start_delete_product_workflow,
    start_update_price_workflow,
    start_update_product_workflow,
    start_update_purchase_price_workflow,
    start_update_stock_workflow,
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
    "update_product": handle_update_product_workflow_message,
    "update_gst": handle_update_gst_workflow_message,
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
    # V0.2 — SPEC.md's Conversation 4 calls this "invoice creation"; it's the
    # exact same flow/handler as "create order" above (both produce a real
    # Invoice row), just an alias for the phrasing distributors may use.
    "create invoice": start_order_workflow,
    "new invoice": start_order_workflow,
    "raise invoice": start_order_workflow,
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
    "update product": start_update_product_workflow,
    "edit product": start_update_product_workflow,
    "update price": start_update_price_workflow,
    "update product price": start_update_price_workflow,
    "change price": start_update_price_workflow,
    "change product price": start_update_price_workflow,
    "edit price": start_update_price_workflow,
    "edit product price": start_update_price_workflow,
    "update purchase price": start_update_purchase_price_workflow,
    "update cost price": start_update_purchase_price_workflow,
    "change purchase price": start_update_purchase_price_workflow,
    "change cost price": start_update_purchase_price_workflow,
    "edit purchase price": start_update_purchase_price_workflow,
    "edit cost price": start_update_purchase_price_workflow,
    "update stock": start_update_stock_workflow,
    "update product stock": start_update_stock_workflow,
    "change stock": start_update_stock_workflow,
    "edit stock": start_update_stock_workflow,
    "restock": start_update_stock_workflow,
    "update quantity": start_update_stock_workflow,
    "update gst": start_update_gst_workflow,
    "update gst rate": start_update_gst_workflow,
    "change gst": start_update_gst_workflow,
    "edit gst": start_update_gst_workflow,
    # Slash-command shortcuts — same handlers as the phrases above, just a
    # fixed, guessable form so a user can lean on /help's list instead of
    # having to phrase the request naturally.
    "/record_payment": start_payment_workflow,
    "/create_order": start_order_workflow,
    "/new_invoice": start_order_workflow,
    "/add_product": start_add_product_workflow,
    "/delete_product": start_delete_product_workflow,
    "/update_product": start_update_product_workflow,
    "/update_price": start_update_price_workflow,
    "/update_purchase_price": start_update_purchase_price_workflow,
    "/update_stock": start_update_stock_workflow,
    "/update_gst": start_update_gst_workflow,
}


async def _export_link_reply(db: AsyncSession, company: Company) -> str:
    """Stateless — a brand-new short-lived signed link every time this is
    asked, never a reused one. See app/services/company_export.py.
    """
    settings = get_settings()
    if not settings.export_link_secret or not settings.public_base_url:
        return (
            "The data export link isn't set up yet — ask your OpsGenie admin "
            "to configure it."
        )
    link = generate_export_link(company, base_url=settings.public_base_url)
    ttl = settings.export_link_ttl_minutes
    return f"Your latest Excel export is ready.\nDownload (valid {ttl} min): {link}"


_HELP_TEXT = """*OpsGenie Help*

*Cash & Overview*
• cash / cash position — current cash, 7-day expected in/out, net position (or reply 1 / /cash)
• summary / business summary — cash, net position, 7-day collections/payments, overdue dealers
• priorities / what should I do — ranked actions: cash warnings, dealers to call, supplier dues

*Dealers (they owe you)*
• dealers / all dealers — every dealer with phone & outstanding
• top debtors / who owes most — dealers with the largest outstanding
• overdue / overdue dealers — days overdue & risk level (or reply 4 / /dealer_risk)
• balance <name> — outstanding for one dealer, e.g. balance Ram Traders

*Suppliers (you owe them)*
• suppliers / all suppliers — every supplier with phone & outstanding
• top creditors — suppliers you owe the most
• balance <name> — outstanding for one supplier

*Upcoming Cash Flow*
• collections / upcoming collections — expected from dealers, next 7 days (or 2 / /collections)
• payments / upcoming payments — owed to suppliers in the next 7 days (or reply 3 / /suppliers)

*Inventory*
• inventory / products / stock — full product catalogue (stock qty, selling price)
• stock <product> — check a specific item, e.g. stock Rice

*Transactions*
• invoices / recent invoices — latest invoices (number, party, total, status, dates)
• payments / recent payments — latest payments recorded
• faq / policy — your saved business policy answers (delivery days, returns, minimum order)

*Manage Products* (guided, one question at a time)
• add product (or /add_product) — add a new item: name, stock, unit, selling price, purchase price
• update stock (or /update_stock) — change a product's stock quantity
• update price (or /update_price) — change a product's selling price
• update purchase price (or /update_purchase_price) — change what you pay your supplier
• update product (or /update_product) — pick price, purchase price, or stock to update
• update gst (or /update_gst) — change GST for all products, or one specific product
• delete product (or /delete_product) — remove a catalogue item

*Orders & Payments*
• new order (or /create_order, or "new invoice") — record a sale to a dealer, product by product
• record payment (or /record_payment) — log a payment received from a dealer or paid to a supplier

*Your Data*
• export data (or /export_data) — a download link to your full business data as Excel
• morning briefing (or /morning_briefing) — resend today's briefing

*Quick Access*
• menu — tap through your options instead of typing
• help (or /help) — see this list again anytime"""


async def _help_reply(db: AsyncSession, company: Company) -> str:
    return _HELP_TEXT


# "menu" sends tappable WhatsApp list messages instead of plain text — every
# zero-argument capability in _HELP_TEXT, split across 3 messages since Meta
# caps a single list at 10 rows total. (balance <name> / stock <product>
# need a typed argument, so they can't be a fixed tappable row — they stay
# type-to-use, per _HELP_TEXT.) Row ids are read back exactly like typed text
# (see _extract_text_body), so each one is either an existing /slash_command
# or a bare keyword the free-form assistant (app/services/assistant.py)
# already understands.
_MENU_TRIGGERS = ("menu", "/menu")
_MENU_FALLBACK_TEXT = "Tap an option below, or reply /help for the full list."
_MENU_MESSAGES: list[dict] = [
    {
        "body": "Reports & Overview — tap one:",
        "button_text": "Choose a report",
        "sections": [
            {
                "title": "Cash & Overview",
                "rows": [
                    {
                        "id": "cash",
                        "title": "Cash Position",
                        "description": "Current cash & 7-day in/out",
                    },
                    {
                        "id": "summary",
                        "title": "Business Summary",
                        "description": "Overall snapshot",
                    },
                    {
                        "id": "priorities",
                        "title": "Priorities",
                        "description": "What should I do today",
                    },
                ],
            },
            {
                "title": "Money Flow",
                "rows": [
                    {
                        "id": "overdue",
                        "title": "Overdue Dealers",
                        "description": "Days overdue & risk level",
                    },
                    {
                        "id": "upcoming collections",
                        "title": "Collections Due",
                        "description": "Expected in next 7 days",
                    },
                    {
                        "id": "upcoming payments",
                        "title": "Payments Due",
                        "description": "Owed to suppliers, 7 days",
                    },
                ],
            },
            {
                "title": "Dealers & Suppliers",
                "rows": [
                    {
                        "id": "all dealers",
                        "title": "All Dealers",
                        "description": "Every dealer, phone & outstanding",
                    },
                    {
                        "id": "all suppliers",
                        "title": "All Suppliers",
                        "description": "Every supplier, phone & outstanding",
                    },
                    {
                        "id": "top debtors",
                        "title": "Top Debtors",
                        "description": "Dealers who owe you the most",
                    },
                    {
                        "id": "top creditors",
                        "title": "Top Creditors",
                        "description": "Suppliers you owe the most",
                    },
                ],
            },
        ],
    },
    {
        "body": "Inventory, Transactions & Products — tap one:",
        "button_text": "Choose an option",
        "sections": [
            {
                "title": "Inventory & Transactions",
                "rows": [
                    {
                        "id": "inventory",
                        "title": "Inventory",
                        "description": "Stock quantity & selling price",
                    },
                    {
                        "id": "invoices",
                        "title": "Recent Invoices",
                        "description": "Latest invoices, newest first",
                    },
                    {
                        "id": "recent payments",
                        "title": "Recent Payments",
                        "description": "Latest payments recorded",
                    },
                    {"id": "faq", "title": "FAQs", "description": "Your saved business policies"},
                ],
            },
            {
                "title": "Manage Products",
                "rows": [
                    {
                        "id": "/add_product",
                        "title": "Add Product",
                        "description": "Add a new catalogue item",
                    },
                    {
                        "id": "/update_stock",
                        "title": "Update Stock",
                        "description": "Change a product's stock qty",
                    },
                    {
                        "id": "/update_price",
                        "title": "Update Price",
                        "description": "Change a product's selling price",
                    },
                    {
                        "id": "/update_purchase_price",
                        "title": "Update Cost Price",
                        "description": "Change what you pay your supplier",
                    },
                    {
                        "id": "/delete_product",
                        "title": "Delete Product",
                        "description": "Remove a catalogue item",
                    },
                    {
                        "id": "/update_product",
                        "title": "Update Product",
                        "description": "Pick price, cost, or stock to change",
                    },
                ],
            },
        ],
    },
    {
        "body": "Orders, Payments & Your Data — tap one:",
        "button_text": "Choose an option",
        "sections": [
            {
                "title": "Orders & Payments",
                "rows": [
                    {
                        "id": "/create_order",
                        "title": "Create Order",
                        "description": "Record a sale to a dealer",
                    },
                    {
                        "id": "/record_payment",
                        "title": "Record Payment",
                        "description": "Log a payment received or paid",
                    },
                    {
                        "id": "/update_gst",
                        "title": "Update GST",
                        "description": "Change GST for all products, or one product",
                    },
                ],
            },
            {
                "title": "Your Data",
                "rows": [
                    {
                        "id": "/export_data",
                        "title": "Export Data",
                        "description": "Download your Excel data",
                    },
                    {
                        "id": "/morning_briefing",
                        "title": "Morning Briefing",
                        "description": "Resend today's briefing",
                    },
                ],
            },
        ],
    },
]


async def _morning_briefing_reply(db: AsyncSession, company: Company) -> str:
    """On-demand morning briefing for a distributor who asks directly instead
    of waiting for the scheduled push (app/core/scheduler.py) — this is the
    deterministic fix for "give me my morning briefing" otherwise falling
    through to the free-form LLM assistant, which has no matching tool and
    just refuses.

    Reuses today's already-generated briefing if the scheduler already ran
    (free, no LLM call); otherwise generates a fresh one on demand via the
    exact same generate_briefing() the scheduler uses — real LLM cost, but
    the user explicitly asked for it right now. Either way, this reply IS the
    delivery (sent like any other webhook reply), so the row is marked
    sent here — otherwise the scheduler's own "already generated today, skip"
    dedup would silently swallow the scheduled push later today for a row
    nothing ever actually delivered.
    """
    briefing = await latest_briefing_today(db, company)
    if briefing is None:
        briefing = await generate_briefing(db, company.id)
    if briefing.delivery_status != "sent":
        briefing.sent_at = business_now(company.timezone)
        briefing.delivery_status = "sent"
    return briefing.generated_text


# WhatsApp's text message body caps around 4096 characters — 60 invoice lines
# comfortably fits with room for the header/footer, generous enough that
# "and N more" almost never triggers for a real distributor's catalogue.
_INVOICES_REPLY_CAP = 60


async def _invoices_reply(db: AsyncSession, company: Company) -> str:
    """The full invoice list, deterministically — "Recent Invoices" is a
    fixed, tappable menu option (not a free-form question), so it must never
    depend on an LLM call (rate limits, an occasional bad tool-call
    response, or the money-safety guard rejecting a reply) to show real
    data that's sitting right there in the database.
    """
    total = await db.scalar(
        select(func.count()).select_from(Invoice).where(Invoice.company_id == company.id)
    )
    if not total:
        return "You don't have any invoices yet."

    stmt = (
        select(Invoice, Dealer.name, Supplier.name)
        .outerjoin(Dealer, Invoice.dealer_id == Dealer.id)
        .outerjoin(Supplier, Invoice.supplier_id == Supplier.id)
        .where(Invoice.company_id == company.id)
        .order_by(Invoice.invoice_date.desc(), Invoice.invoice_number)
        .limit(_INVOICES_REPLY_CAP)
    )
    rows = (await db.execute(stmt)).all()
    lines = [
        f"{invoice.invoice_number} — {dealer_name or supplier_name or 'unknown party'} — "
        f"{format_inr(invoice.total_amount)} — {invoice.status.value} — "
        f"due {invoice.due_date.isoformat()}"
        for invoice, dealer_name, supplier_name in rows
    ]
    remaining = total - len(rows)
    header = (
        f"📄 Invoices ({len(rows)} of {total}):" if remaining > 0 else f"📄 Invoices ({len(rows)}):"
    )
    footer = (
        f"\n…and {remaining} more — use 'export data' for the full list." if remaining > 0 else ""
    )
    return f"{header}\n" + "\n".join(lines) + footer


# Registry: exact-match keyword -> an instant, stateless async reply builder —
# unlike _WORKFLOW_START_TRIGGERS, these never set active_workflow (there's
# nothing to advance through, the whole answer is produced in one shot).
# Checked at the same priority tier, right alongside it.
_INSTANT_COMMANDS: dict[str, Callable[[AsyncSession, Company], Awaitable[str]]] = {
    "export data": _export_link_reply,
    "get my excel": _export_link_reply,
    "send my excel": _export_link_reply,
    "my data sheet": _export_link_reply,
    "download my data": _export_link_reply,
    "morning briefing": _morning_briefing_reply,
    "my morning briefing": _morning_briefing_reply,
    "give me morning briefing": _morning_briefing_reply,
    "give me my morning briefing": _morning_briefing_reply,
    "today's briefing": _morning_briefing_reply,
    "todays briefing": _morning_briefing_reply,
    "send my briefing": _morning_briefing_reply,
    "my briefing": _morning_briefing_reply,
    "brief me": _morning_briefing_reply,
    "/export_data": _export_link_reply,
    "/morning_briefing": _morning_briefing_reply,
    "invoices": _invoices_reply,
    "recent invoices": _invoices_reply,
    "all invoices": _invoices_reply,
    "/invoices": _invoices_reply,
    "/help": _help_reply,
    "help": _help_reply,
    "commands": _help_reply,
    "what can you do": _help_reply,
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
    """'text' messages have a unified body field. 'interactive' messages (a
    tapped list row or reply button) carry no body text at all — Meta puts
    the tapped option's `id` under interactive.list_reply/button_reply
    instead — so it's surfaced here too, and read exactly like typed text by
    every downstream command registry (menu_router, _WORKFLOW_START_TRIGGERS,
    _INSTANT_COMMANDS): a tapped "/add_product" row behaves identically to a
    distributor typing "/add_product" by hand. Other types (image, audio,
    document, location) are logged with `type` set and an empty body —
    parsing their specific shapes is out of scope until a later phase needs
    to act on them.
    """
    if message.get("type") == "text":
        return message.get("text", {}).get("body", "")
    if message.get("type") == "interactive":
        interactive = message.get("interactive", {})
        reply = interactive.get("button_reply") or interactive.get("list_reply")
        if reply:
            return reply.get("id", "")
    return ""


async def _find_company_by_whatsapp_number(
    db: AsyncSession, whatsapp_number: str
) -> Company | None:
    return await db.scalar(select(Company).where(Company.whatsapp_number == whatsapp_number))


async def _find_inbound_event(
    db: AsyncSession, company: Company, message_id: str | None
) -> BusinessEvent | None:
    """The whatsapp_message_received event already written for this exact
    Meta message id, if any. Meta's webhook delivery is at-least-once and
    retries aggressively on slow/non-2xx responses (notably while a cold
    Render instance is still waking up), so redeliveries are common.

    Finding a row here does NOT by itself mean the redelivery should be
    skipped — see _reply_already_sent, which is what actually decides that.
    A row can exist with no reply yet if a previous delivery claimed the
    message (inserted this row) but the process died before finishing (e.g.
    an uncaught error, or Render/Neon suspending mid-request) — that case
    must resume, not be silently dropped.
    """
    if not message_id:
        return None
    return await db.scalar(
        select(BusinessEvent).where(
            BusinessEvent.company_id == company.id,
            BusinessEvent.event_type == BusinessEventType.whatsapp_message_received,
            BusinessEvent.payload["message_id"].astext == message_id,
        )
    )


async def _reply_already_sent(
    db: AsyncSession, company: Company, correlation_id: uuid.UUID
) -> bool:
    """Whether a whatsapp_reply_sent event already exists for this inbound
    message — the actual "fully handled, nothing left to do" signal.
    """
    existing = await db.scalar(
        select(BusinessEvent.id).where(
            BusinessEvent.company_id == company.id,
            BusinessEvent.event_type == BusinessEventType.whatsapp_reply_sent,
            BusinessEvent.payload["correlation_id"].astext == str(correlation_id),
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
    interactive: dict | None = None,
) -> None:
    """Send `reply` over WhatsApp (best-effort — a failed or unconfigured send
    is logged, never raised, so the inbound webhook still 200s to Meta) and
    durably record the attempt: a NotificationLog row keyed by Meta's message
    id, plus a whatsapp_reply_sent BusinessEvent carrying `correlation_id`
    back to the inbound message that triggered this reply.

    `interactive`, if given, is sent instead of plain text (a tappable list —
    see send_interactive_list_message); `reply` is still stored in the
    NotificationLog/trace either way, so the audit trail stays human-readable
    regardless of which message type Meta actually delivered.
    """
    send_result: WhatsAppSendResult | None
    try:
        if interactive is not None:
            send_result = await send_interactive_list_message(recipient, **interactive)
        else:
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
                # Meta's webhook delivery is at-least-once and retries
                # aggressively on a slow response, not just non-2xx — a reply
                # that takes a few seconds (an LLM call, or "menu"'s 3 sends)
                # can trigger a retry before this delivery's whatsapp_reply_sent
                # event commits, and the dedup check below only catches an
                # ALREADY-sent reply, not one still in flight. This Postgres
                # advisory lock (same pattern as app/core/scheduler.py's tick
                # lock) makes a concurrent redelivery of the exact same message
                # WAIT here instead of racing past that check and sending a
                # second reply. If the first delivery genuinely crashed rather
                # than just being slow, its DB connection dies with it and
                # Postgres releases the lock automatically, so a truly dead
                # attempt still lets the retry resume normally. Held on a
                # dedicated `lock_db` connection (never committed) rather than
                # the shared `db` session — `db`'s own commits below (the
                # dedup claim, then the final commit) can hand it a *different*
                # pooled physical connection afterward, which would silently
                # drop a lock acquired on it.
                message_id = message.get("id")
                async with async_session_factory() as lock_db:
                    if message_id is not None:
                        await lock_db.scalar(
                            select(func.pg_advisory_lock(func.hashtext(message_id)))
                        )
                    try:
                        sender = _normalize_to_e164(message.get("from", ""))
                        company = await _find_company_by_whatsapp_number(db, sender)
                        if company is None:
                            logger.warning(
                                "WhatsApp message from unknown sender %s — skipping.", sender
                            )
                            continue
                        existing_inbound = await _find_inbound_event(db, company, message.get("id"))
                        if existing_inbound is not None:
                            if await _reply_already_sent(db, company, existing_inbound.id):
                                logger.info(
                                    "WhatsApp message %s already replied to — skipping redelivery.",
                                    message.get("id"),
                                )
                                continue
                            # Claimed by an earlier delivery but never got a reply out
                            # (that attempt crashed mid-processing — e.g. an uncaught
                            # error, or Render/Neon suspending mid-request). Resume
                            # using the same inbound event rather than re-inserting,
                            # so the reply this redelivery produces still correlates
                            # back to the original message.
                            inbound_event = existing_inbound
                            logger.info(
                                "WhatsApp message %s claimed but never replied to — resuming.",
                                message.get("id"),
                            )
                        else:
                            inbound_event = await _record_message_event(db, company, message)
                            try:
                                # inbound_event.id is a Python-side default applied at
                                # flush time — flush now so it's populated before use
                                # as a correlation_id below. This flush is also the
                                # atomic dedup claim: uq_business_events_wa_inbound_msg
                                # rejects a second insert for the same (company_id,
                                # message_id), so a concurrent redelivery that raced
                                # past the lookup above gets caught here instead. The
                                # loser simply skips — if the winner also fails to
                                # reply, the next Meta redelivery will find this row
                                # via the branch above and resume, same as any other
                                # crash-recovery case.
                                await db.flush()
                            except IntegrityError:
                                await db.rollback()
                                logger.info(
                                    "WhatsApp message %s lost the dedup race — skipping.",
                                    message.get("id"),
                                )
                                continue
                            # Commit the claim now, not just at the end of this whole
                            # webhook call — a redelivery arriving seconds later (Meta
                            # retries several times while a cold instance wakes up)
                            # needs this row visible/committed immediately, or its own
                            # INSERT would block on the uncommitted index entry
                            # instead of failing fast against a committed one.
                            await db.commit()

                        # The agent only responds for companies whose subscription is
                        # active. Onboarded-but-not-yet-activated numbers are logged
                        # (above) but get no reply — the subscription is what "turns on
                        # the agent" for them.
                        if not company.subscription_active:
                            logger.info(
                                "Inbound from %s but subscription inactive — not responding.",
                                sender,
                            )
                            continue

                        if message.get("type") in ("text", "interactive"):
                            text = _extract_text_body(message)
                            command: str | None = None
                            interactive_batch: list[dict] | None = None
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
                            elif text.strip().lower() in _MENU_TRIGGERS:
                                command = text.strip().lower()
                                notification_type = "interactive_menu"
                                reply = _MENU_FALLBACK_TEXT
                                interactive_batch = _MENU_MESSAGES
                            else:
                                # .lower() so the /cash-style slash aliases are
                                # case-insensitive like _WORKFLOW_START_TRIGGERS and
                                # _INSTANT_COMMANDS below — harmless for the plain
                                # "1"-"4" digits, which have no case.
                                command = menu_router.match(text.strip().lower())
                                if command is not None:
                                    # 1-4 (and their /slash aliases) stay instant
                                    # deterministic shortcuts.
                                    snapshot = await build_snapshot(db, company.id)
                                    result = menu_router.execute(command, snapshot)
                                    notification_type = result.notification_type
                                    reply = result.reply
                                elif (
                                    starter := _WORKFLOW_START_TRIGGERS.get(text.strip().lower())
                                ) is not None:
                                    # Deterministic keyword trigger — works without AI,
                                    # per Phase 2A's scope (see module docstring).
                                    command = text.strip().lower()
                                    notification_type = "write_workflow"
                                    reply = starter(company)
                                elif (
                                    instant := _INSTANT_COMMANDS.get(text.strip().lower())
                                ) is not None:
                                    command = text.strip().lower()
                                    notification_type = "instant_command"
                                    reply = await instant(db, company)
                                else:
                                    # Anything else -> the grounded LLM assistant, which
                                    # answers free-form questions from real figures and
                                    # never forwards an unverifiable number.
                                    notification_type = ASSISTANT_NOTIFICATION_TYPE
                                    reply = await answer_question(db, company, text)
                            if interactive_batch is not None:
                                # "menu" — several list messages, one per _send_reply_and_log
                                # call (Meta has no single-message way to exceed 10 rows).
                                # A redelivery of this inbound message only needs to find
                                # one whatsapp_reply_sent event to skip re-sending all of
                                # them — see _reply_already_sent.
                                for payload in interactive_batch:
                                    await _send_reply_and_log(
                                        db,
                                        company,
                                        sender,
                                        notification_type=notification_type,
                                        reply=payload["body"],
                                        command=command,
                                        correlation_id=inbound_event.id,
                                        interactive=payload,
                                    )
                            else:
                                await _send_reply_and_log(
                                    db,
                                    company,
                                    sender,
                                    notification_type=notification_type,
                                    reply=reply,
                                    command=command,
                                    correlation_id=inbound_event.id,
                                )
                    finally:
                        if message_id is not None:
                            await lock_db.scalar(
                                select(func.pg_advisory_unlock(func.hashtext(message_id)))
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
