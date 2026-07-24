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

A `type: image` message is handled separately from the text/interactive
ladder above (see _handle_invoice_photo) — invoice-photo OCR pre-fill
(SPEC V0.3/Future), scoped to the existing dealer/receivable create_order
flow. A `type: audio` message (a WhatsApp voice note, see _handle_voice_note)
is transcribed then fed straight into the same ladder every typed message
goes through (_handle_text_message, factored out of this docstring's ladder
so both entry points share it) — unlike the image path, it is NOT scoped to
one flow, since a spoken "record payment" or a spoken "yes" mid-workflow
must resolve exactly like typing those words would. Any other non-text type
(document/video/sticker/location/contacts, …) still gets a deterministic
"can't read this yet" reply rather than silence, but remains genuinely
unhandled.

A sender that matches no Company's own `whatsapp_number` is not necessarily
unknown: if it's a Dealer's phone under a company with
`dealer_self_service_enabled`, it's routed to a completely separate,
read-only path (app.services.dealer_self_service) instead of being dropped —
see `is_dealer_message` below. This is a structurally distinct ladder, not an
extension of the one above: it never touches onboarding/workflow/pending-op/
follow-up state and never reaches the founder's menu, instant commands, or
the LLM assistant. A phone that matches a Dealer row in more than one company
is refused outright (a generic "contact your distributor" reply, no data
sent) rather than guessing which company it belongs to — see
find_dealer_company's own docstring.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import async_session_factory, get_db
from app.i18n import DEFAULT_LOCALE, Locale, resolve_locale, t
from app.models.business_event import BusinessEvent, BusinessEventType
from app.models.company import Company, OnboardingState
from app.models.dealer import Dealer
from app.models.notification_log import NotificationLog
from app.models.pending_operation import PendingOperationType
from app.models.supplier import Supplier
from app.services import instant_reports
from app.services.assistant import ASSISTANT_NOTIFICATION_TYPE, answer_question
from app.services.briefing import generate_briefing, latest_briefing_today
from app.services.company_export import generate_export_link
from app.services.dealer_self_service import (
    Ambiguous,
    DealerMatch,
    find_dealer_company,
    handle_dealer_message,
)
from app.services.followup import handle_follow_up_reply
from app.services.invoice_ocr import extract_invoice_from_image
from app.services.money_format import format_inr
from app.services.onboarding_flow import handle_onboarding_message, start_language_change
from app.services.party_lookup import find_party
from app.services.query_menu import menu_router
from app.services.reports.period import resolve_period
from app.services.reports.registry import REPORTS
from app.services.snapshot import build_snapshot, business_now
from app.services.voice_transcription import transcribe_voice_note
from app.services.whatsapp_client import (
    WhatsAppMediaTooLargeError,
    WhatsAppNotConfiguredError,
    WhatsAppSendError,
    WhatsAppSendResult,
    download_media,
    send_interactive_list_message,
    send_text_message,
)
from app.services.workflows.broadcast_flow import (
    handle_broadcast_workflow_message,
    start_broadcast_workflow,
)
from app.services.workflows.edit_flow import (
    handle_edit_invoice_workflow_message,
    handle_edit_payment_workflow_message,
    start_edit_invoice_workflow,
    start_edit_payment_workflow,
)
from app.services.workflows.gst_flow import (
    handle_update_gst_workflow_message,
    start_update_gst_workflow,
)
from app.services.workflows.order_flow import (
    handle_order_workflow_message,
    start_order_workflow,
    start_order_workflow_from_ocr,
)
from app.services.workflows.party_flow import (
    handle_add_dealer_workflow_message,
    handle_add_supplier_workflow_message,
    handle_edit_dealer_workflow_message,
    handle_edit_supplier_workflow_message,
    start_add_dealer_workflow,
    start_add_supplier_workflow,
    start_edit_dealer_workflow,
    start_edit_supplier_workflow,
)
from app.services.workflows.payment_flow import (
    handle_payment_workflow_message,
    start_payment_workflow,
)
from app.services.workflows.payment_reminder_confirm import (
    handle_reminder_confirm_workflow_message,
    promote_queued_reminder,
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
from app.services.workflows.stock_take_flow import (
    handle_stock_take_workflow_message,
    start_stock_take_workflow,
)
from app.services.workflows.void_flow import (
    handle_void_order_workflow_message,
    handle_void_payment_workflow_message,
    start_void_order_workflow,
    start_void_payment_workflow,
)
from app.services.writes.pending_operation import (
    create_pending_operation,
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
    "add_dealer": handle_add_dealer_workflow_message,
    "add_supplier": handle_add_supplier_workflow_message,
    "void_payment": handle_void_payment_workflow_message,
    "void_order": handle_void_order_workflow_message,
    "edit_invoice": handle_edit_invoice_workflow_message,
    "edit_payment": handle_edit_payment_workflow_message,
    "edit_dealer": handle_edit_dealer_workflow_message,
    "edit_supplier": handle_edit_supplier_workflow_message,
    "stock_take": handle_stock_take_workflow_message,
    "broadcast_dealers": handle_broadcast_workflow_message,
    # Not in _WORKFLOW_START_TRIGGERS below — this one is only ever started
    # programmatically, by check_supplier_payment_reminders /
    # advance_reminder_queue (app/services/workflows/payment_reminder_confirm.py),
    # never by a founder-typed keyword.
    "confirm_supplier_payment": handle_reminder_confirm_workflow_message,
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
    "add dealer": start_add_dealer_workflow,
    "add a dealer": start_add_dealer_workflow,
    "new dealer": start_add_dealer_workflow,
    "add customer": start_add_dealer_workflow,
    "new customer": start_add_dealer_workflow,
    "add supplier": start_add_supplier_workflow,
    "add a supplier": start_add_supplier_workflow,
    "new supplier": start_add_supplier_workflow,
    "edit invoice": start_edit_invoice_workflow,
    "edit an invoice": start_edit_invoice_workflow,
    "correct invoice": start_edit_invoice_workflow,
    "edit payment": start_edit_payment_workflow,
    "edit a payment": start_edit_payment_workflow,
    "correct payment": start_edit_payment_workflow,
    "edit dealer": start_edit_dealer_workflow,
    "update dealer": start_edit_dealer_workflow,
    "edit a dealer": start_edit_dealer_workflow,
    "edit customer": start_edit_dealer_workflow,
    "edit supplier": start_edit_supplier_workflow,
    "update supplier": start_edit_supplier_workflow,
    "edit a supplier": start_edit_supplier_workflow,
    "stock take": start_stock_take_workflow,
    "stock count": start_stock_take_workflow,
    "bulk stock update": start_stock_take_workflow,
    "stocktake": start_stock_take_workflow,
    "broadcast": start_broadcast_workflow,
    "send broadcast": start_broadcast_workflow,
    "marketing broadcast": start_broadcast_workflow,
    "message dealers": start_broadcast_workflow,
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
    "/add_dealer": start_add_dealer_workflow,
    "/add_supplier": start_add_supplier_workflow,
    "/edit_invoice": start_edit_invoice_workflow,
    "/edit_payment": start_edit_payment_workflow,
    "/edit_dealer": start_edit_dealer_workflow,
    "/edit_supplier": start_edit_supplier_workflow,
    "/stock_take": start_stock_take_workflow,
    "/broadcast": start_broadcast_workflow,
}


async def _export_link_reply(db: AsyncSession, company: Company) -> str:
    """Stateless — a brand-new short-lived signed link every time this is
    asked, never a reused one. See app/services/company_export.py.
    """
    settings = get_settings()
    if not settings.export_link_secret or not settings.public_base_url:
        return t("reports.export.not_configured", resolve_locale(company))
    link = generate_export_link(company, base_url=settings.public_base_url)
    ttl = settings.export_link_ttl_minutes
    return t("reports.export.ready", resolve_locale(company), ttl=ttl, link=link)


async def _opt_in_all_dealers_reply(db: AsyncSession, company: Company) -> str:
    """Bulk "opt in all dealers" — skips straight to a PendingOperation
    confirm (no active_workflow needed, it's a single yes/no) since it's a
    real bulk data mutation, not a stateless reply like _export_link_reply.
    """
    loc = resolve_locale(company)
    count = await db.scalar(
        select(func.count())
        .select_from(Dealer)
        .where(Dealer.company_id == company.id, Dealer.marketing_opt_in.is_(False))
    )
    if not count:
        return t("broadcast.opt_in_all_none", loc)
    await create_pending_operation(db, company, PendingOperationType.bulk_opt_in_dealers, {})
    return t("broadcast.opt_in_all_confirm", loc, count=count)


async def _enable_dealer_self_service_reply(db: AsyncSession, company: Company) -> str:
    """Write-immediately settings toggle (an attribute flip, not a
    money-affecting write) — same tier as update_product's plain field edits,
    no PendingOperation confirm gate needed. See
    app/services/dealer_self_service.py for what this actually turns on.
    """
    company.dealer_self_service_enabled = True
    return t("settings.dealer_self_service_enabled", resolve_locale(company))


async def _disable_dealer_self_service_reply(db: AsyncSession, company: Company) -> str:
    company.dealer_self_service_enabled = False
    return t("settings.dealer_self_service_disabled", resolve_locale(company))


def _current_month_str(company: Company) -> str:
    today = business_now(company.timezone).date()
    return f"{today.year:04d}-{today.month:02d}"


async def _report_link_reply(
    db: AsyncSession, company: Company, *, report: str, party: Dealer | Supplier | None = None
) -> str:
    """Generic reply for every period-scoped report in
    app.services.reports.registry.REPORTS — un-parameterized requests
    default to the current calendar month (aging/outstanding ignores the
    period entirely, it's always a snapshot as of today, see
    app/services/reports/aging.py). Sends both an Excel and, when the report
    has one, a PDF link, so the WhatsApp reply itself names the report *and*
    the period, not just the downloaded file.
    """
    settings = get_settings()
    loc = resolve_locale(company)
    if not settings.export_link_secret or not settings.public_base_url:
        return t("reports.export.not_configured", loc)

    spec = REPORTS[report]
    if report == "aging":
        month, period_label = None, "as of today"
    else:
        month = _current_month_str(company)
        period_label = resolve_period(month_str=month).label

    link_kwargs: dict[str, object] = {"report": report, "month": month}
    if party is not None:
        link_kwargs["party_id"] = party.id

    excel_link = generate_export_link(company, base_url=settings.public_base_url, **link_kwargs)
    lines = [f"Excel: {excel_link}"]
    if spec.build_pdf is not None:
        pdf_link = generate_export_link(
            company, base_url=settings.public_base_url, format="pdf", **link_kwargs
        )
        lines.append(f"PDF: {pdf_link}")

    report_label = f"{spec.display_name} — {party.name}" if party is not None else spec.display_name
    return t(
        "reports.download.ready",
        loc,
        report_name=report_label,
        period=period_label,
        ttl=settings.export_link_ttl_minutes,
        links="\n".join(lines),
    )


async def _ledger_reply(db: AsyncSession, company: Company, name: str) -> str:
    match = await find_party(db, company.id, name)
    if match is None:
        return t("reports.ledger.not_found", resolve_locale(company), name=name)
    party, _direction = match
    return await _report_link_reply(db, company, report="ledger", party=party)


async def _gst_report_reply(db: AsyncSession, company: Company) -> str:
    """"GST report" is ambiguous between sales and purchase — send both
    rather than guess. Distributors who want just one already have
    "sales register"/"purchase register" for that.
    """
    sales = await _report_link_reply(db, company, report="sales_register")
    purchase = await _report_link_reply(db, company, report="purchase_register")
    return f"{sales}\n\n{purchase}"


async def _sales_register_reply(db: AsyncSession, company: Company) -> str:
    return await _report_link_reply(db, company, report="sales_register")


async def _purchase_register_reply(db: AsyncSession, company: Company) -> str:
    return await _report_link_reply(db, company, report="purchase_register")


async def _payment_register_reply(db: AsyncSession, company: Company) -> str:
    return await _report_link_reply(db, company, report="payment_register")


async def _day_book_reply(db: AsyncSession, company: Company) -> str:
    return await _report_link_reply(db, company, report="day_book")


async def _aging_report_reply(db: AsyncSession, company: Company) -> str:
    return await _report_link_reply(db, company, report="aging")


def _help_reply_parts(company: Company) -> list[str]:
    """The full help block, as two plain-text messages. Real production bug
    (2026-07-24): stored as a single message, the English text alone was
    4,594 characters — over Meta's hard 4,096-char limit on a single text
    body (every other locale catalog was over too) — so every "help"/"/help"
    send failed outright (a real 400: "Param text.body must be at most 4096
    characters long") and the founder got nothing at all, indistinguishable
    from the command not existing. Split at a natural section boundary
    (menu.help_text / menu.help_text_more) rather than truncated, so no
    command documented here is lost.
    """
    loc = resolve_locale(company)
    return [t("menu.help_text", loc), t("menu.help_text_more", loc)]


async def _change_language_reply(db: AsyncSession, company: Company) -> str:
    """Re-enter the language/script selection for an already-onboarded company
    (see onboarding_flow.start_language_change). Sets onboarding_state so the
    next messages flow back through the two-step picker, then return to done.
    """
    return start_language_change(company)


# "menu" sends tappable WhatsApp list messages instead of plain text — every
# zero-argument capability in the help text, split across 4 messages since Meta
# caps a single list at 10 rows total. (balance <name> / stock <product> /
# ledger <name> need a typed argument, so they can't be a fixed tappable row —
# they stay type-to-use, per the help text.) Row ids are read back exactly like typed text
# (see _extract_text_body), so each one is either an existing /slash_command
# or a bare keyword the free-form assistant (app/services/assistant.py)
# already understands.
_MENU_TRIGGERS = ("menu", "/menu")

# "help" sends the full command reference as two plain-text messages (see
# _help_reply_parts) — split, not truncated, since the combined text is over
# Meta's 4,096-char single-message limit in every locale.
_HELP_TRIGGERS = ("/help", "help", "commands", "what can you do")


# Menu *structure* only — the tappable-row ids stay fixed English (they're
# read back verbatim as commands, see _extract_text_body), while every
# human-readable label (message body/button, section titles, row
# titles/descriptions) is looked up from the i18n catalog per the company's
# locale by menu_messages() below. Each row is (id, title_key, desc_key).
_MENU_LAYOUT: list[dict] = [
    {
        "body_key": "menu.msg.reports.body",
        "button_key": "menu.msg.reports.button",
        "sections": [
            (
                "menu.section.cash_overview",
                [
                    ("cash", "menu.row.cash.title", "menu.row.cash.desc"),
                    ("summary", "menu.row.summary.title", "menu.row.summary.desc"),
                    ("priorities", "menu.row.priorities.title", "menu.row.priorities.desc"),
                ],
            ),
            (
                "menu.section.money_flow",
                [
                    ("overdue", "menu.row.overdue.title", "menu.row.overdue.desc"),
                    (
                        "upcoming collections",
                        "menu.row.collections.title",
                        "menu.row.collections.desc",
                    ),
                    ("upcoming payments", "menu.row.payments.title", "menu.row.payments.desc"),
                ],
            ),
            (
                "menu.section.dealers_suppliers",
                [
                    ("all dealers", "menu.row.all_dealers.title", "menu.row.all_dealers.desc"),
                    (
                        "all suppliers",
                        "menu.row.all_suppliers.title",
                        "menu.row.all_suppliers.desc",
                    ),
                    ("top debtors", "menu.row.top_debtors.title", "menu.row.top_debtors.desc"),
                    (
                        "top creditors",
                        "menu.row.top_creditors.title",
                        "menu.row.top_creditors.desc",
                    ),
                ],
            ),
        ],
    },
    {
        "body_key": "menu.msg.inventory.body",
        "button_key": "menu.msg.inventory.button",
        "sections": [
            (
                "menu.section.inventory_transactions",
                [
                    ("inventory", "menu.row.inventory.title", "menu.row.inventory.desc"),
                    ("invoices", "menu.row.invoices.title", "menu.row.invoices.desc"),
                    (
                        "recent payments",
                        "menu.row.recent_payments.title",
                        "menu.row.recent_payments.desc",
                    ),
                    ("faq", "menu.row.faq.title", "menu.row.faq.desc"),
                ],
            ),
            (
                "menu.section.manage_products",
                [
                    ("/add_product", "menu.row.add_product.title", "menu.row.add_product.desc"),
                    ("/update_stock", "menu.row.update_stock.title", "menu.row.update_stock.desc"),
                    ("/update_price", "menu.row.update_price.title", "menu.row.update_price.desc"),
                    (
                        "/update_purchase_price",
                        "menu.row.update_cost.title",
                        "menu.row.update_cost.desc",
                    ),
                    (
                        "/delete_product",
                        "menu.row.delete_product.title",
                        "menu.row.delete_product.desc",
                    ),
                    (
                        "/update_product",
                        "menu.row.update_product.title",
                        "menu.row.update_product.desc",
                    ),
                ],
            ),
        ],
    },
    {
        "body_key": "menu.msg.orders.body",
        "button_key": "menu.msg.orders.button",
        "sections": [
            (
                "menu.section.orders_payments",
                [
                    ("/create_order", "menu.row.create_order.title", "menu.row.create_order.desc"),
                    (
                        "/record_payment",
                        "menu.row.record_payment.title",
                        "menu.row.record_payment.desc",
                    ),
                    ("/update_gst", "menu.row.update_gst.title", "menu.row.update_gst.desc"),
                ],
            ),
            (
                "menu.section.manage_parties",
                [
                    ("/add_dealer", "menu.row.add_dealer.title", "menu.row.add_dealer.desc"),
                    ("/add_supplier", "menu.row.add_supplier.title", "menu.row.add_supplier.desc"),
                ],
            ),
            (
                "menu.section.your_data",
                [
                    ("/export_data", "menu.row.export_data.title", "menu.row.export_data.desc"),
                    (
                        "/morning_briefing",
                        "menu.row.morning_briefing.title",
                        "menu.row.morning_briefing.desc",
                    ),
                ],
            ),
            (
                "menu.section.full_lists",
                [
                    (
                        "all inventory",
                        "menu.row.all_inventory.title",
                        "menu.row.all_inventory.desc",
                    ),
                    ("all invoices", "menu.row.all_invoices.title", "menu.row.all_invoices.desc"),
                    ("all payments", "menu.row.all_payments.title", "menu.row.all_payments.desc"),
                ],
            ),
        ],
    },
    {
        "body_key": "menu.msg.statements.body",
        "button_key": "menu.msg.statements.button",
        "sections": [
            (
                "menu.section.reports_statements",
                [
                    ("gst report", "menu.row.gst_report.title", "menu.row.gst_report.desc"),
                    (
                        "sales register",
                        "menu.row.sales_register.title",
                        "menu.row.sales_register.desc",
                    ),
                    (
                        "purchase register",
                        "menu.row.purchase_register.title",
                        "menu.row.purchase_register.desc",
                    ),
                    (
                        "payment register",
                        "menu.row.payment_register.title",
                        "menu.row.payment_register.desc",
                    ),
                    ("day book", "menu.row.day_book.title", "menu.row.day_book.desc"),
                    (
                        "outstanding report",
                        "menu.row.outstanding_report.title",
                        "menu.row.outstanding_report.desc",
                    ),
                    (
                        "trend report",
                        "menu.row.trend_report.title",
                        "menu.row.trend_report.desc",
                    ),
                    (
                        "delivery status",
                        "menu.row.delivery_status.title",
                        "menu.row.delivery_status.desc",
                    ),
                ],
            ),
        ],
    },
    {
        "body_key": "menu.msg.corrections.body",
        "button_key": "menu.msg.corrections.button",
        "sections": [
            (
                "menu.section.corrections",
                [
                    (
                        "undo payment",
                        "menu.row.undo_payment.title",
                        "menu.row.undo_payment.desc",
                    ),
                    ("undo order", "menu.row.undo_order.title", "menu.row.undo_order.desc"),
                    (
                        "/edit_invoice",
                        "menu.row.edit_invoice.title",
                        "menu.row.edit_invoice.desc",
                    ),
                    (
                        "/edit_payment",
                        "menu.row.edit_payment.title",
                        "menu.row.edit_payment.desc",
                    ),
                    ("/edit_dealer", "menu.row.edit_dealer.title", "menu.row.edit_dealer.desc"),
                    (
                        "/edit_supplier",
                        "menu.row.edit_supplier.title",
                        "menu.row.edit_supplier.desc",
                    ),
                    ("/stock_take", "menu.row.stock_take.title", "menu.row.stock_take.desc"),
                ],
            ),
        ],
    },
]


def menu_messages(locale: Locale | object) -> list[dict]:
    """Render _MENU_LAYOUT into WhatsApp interactive-list payloads with every
    label localized to `locale`. Row ids are untouched (English commands).
    """
    loc = resolve_locale(locale)
    return [
        {
            "body": t(msg["body_key"], loc),
            "button_text": t(msg["button_key"], loc),
            "sections": [
                {
                    "title": t(section_key, loc),
                    "rows": [
                        {"id": rid, "title": t(title_key, loc), "description": t(desc_key, loc)}
                        for rid, title_key, desc_key in rows
                    ],
                }
                for section_key, rows in msg["sections"]
            ],
        }
        for msg in _MENU_LAYOUT
    ]


# English materialization kept for the structural webhook tests that import it
# directly; the localized builders above are the source of truth and are what
# the webhook actually sends (see the "menu" branch in the handler).
_MENU_MESSAGES: list[dict] = menu_messages(DEFAULT_LOCALE)


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


_BALANCE_PREFIX = "balance "
_STOCK_PREFIX = "stock "
_LEDGER_PREFIX = "ledger "


async def _try_deterministic_free_text(db: AsyncSession, company: Company, text: str) -> str | None:
    """The last deterministic tier before the LLM assistant: a name/item-
    scoped lookup ("balance <name>", "stock <item>", "ledger <name>") or the
    "if I sell N of X" fast-path — too free-form for _INSTANT_COMMANDS'
    exact-match dict, but narrow enough to resolve with certainty against the
    real party list/catalogue. Returns None (never a guess) if nothing
    matches confidently, so the caller falls through to the LLM assistant
    exactly as before — this can only ever add coverage, never regress it.
    """
    stripped = text.strip()
    lower = stripped.lower()
    if lower.startswith(_BALANCE_PREFIX):
        name = stripped[len(_BALANCE_PREFIX) :].strip()
        if name:
            return await instant_reports.party_balance_reply(db, company, name)
    elif lower.startswith(_STOCK_PREFIX):
        name = stripped[len(_STOCK_PREFIX) :].strip()
        if name:
            return await instant_reports.stock_item_reply(db, company, name)
    elif lower.startswith(_LEDGER_PREFIX):
        name = stripped[len(_LEDGER_PREFIX) :].strip()
        if name:
            return await _ledger_reply(db, company, name)

    return await instant_reports.try_deterministic_sales_impact(db, company, text)


# Registry: exact-match keyword -> an instant, stateless async reply builder —
# unlike _WORKFLOW_START_TRIGGERS, these never set active_workflow (there's
# nothing to advance through, the whole answer is produced in one shot).
# Checked at the same priority tier, right alongside it.
#
# Everything below from "cash"/"cash position" onward answers a *fixed,
# tappable menu option* under Reports & Overview / Dealers & Suppliers /
# Inventory & Transactions (see _MENU_MESSAGES) — never a free-form question
# — so it must never depend on an LLM call succeeding (a rate-limited
# provider or the money-safety guard rejecting a reply otherwise turns real
# data sitting right there in the database into "Sorry, I couldn't answer
# that right now"). See app/services/instant_reports.py for the formatters.
#
# Deliberately NOT claiming bare "payments" here: /help documents it as an
# alias for BOTH "upcoming payments" (owed to suppliers) and "recent
# payments" (payment history) — a genuine pre-existing ambiguity that only
# the free-form assistant can resolve from context. Only the unambiguous
# full phrases are claimed.
_INSTANT_COMMANDS: dict[str, Callable[[AsyncSession, Company], Awaitable[str]]] = {
    # Correction workflows — void the single most-recently WhatsApp-recorded
    # payment/order. Instant (not a _WORKFLOW_START_TRIGGERS entry) because
    # the lookup needs `db`, which that dict's starters don't receive; each
    # opens its own tiny active_workflow just for the optional reason step —
    # see app/services/workflows/void_flow.py.
    "undo payment": start_void_payment_workflow,
    "undo last payment": start_void_payment_workflow,
    "void payment": start_void_payment_workflow,
    "void last payment": start_void_payment_workflow,
    "/undo_payment": start_void_payment_workflow,
    "undo order": start_void_order_workflow,
    "undo last order": start_void_order_workflow,
    "void order": start_void_order_workflow,
    "void last order": start_void_order_workflow,
    "/undo_order": start_void_order_workflow,
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
    "gst report": _gst_report_reply,
    "gst sales register": _sales_register_reply,
    "sales register": _sales_register_reply,
    "gst purchase register": _purchase_register_reply,
    "purchase register": _purchase_register_reply,
    "payment register": _payment_register_reply,
    "receipt register": _payment_register_reply,
    "day book": _day_book_reply,
    "outstanding report": _aging_report_reply,
    "aging report": _aging_report_reply,
    "outstanding aging report": _aging_report_reply,
    "trend report": instant_reports.trend_report_reply,
    "business trends": instant_reports.trend_report_reply,
    "trends": instant_reports.trend_report_reply,
    "sales trend": instant_reports.trend_report_reply,
    "/gst_report": _gst_report_reply,
    "/sales_register": _sales_register_reply,
    "/purchase_register": _purchase_register_reply,
    "/payment_register": _payment_register_reply,
    "/day_book": _day_book_reply,
    "/outstanding_report": _aging_report_reply,
    "/trend_report": instant_reports.trend_report_reply,
    "delivery status": instant_reports.delivery_status_reply,
    "message status": instant_reports.delivery_status_reply,
    "/delivery_status": instant_reports.delivery_status_reply,
    "cash": instant_reports.cash_position_reply,
    "cash position": instant_reports.cash_position_reply,
    "/cash": instant_reports.cash_position_reply,
    "summary": instant_reports.business_summary_reply,
    "business summary": instant_reports.business_summary_reply,
    "priorities": instant_reports.priorities_reply,
    "what should i do": instant_reports.priorities_reply,
    "overdue": instant_reports.overdue_dealers_reply,
    "overdue dealers": instant_reports.overdue_dealers_reply,
    "/dealer_risk": instant_reports.overdue_dealers_reply,
    "collections": instant_reports.upcoming_collections_reply,
    "upcoming collections": instant_reports.upcoming_collections_reply,
    "/collections": instant_reports.upcoming_collections_reply,
    "upcoming payments": instant_reports.upcoming_payments_reply,
    "payments due": instant_reports.upcoming_payments_reply,
    "/suppliers": instant_reports.upcoming_payments_reply,
    "dealers": instant_reports.all_dealers_reply,
    "all dealers": instant_reports.all_dealers_reply,
    "suppliers": instant_reports.all_suppliers_reply,
    "all suppliers": instant_reports.all_suppliers_reply,
    "top debtors": instant_reports.top_debtors_reply,
    "who owes most": instant_reports.top_debtors_reply,
    "top creditors": instant_reports.top_creditors_reply,
    "inventory": instant_reports.recent_inventory_reply,
    "products": instant_reports.recent_inventory_reply,
    "stock": instant_reports.recent_inventory_reply,
    "recent inventory": instant_reports.recent_inventory_reply,
    "all inventory": instant_reports.all_inventory_reply,
    "faq": instant_reports.faqs_reply,
    "faqs": instant_reports.faqs_reply,
    "policy": instant_reports.faqs_reply,
    "invoices": instant_reports.recent_invoices_reply,
    "recent invoices": instant_reports.recent_invoices_reply,
    "/invoices": instant_reports.recent_invoices_reply,
    "all invoices": instant_reports.all_invoices_reply,
    "recent payments": instant_reports.recent_payments_reply,
    "all payments": instant_reports.all_payments_reply,
    "all time payments": instant_reports.all_payments_reply,
    "change language": _change_language_reply,
    "change script": _change_language_reply,
    "language": _change_language_reply,
    "script": _change_language_reply,
    "/language": _change_language_reply,
    "opt in all dealers": _opt_in_all_dealers_reply,
    "opt in all": _opt_in_all_dealers_reply,
    "enable marketing for all dealers": _opt_in_all_dealers_reply,
    "/opt_in_all_dealers": _opt_in_all_dealers_reply,
    "enable dealer self-service": _enable_dealer_self_service_reply,
    "enable dealer self service": _enable_dealer_self_service_reply,
    "/enable_dealer_self_service": _enable_dealer_self_service_reply,
    "disable dealer self-service": _disable_dealer_self_service_reply,
    "disable dealer self service": _disable_dealer_self_service_reply,
    "/disable_dealer_self_service": _disable_dealer_self_service_reply,
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
    id, plus — only when the send actually succeeded — a whatsapp_reply_sent
    BusinessEvent carrying `correlation_id` back to the inbound message that
    triggered this reply.

    That marker is the *only* thing _reply_already_sent checks to decide
    whether a Meta redelivery of this inbound message should be skipped or
    reprocessed. Writing it unconditionally (the original behavior) meant a
    real send failure — a transient WhatsApp API error, not a code bug —
    still got permanently marked "handled": the founder's phone never
    received anything, but any future redelivery of that exact message would
    see the marker and silently skip retrying it forever. Now a failed send
    leaves no marker, so a genuine redelivery resumes and tries the send
    again instead of going permanently silent.

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

    if send_result is not None:
        await _record_reply_sent_event(
            db,
            company,
            correlation_id=correlation_id,
            notification_log_id=log.id,
            whatsapp_message_id=send_result.message_id,
            command=command,
        )


async def _handle_text_message(
    db: AsyncSession, company: Company, text: str
) -> tuple[str, str | None, str, list[dict] | None]:
    """Resolve `text` through the full reply-priority ladder documented in
    this module's own docstring (onboarding > active workflow > pending
    confirm > follow-up > menu trigger > instant command > deterministic
    free text > LLM assistant). Shared by real inbound text/interactive
    messages and a transcribed voice note (see _handle_voice_note) — a voice
    note is just another way to produce `text`, so it must resolve through
    the exact same priority order, never a separate/simpler path.

    Returns (notification_type, command, reply, interactive_batch).
    """
    command: str | None = None
    interactive_batch: list[dict] | None = None
    if company.onboarding_state != OnboardingState.completed:
        # Guided setup outranks everything else — mid-onboarding a "1" is an
        # answer to the current question, not the "Cash Position" menu command.
        notification_type = "onboarding"
        reply = await handle_onboarding_message(db, company, text)
    elif company.active_workflow is not None:
        # A guided write workflow (Phase 2A) outranks the menu and the
        # follow-up for the same reason follow-up already did — mid-flow, a
        # bare "10" is the quantity/amount answer, not a menu command.
        # Dispatch by the workflow's own value (not just its presence) so a
        # second workflow type (Phase 2B) can register its own handler
        # without this branch needing to change.
        workflow_handler = _WORKFLOW_HANDLERS.get(company.active_workflow)
        if workflow_handler is not None:
            notification_type = "write_workflow"
            reply = await workflow_handler(db, company, text)
        else:
            # An active_workflow value nothing registers a handler for
            # (shouldn't happen) — never leave the company stuck on a
            # workflow this code can't run.
            company.active_workflow = None
            company.workflow_scratch = None
            notification_type = "write_workflow_error"
            reply = "Something went wrong. Please try again."
    elif company.active_pending_operation_id is not None:
        # In-memory pointer check (no query) — mirrors
        # pending_follow_up_invoice_id below, so companies that never use a
        # guided write workflow pay zero extra cost on every message.
        pending_op = await get_pending_operation(db, company.active_pending_operation_id)
        if pending_op is None:
            # Pointer stale (shouldn't happen — every deletion path clears
            # it in the same transaction).
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
            reply = await handle_pending_operation_reply(db, company, pending_op, text)
    elif company.pending_follow_up_invoice_id is not None:
        # A pending follow-up takes priority over the numbered menu —
        # "1"/"2"/"3" here answers the follow-up question, not "Cash Position".
        notification_type = "follow_up_reply"
        reply = await handle_follow_up_reply(db, company, text)
    elif text.strip().lower() in _MENU_TRIGGERS:
        command = text.strip().lower()
        notification_type = "interactive_menu"
        locale = resolve_locale(company)
        # Each list message carries its own body; this reply is a
        # plain-text safety net (kept bound for the shared send contract
        # below).
        reply = t("menu.fallback", locale)
        interactive_batch = menu_messages(locale)
    elif text.strip().lower() in _HELP_TRIGGERS:
        command = text.strip().lower()
        notification_type = "instant_command"
        parts = _help_reply_parts(company)
        reply = parts[0]
        # Plain-text batch — no "sections" key, so _dispatch_ladder_reply
        # sends each as an ordinary text message rather than an interactive
        # list (see its own docstring for that distinction).
        interactive_batch = [{"body": part} for part in parts]
    else:
        # .lower() so the /cash-style slash aliases are case-insensitive
        # like _WORKFLOW_START_TRIGGERS and _INSTANT_COMMANDS below —
        # harmless for the plain "1"-"4" digits, which have no case.
        command = menu_router.match(text.strip().lower())
        if command is not None:
            # 1-4 (and their /slash aliases) stay instant deterministic
            # shortcuts.
            snapshot = await build_snapshot(db, company.id)
            result = menu_router.execute(command, snapshot)
            notification_type = result.notification_type
            reply = result.reply
        elif (starter := _WORKFLOW_START_TRIGGERS.get(text.strip().lower())) is not None:
            # Deterministic keyword trigger — works without AI, per Phase
            # 2A's scope (see module docstring).
            command = text.strip().lower()
            notification_type = "write_workflow"
            reply = starter(company)
        elif (instant := _INSTANT_COMMANDS.get(text.strip().lower())) is not None:
            command = text.strip().lower()
            notification_type = "instant_command"
            reply = await instant(db, company)
        elif (deterministic := await _try_deterministic_free_text(db, company, text)) is not None:
            # A narrower, parsed deterministic match ("balance <name>",
            # "stock <item>", "if I sell N of X") — still never touches the
            # LLM, but needs an argument _INSTANT_COMMANDS' exact-match dict
            # can't take.
            command = text.strip().lower()
            notification_type = "instant_command"
            reply = deterministic
        else:
            # Anything else -> the grounded LLM assistant, which answers
            # free-form questions from real figures and never forwards an
            # unverifiable number.
            notification_type = ASSISTANT_NOTIFICATION_TYPE
            reply = await answer_question(db, company, text)
    return notification_type, command, reply, interactive_batch


async def _dispatch_ladder_reply(
    db: AsyncSession,
    company: Company,
    sender: str,
    correlation_id: uuid.UUID,
    *,
    notification_type: str,
    command: str | None,
    reply: str,
    interactive_batch: list[dict] | None,
) -> None:
    """Send whatever _handle_text_message decided — either a batch of several
    messages ("menu"'s tappable interactive lists, or "help"'s two plain-text
    halves — see _help_reply_parts), or a single plain-text reply. Factored
    out so both the real text/interactive branch and the transcribed-voice-
    note branch (_handle_voice_note) share one send path.
    """
    if interactive_batch is not None:
        # Several messages, one per _send_reply_and_log call (Meta has no
        # single-message way to exceed either its 10-row interactive-list cap
        # or its 4,096-char text cap). A redelivery of this inbound message
        # only needs to find one whatsapp_reply_sent event to skip re-sending
        # all of them — see _reply_already_sent.
        for payload in interactive_batch:
            # A batch entry with no "sections" key is plain text (help's two
            # halves), not a real interactive-list payload (menu's) — Meta's
            # interactive-list API requires body/button_text/sections, so
            # passing a plain-text entry to send_interactive_list_message
            # would be a malformed request.
            is_interactive = "sections" in payload
            await _send_reply_and_log(
                db,
                company,
                sender,
                notification_type=notification_type,
                reply=payload["body"],
                command=command,
                correlation_id=correlation_id,
                interactive=payload if is_interactive else None,
            )
    else:
        await _send_reply_and_log(
            db,
            company,
            sender,
            notification_type=notification_type,
            reply=reply,
            command=command,
            correlation_id=correlation_id,
        )


async def _handle_invoice_photo(db: AsyncSession, company: Company, message: dict) -> str:
    """Entry point for an inbound `type: image` message — invoice-photo OCR
    pre-fill (SPEC V0.3/Future's "OCR for invoice photos"), scoped to the
    existing dealer/receivable create_order flow (see
    app/services/workflows/order_flow.py::start_order_workflow_from_ocr and
    app/services/invoice_ocr.py). Never raises — same "must never raise in
    the webhook path" contract every other reply builder here follows.

    A company already mid-onboarding, mid another guided workflow, mid a
    pending-operation confirm, or mid a follow-up conversation gets a
    deterministic "finish that first" reply instead of being silently
    dropped — this is what actually closes the "images get total silence"
    finding, in every state, not just idle.
    """
    loc = resolve_locale(company)
    busy = (
        company.onboarding_state != OnboardingState.completed
        or company.active_workflow is not None
        or company.active_pending_operation_id is not None
        or company.pending_follow_up_invoice_id is not None
    )
    if busy:
        return t("workflow.photo_busy", loc)

    media_id = (message.get("image") or {}).get("id")
    if not media_id:
        return t("order.ocr_unreadable", loc)

    try:
        image_bytes, mime_type = await download_media(media_id)
    except (WhatsAppNotConfiguredError, WhatsAppSendError, WhatsAppMediaTooLargeError) as exc:
        logger.warning("Invoice photo download failed for company %s: %s", company.id, exc)
        return t("order.ocr_download_failed", loc)

    extraction = await extract_invoice_from_image(image_bytes, mime_type)
    if extraction is None:
        return t("order.ocr_unreadable", loc)
    return start_order_workflow_from_ocr(company, extraction)


async def _handle_voice_note(
    db: AsyncSession, company: Company, sender: str, message: dict, correlation_id: uuid.UUID
) -> None:
    """Entry point for an inbound `type: audio` message (a WhatsApp voice
    note) — transcribes it (app/services/voice_transcription.py), then
    routes the transcript through _handle_text_message exactly like a typed
    message. Deliberately NOT gated on a "busy" state first, unlike
    _handle_invoice_photo above — a voice note is just another way to
    produce `text`, so a voice-note "yes" mid-onboarding (or mid any other
    guided flow) must answer that flow's current question, not get a canned
    "finish that first" reply; _handle_text_message already resolves every
    one of those states correctly on its own, so no separate gate is needed
    or wanted here.

    The transcript is echoed back ahead of the actual reply, folded into the
    very same outbound send rather than a separate one first — sending it
    separately would reintroduce the exact race _dispatch_ladder_reply's
    single-dispatch-per-inbound-message contract exists to avoid: a crash
    between an ack send and the real reply would let a redelivery see
    "already replied" (_reply_already_sent) and skip re-running a write
    _handle_text_message already decided on. Folding it into one send keeps
    this path exactly as crash-safe as a real typed message. Worth the
    acknowledgment at all because voice is far more error-prone than typed
    text — it's the only visibility a distributor gets into what was
    actually understood before it's dispatched through every write-capable
    branch _handle_text_message can reach.
    """
    loc = resolve_locale(company)
    media_id = (message.get("audio") or {}).get("id")
    if not media_id:
        await _send_reply_and_log(
            db,
            company,
            sender,
            notification_type="voice_note_unreadable",
            reply=t("workflow.voice_unreadable", loc),
            command=None,
            correlation_id=correlation_id,
        )
        return

    try:
        audio_bytes, mime_type = await download_media(media_id)
    except (WhatsAppNotConfiguredError, WhatsAppSendError, WhatsAppMediaTooLargeError) as exc:
        logger.warning("Voice note download failed for company %s: %s", company.id, exc)
        await _send_reply_and_log(
            db,
            company,
            sender,
            notification_type="voice_note_download_failed",
            reply=t("workflow.voice_download_failed", loc),
            command=None,
            correlation_id=correlation_id,
        )
        return

    transcript = await transcribe_voice_note(audio_bytes, mime_type)
    if not transcript:
        await _send_reply_and_log(
            db,
            company,
            sender,
            notification_type="voice_note_unreadable",
            reply=t("workflow.voice_unreadable", loc),
            command=None,
            correlation_id=correlation_id,
        )
        return

    notification_type, command, reply, interactive_batch = await _handle_text_message(
        db, company, transcript
    )
    ack = t("workflow.voice_transcribed", loc, transcript=transcript)
    if interactive_batch is not None:
        # "menu" triggered by voice — read-only, so folding the ack into the
        # first list message's own body (rather than sending it separately)
        # is purely a UX choice here, not a safety requirement like the
        # plain-reply branch below; done the same way regardless for one
        # consistent shape.
        first, *rest = interactive_batch
        interactive_batch = [{**first, "body": f"{ack}\n\n{first['body']}"}, *rest]
    else:
        reply = f"{ack}\n\n{reply}"
    await _dispatch_ladder_reply(
        db,
        company,
        sender,
        correlation_id,
        notification_type=notification_type,
        command=command,
        reply=reply,
        interactive_batch=interactive_batch,
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
                        is_dealer_message = False
                        dealer: Dealer | None = None
                        if company is None:
                            # Not a founder's own number — see if it's a
                            # dealer opted into self-service (Phase 1,
                            # read-only; app/services/dealer_self_service.py).
                            # Founder lookup above always wins and is
                            # unaffected by any of this.
                            dealer_match = await find_dealer_company(db, sender)
                            if isinstance(dealer_match, Ambiguous):
                                # Never attribute this to any one company's
                                # audit trail — see find_dealer_company's
                                # docstring. Best-effort, no
                                # NotificationLog/BusinessEvent tied to a
                                # single (possibly wrong) company.
                                with contextlib.suppress(
                                    WhatsAppNotConfiguredError, WhatsAppSendError
                                ):
                                    await send_text_message(
                                        sender, t("dealer.ambiguous_number", DEFAULT_LOCALE)
                                    )
                                logger.warning(
                                    "Inbound %s matches dealers in multiple companies —"
                                    " refusing.",
                                    sender,
                                )
                                continue
                            if isinstance(dealer_match, DealerMatch):
                                company = dealer_match.company
                                dealer = dealer_match.dealer
                                is_dealer_message = True
                            else:
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

                        if is_dealer_message:
                            # Structurally separate from the founder ladder
                            # below — a dealer message never reaches
                            # onboarding/workflow/pending-op/follow-up state,
                            # never the founder's menu/instant commands, never
                            # the LLM assistant. Voice/photo/other from a
                            # dealer is out of scope for this slice and gets
                            # the same deterministic fallback any other
                            # unhandled type gets.
                            assert dealer is not None
                            if message.get("type") in ("text", "interactive"):
                                text = _extract_text_body(message)
                                await _send_reply_and_log(
                                    db,
                                    company,
                                    sender,
                                    notification_type="dealer_self_service",
                                    reply=await handle_dealer_message(db, company, dealer, text),
                                    command=text.strip().lower(),
                                    correlation_id=inbound_event.id,
                                )
                            else:
                                loc = resolve_locale(company)
                                await _send_reply_and_log(
                                    db,
                                    company,
                                    sender,
                                    notification_type="unsupported_message_type",
                                    reply=t("workflow.unsupported_message_type", loc),
                                    command=None,
                                    correlation_id=inbound_event.id,
                                )
                        elif message.get("type") in ("text", "interactive"):
                            text = _extract_text_body(message)
                            # Native WhatsApp quote-reply on a specific queued
                            # payment reminder — let the founder jump ahead of
                            # whichever bill is currently active instead of
                            # being forced through the queue in strict order.
                            # A no-op (returns False) whenever this isn't a
                            # reminder-jump: no reminder conversation active,
                            # quoting the already-active message, or quoting
                            # something unrelated — see promote_queued_
                            # reminder's own docstring.
                            context_id = (message.get("context") or {}).get("id")
                            promoted = bool(context_id) and promote_queued_reminder(
                                company, context_id
                            )
                            # Snapshot the promoted bill's own details *before*
                            # _handle_text_message runs — the very reply being
                            # processed can itself finish this reminder (e.g.
                            # a full "1, yes paid" confirmation clears
                            # workflow_scratch entirely), so reading scratch
                            # afterward could no longer show what was just
                            # switched to.
                            switched_supplier = (
                                (company.workflow_scratch or {}).get("supplier_name")
                                if promoted
                                else None
                            )
                            switched_amount = (
                                (company.workflow_scratch or {}).get("amount") if promoted else None
                            )
                            notification_type, command, reply, interactive_batch = (
                                await _handle_text_message(db, company, text)
                            )
                            if promoted:
                                reply = (
                                    t(
                                        "reminder_confirm.switched_to",
                                        resolve_locale(company),
                                        supplier=switched_supplier,
                                        amount=format_inr(Decimal(switched_amount)),
                                    )
                                    + "\n\n"
                                    + reply
                                )
                            await _dispatch_ladder_reply(
                                db,
                                company,
                                sender,
                                inbound_event.id,
                                notification_type=notification_type,
                                command=command,
                                reply=reply,
                                interactive_batch=interactive_batch,
                            )
                        elif message.get("type") == "audio":
                            # Voice note — see _handle_voice_note. Own branch,
                            # not folded into the text/interactive dispatch
                            # above, since an audio message needs a download
                            # + transcribe step before it has any `text` for
                            # _handle_text_message to read at all.
                            await _handle_voice_note(
                                db, company, sender, message, inbound_event.id
                            )
                        elif message.get("type") == "image":
                            # Invoice-photo OCR pre-fill (SPEC V0.3/Future) —
                            # see _handle_invoice_photo. Own branch, not
                            # folded into the text/interactive ladder above,
                            # since an image carries no text body for any of
                            # those handlers to read.
                            await _send_reply_and_log(
                                db,
                                company,
                                sender,
                                notification_type="invoice_photo",
                                reply=await _handle_invoice_photo(db, company, message),
                                command=None,
                                correlation_id=inbound_event.id,
                            )
                        else:
                            # Any other message type (documents, video,
                            # stickers, location, contacts, …) previously got
                            # total silence — no reply of any kind,
                            # indistinguishable from the message never having
                            # arrived. A deterministic "can't read this yet"
                            # reply closes that gap the same way image/audio
                            # handling already does above; actually
                            # supporting any of these remaining types is
                            # separate, unbuilt scope.
                            loc = resolve_locale(company)
                            await _send_reply_and_log(
                                db,
                                company,
                                sender,
                                notification_type="unsupported_message_type",
                                reply=t("workflow.unsupported_message_type", loc),
                                command=None,
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
