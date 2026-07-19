"""Guided WhatsApp onboarding — SPEC extension (onboarding.md).

A resumable, one-field-at-a-time setup conversation for a newly-activated
self-serve company. Same contract and layering as
app/services/followup.py's handle_follow_up_reply: this only advances
Company.onboarding_state (+ onboarding_scratch) and adds rows — it never
commits; the webhook commits once. State persists, so a distributor can leave
and resume mid-flow at any time.

Order (each field is collected only because a real feature consumes it — see
the data-purpose audit in the plan): business type -> products -> dealers ->
suppliers -> opening cash -> outstanding receivables -> outstanding payables ->
briefing time -> completed. Everything is deterministic (no LLM); the free-form
natural-language assistant is a separate module (app/services/assistant.py)
that only runs once onboarding is completed.

Two typed commands work from any in-flight business-setup state (not the
language pre-step): "progress"/"status" shows an 8-section checklist + %
complete so a distributor returning after a break can reorient without
scrolling back through the chat; "restart" (confirm-gated) wipes everything
this conversation has created so far and starts the 8 steps over, for anyone
who'd rather begin fresh than continue with what they've already entered.

Right after GST setup, _after_gst checks whether the company already has
data from the website's "seed from an existing export" step (POST /onboard/
{id}/import, run before WhatsApp ever starts) — products, dealers, suppliers,
or receivable/payable invoices. Nothing imported -> straight to the normal
products question. Anything imported -> one consolidated import_confirm
("here's what we found, correct?") instead of a note per section; either
answer then skips exactly the imported sections and still asks normally for
whatever wasn't, via the same skip-or-ask chain the answer routes through.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import Locale, compose_locale, resolve_locale, t
from app.i18n.languages import get_locale
from app.models.company import Company, OnboardingState
from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceDirection, InvoiceSource, InvoiceStatus
from app.models.product import Product
from app.models.supplier import Supplier
from app.services.followup import _parse_relative_date
from app.services.gst import parse_gst_rate
from app.services.importer.normalizer import parse_amount
from app.services.importer.parties import find_or_create_party, find_party
from app.services.money_format import format_inr
from app.services.party_outstanding import calculate_outstanding_for_company
from app.services.snapshot import business_now

# Language/script is picked *first* (a pre-step), so every question after it is
# shown in the distributor's chosen locale. The 8 numbered steps below are the
# business fields; the language pre-step isn't numbered.
_TOTAL_STEPS = 8

# The briefing hour also gates the notification window (scheduler only runs
# checks from this hour on), so it's clamped to sane morning hours rather than
# any 0-23 — a briefing at 00:00 or 23:00 would distort that gate.
_MIN_BRIEFING_HOUR = 5
_MAX_BRIEFING_HOUR = 11

# ── Language & script selection (asked first) ────────────────────────────────
# Step 1 lists the three languages self-explanatorily (each in its own script).
# Step 2 (Hindi/Odia only) picks native script vs Romanized, showing a sample of
# each — Romanized is the recommended default since most WhatsApp users here
# type that way. The composite locale code (en / hi-Deva / hi-Latn / or-Orya /
# or-Latn) is stored in Company.preferred_language.
_LANGUAGE_BY_CHOICE = {"1": "en", "2": "hi", "3": "or"}
_LANGUAGE_BY_WORD = {"english": "en", "hindi": "hi", "odia": "or", "oriya": "or"}
_NATIVE_WORDS = {"2", "native", "script", "native script"}
_ROMANIZED_WORDS = {"1", "romanized", "roman", "", "default", "english letters"}

_LANGUAGE_PROMPT = (
    "👋 Welcome to OpsGenie!\n\n"
    "First, which language should I message you in?\n"
    "1. English\n"
    "2. हिंदी (Hindi)\n"
    "3. ଓଡ଼ିଆ (Odia)"
)


def _script_prompt(language: str) -> str:
    romanized = get_locale(compose_locale(language, romanized=True))
    native = get_locale(compose_locale(language, romanized=False))
    return (
        "How would you like your messages?\n\n"
        f"1. Romanized (recommended)\n   {romanized.native_display}\n\n"
        f"2. Native script\n   {native.native_display}"
    )


def start_language_change(company: Company) -> str:
    """Post-onboarding switch: re-enter the same language/script selection for
    an already-completed company (triggered by "change language"). A
    `relanguage` scratch flag tells the selection handlers to return to
    `completed` with a confirmation instead of continuing into business setup.
    """
    company.onboarding_state = OnboardingState.awaiting_language
    company.onboarding_scratch = {"relanguage": True}
    return _LANGUAGE_PROMPT


def _after_language_selected(company: Company, scratch: dict) -> str:
    """Shared tail of both selection steps: either finish a post-onboarding
    language change (back to `completed`, confirm in the new locale) or hand off
    into the first real onboarding question.
    """
    relanguage = scratch.get("relanguage")
    company.onboarding_scratch = None
    locale = resolve_locale(company)
    if relanguage:
        company.onboarding_state = OnboardingState.completed
        return t("onboarding.language_changed", locale, language=locale.display_name)
    company.onboarding_state = OnboardingState.awaiting_business_type
    return t("onboarding.intro", locale)


def _progress(step: int, loc: Locale) -> str:
    return t("onboarding.progress", loc, step=step, total=_TOTAL_STEPS)


def _finish_message(loc: Locale) -> str:
    return t("onboarding.finish", loc)


def _is(word: str, *options: str) -> bool:
    return word.strip().lower() in options


def _format_quantity(quantity: Decimal) -> str:
    """Render a stock quantity without parse_amount's forced 2-decimal padding
    (e.g. Decimal("100.00") -> "100").

    Only fractional trailing zeros are stripped — a whole-number Decimal whose
    string form carries no decimal point (Decimal("50") -> "50", not the
    "50".rstrip("0") == "5" a blanket strip would produce) must be left
    intact. Every current caller passes a DB Numeric(14,4) or parse_amount's
    2-decimal output (both always have a "."), but this helper must stay
    correct for a bare whole Decimal too rather than depend on that invariant.
    """
    text = format(quantity, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


# ── Bulk entry (products, dealers, suppliers) ────────────────────────────────
# A distributor pasting a whole price list (e.g. "Rice - 400, Dal - 450") in
# one message used to be swallowed whole as a single product *name* by the
# one-at-a-time flow below — this gives bulk pasting its own parser so each
# item is matched and saved as its own row. The same bulk-vs-one-by-one choice
# and parser shape is reused for dealers and suppliers further down (their
# lines just carry fewer fields: Name, Phone, Credit Days).

_BULK_MODE_WORDS = {"bulk", "all at once", "at once", "together", "list", "in bulk"}
_ONE_BY_ONE_MODE_WORDS = {"one by one", "one at a time", "individually", "single", "one"}

_SKIP_FIELD_WORDS = {"skip", "none", "-", ""}


def _classify_entry_mode(text: str) -> str | None:
    normalized = text.strip().lower()
    if normalized in _BULK_MODE_WORDS:
        return "bulk"
    if normalized in _ONE_BY_ONE_MODE_WORDS:
        return "one_by_one"
    return None


def _bulk_field(parts: list[str], index: int) -> str | None:
    """The raw text of a positional field, or None if absent/short-line/
    explicitly skipped."""
    if index >= len(parts):
        return None
    value = parts[index].strip()
    return None if value.lower() in _SKIP_FIELD_WORDS else value


def _parse_bulk_line(line: str) -> dict:
    """Parse one "Name, Purchase Price, Selling Price, Unit, Stock, GST%"
    line. Raises ValueError (with a message naming the offending field) on
    any present-but-unparseable numeric field — a bad line is rejected
    outright rather than silently dropped or half-saved.
    """
    parts = line.split(",")
    name = parts[0].strip() if parts else ""
    if not name:
        raise ValueError(f"'{line}' has no product name")

    purchase_raw = _bulk_field(parts, 1)
    selling_raw = _bulk_field(parts, 2)
    unit = _bulk_field(parts, 3)
    stock_raw = _bulk_field(parts, 4)
    gst_raw = _bulk_field(parts, 5)

    try:
        purchase_price = parse_amount(purchase_raw) if purchase_raw else None
    except ValueError as exc:
        raise ValueError(f"'{name}': purchase price — {exc}") from exc
    try:
        selling_price = parse_amount(selling_raw) if selling_raw else None
    except ValueError as exc:
        raise ValueError(f"'{name}': selling price — {exc}") from exc
    try:
        stock = parse_amount(stock_raw) if stock_raw else Decimal("0")
    except ValueError as exc:
        raise ValueError(f"'{name}': stock — {exc}") from exc
    try:
        gst_rate = parse_gst_rate(gst_raw) if gst_raw else None
    except ValueError as exc:
        raise ValueError(f"'{name}': GST — {exc}") from exc

    return {
        "name": name,
        "purchase_price": purchase_price,
        "selling_price": selling_price,
        "unit": unit,
        "stock": stock,
        "gst_rate": gst_rate,
    }


def _parse_bulk_party_line(line: str) -> dict:
    """Parse one "Name, Phone, Credit Days" line — the dealer/supplier bulk
    entry format, shared by both since Dealer and Supplier collect the same
    three fields one-by-one. Raises ValueError (naming the offending field)
    on a present-but-unparseable credit-days value — same fail-fast contract
    as _parse_bulk_line.
    """
    parts = line.split(",")
    name = parts[0].strip() if parts else ""
    if not name:
        raise ValueError(f"'{line}' has no name")

    phone = _bulk_field(parts, 1)
    credit_raw = _bulk_field(parts, 2)
    credit_days = None
    if credit_raw:
        try:
            credit_days = int(credit_raw)
        except ValueError as exc:
            raise ValueError(f"'{name}': credit days — send a whole number, e.g. 15") from exc

    return {"name": name, "phone": phone, "credit_days": credit_days}


def _describe_product(name: str, price: Decimal | None, unit: str | None = None) -> str:
    bits = [format_inr(price)] if price is not None else []
    if unit:
        bits.append(unit)
    return f"{name} ({', '.join(bits)})" if bits else name


def _finalize_one_by_one_product(
    db: AsyncSession,
    company: Company,
    scratch: dict,
    purchase_price: Decimal | None,
    gst_rate: Decimal | None,
    loc: Locale,
) -> str:
    """Creates the Product row from the one-by-one loop's accumulated
    scratch fields — the loop's single terminal point, reached either
    directly after purchase price (gst_varies_by_product False) or after the
    extra GST question (True). Loops back to product_awaiting_name either
    way.
    """
    name = scratch.get("name", "Product")
    quantity = Decimal(scratch.get("quantity", "0"))
    unit = scratch.get("unit")
    price_raw = scratch.get("price")
    price = Decimal(price_raw) if price_raw is not None else None
    db.add(
        Product(
            company_id=company.id,
            name=name,
            stock_quantity=quantity,
            unit=unit,
            selling_price=price,
            purchase_price=purchase_price,
            gst_rate=gst_rate,
        )
    )
    company.onboarding_scratch = None
    company.onboarding_state = OnboardingState.product_awaiting_name
    unit_suffix = f" {unit}" if unit else ""
    stock = f"{_format_quantity(quantity)}{unit_suffix}"
    return t("onboarding.product.added", loc, name=name, stock=stock)


def _product_intro(loc: Locale) -> str:
    return f"{_progress(1, loc)}\n\n{t('onboarding.product.intro', loc)}"


def _bulk_format_message(company: Company, loc: Locale) -> str:
    """The bulk-paste format instructions, with a GST% column only when GST
    varies by product. When it's the same for every product (or "not sure"),
    the company already has that answer from gst_mode_ask/gst_rate_same
    (or will set it later via "update gst") — asking again per product here
    would be the exact redundant re-ask the one-by-one flow already avoids
    (see the `company.gst_varies_by_product` check at
    product_awaiting_purchase_price below).
    """
    key = (
        "onboarding.product.bulk_format"
        if company.gst_varies_by_product
        else "onboarding.product.bulk_format_no_gst"
    )
    return t(key, loc)


# ── Skip already-imported sections ───────────────────────────────────────────
# A distributor who used the website's "seed from an existing export" step
# (app/api/onboarding.py's POST /onboard/{id}/import, run before WhatsApp
# ever starts) arrives here with Product/Dealer/Supplier/Invoice rows already
# in place before this state machine's products/dealers/suppliers/
# receivable/payable sections would otherwise ask for them one at a time.
# _after_gst (below, right after GST setup — the last question that doesn't
# depend on import data) checks all five at once and, if anything was
# imported, shows ONE consolidated confirmation instead of scattering a
# "found N" note through every section. Once confirmed either way, each
# _after_* helper below checks its own section's row count exactly once,
# right at the moment that section would start, and skips silently — a
# company with no import (the common case) always sees count 0 at every one
# of these checkpoints (the section's own loop is what would create rows,
# and it hasn't run yet), so this whole chain is a no-op for everyone else.


async def _count(db: AsyncSession, model, company_id: uuid.UUID) -> int:
    stmt = select(func.count()).select_from(model).where(model.company_id == company_id)
    return await db.scalar(stmt) or 0


async def _invoice_count(
    db: AsyncSession, company_id: uuid.UUID, direction: InvoiceDirection
) -> int:
    stmt = (
        select(func.count())
        .select_from(Invoice)
        .where(Invoice.company_id == company_id, Invoice.direction == direction)
    )
    return await db.scalar(stmt) or 0


def _after_suppliers(company: Company, loc: Locale) -> str:
    company.onboarding_state = OnboardingState.awaiting_opening_balance
    return f"{_progress(4, loc)}\n\n{t('onboarding.opening.ask', loc)}"


async def _after_dealers(db: AsyncSession, company: Company, loc: Locale) -> str:
    supplier_count = await _count(db, Supplier, company.id)
    if supplier_count:
        return _after_suppliers(company, loc)
    company.onboarding_state = OnboardingState.supplier_awaiting_mode
    return f"{_progress(3, loc)}\n\n{t('onboarding.suppliers.intro', loc)}"


async def _after_products(db: AsyncSession, company: Company, loc: Locale) -> str:
    dealer_count = await _count(db, Dealer, company.id)
    if dealer_count:
        return await _after_dealers(db, company, loc)
    company.onboarding_state = OnboardingState.dealer_awaiting_mode
    return f"{_progress(2, loc)}\n\n{t('onboarding.dealers.intro', loc)}"


async def _after_receivables(db: AsyncSession, company: Company, loc: Locale) -> str:
    payable_count = await _invoice_count(db, company.id, InvoiceDirection.payable)
    if payable_count:
        company.onboarding_state = OnboardingState.awaiting_briefing_hour
        return f"{_progress(7, loc)}\n\n{t('onboarding.briefing.ask', loc)}"
    company.onboarding_state = OnboardingState.payable_ask
    return f"{_progress(6, loc)}\n\n{t('onboarding.payable.ask', loc)}"


async def _after_opening_balance(db: AsyncSession, company: Company, loc: Locale) -> str:
    receivable_count = await _invoice_count(db, company.id, InvoiceDirection.receivable)
    if receivable_count:
        return await _after_receivables(db, company, loc)
    company.onboarding_state = OnboardingState.receivable_ask
    return f"{_progress(5, loc)}\n\n{t('onboarding.receivable.ask', loc)}"


async def _route_past_import(db: AsyncSession, company: Company, loc: Locale) -> str:
    """The tail both import_confirm answers share: check products (the one
    category _after_gst itself doesn't hand off to a _after_* sibling for),
    then fall into the same skip-or-ask chain _after_products already uses
    for dealers/suppliers/receivables/payables.
    """
    product_count = await _count(db, Product, company.id)
    if product_count:
        return await _after_products(db, company, loc)
    company.onboarding_state = OnboardingState.product_awaiting_mode
    return _product_intro(loc)


async def _import_summary_counts(db: AsyncSession, company: Company) -> dict[str, object]:
    receivable_count = await _invoice_count(db, company.id, InvoiceDirection.receivable)
    payable_count = await _invoice_count(db, company.id, InvoiceDirection.payable)
    receivable_total = Decimal("0.00")
    payable_total = Decimal("0.00")
    if receivable_count:
        by_party = await calculate_outstanding_for_company(
            db, company_id=company.id, direction="receivable"
        )
        receivable_total = sum(by_party.values(), Decimal("0.00"))
    if payable_count:
        by_party = await calculate_outstanding_for_company(
            db, company_id=company.id, direction="payable"
        )
        payable_total = sum(by_party.values(), Decimal("0.00"))
    return {
        "product": await _count(db, Product, company.id),
        "dealer": await _count(db, Dealer, company.id),
        "supplier": await _count(db, Supplier, company.id),
        "receivable": receivable_count,
        "receivable_total": receivable_total,
        "payable": payable_count,
        "payable_total": payable_total,
    }


def _import_confirm_prompt(loc: Locale, counts: dict[str, object]) -> str:
    lines = []
    if counts["product"]:
        lines.append(t("onboarding.import_confirm.line_products", loc, count=counts["product"]))
    if counts["dealer"]:
        lines.append(t("onboarding.import_confirm.line_dealers", loc, count=counts["dealer"]))
    if counts["supplier"]:
        lines.append(t("onboarding.import_confirm.line_suppliers", loc, count=counts["supplier"]))
    if counts["receivable"]:
        lines.append(
            t(
                "onboarding.import_confirm.line_receivables",
                loc,
                count=counts["receivable"],
                amount=format_inr(counts["receivable_total"]),
            )
        )
    if counts["payable"]:
        lines.append(
            t(
                "onboarding.import_confirm.line_payables",
                loc,
                count=counts["payable"],
                amount=format_inr(counts["payable_total"]),
            )
        )
    title = t("onboarding.import_confirm.title", loc)
    ask = t("onboarding.import_confirm.ask", loc)
    return f"{title}\n\n" + "\n".join(lines) + f"\n\n{ask}"


async def _after_gst(db: AsyncSession, company: Company, loc: Locale) -> str:
    """Where products would normally start — the first point at which every
    website-import category (products/dealers/suppliers/receivables/
    payables, all seeded before WhatsApp ever starts) is known. Nothing
    imported -> the normal products question. Anything imported -> one
    consolidated confirmation before the skip chain runs, so a distributor
    only ever gets asked "is this correct?" once, not once per section.
    """
    counts = await _import_summary_counts(db, company)
    imported_anything = any(
        [
            counts["product"],
            counts["dealer"],
            counts["supplier"],
            counts["receivable"],
            counts["payable"],
        ]
    )
    if not imported_anything:
        company.onboarding_state = OnboardingState.product_awaiting_mode
        return _product_intro(loc)
    company.onboarding_state = OnboardingState.import_confirm
    return _import_confirm_prompt(loc, counts)


# ── Resume: progress checklist & restart (any in-flight business-setup state) ─
# The state machine above is already resumable by construction — it's all
# durable Company columns, so a distributor can close WhatsApp mid-flow and
# reply days later and just pick up where they left off. What's missing is
# visibility (which step am I on, out of how many) and an escape hatch (what
# if I don't want to continue with what I've already entered and would rather
# start clean). Both are typed commands, same convention as "done"/"skip"/
# "bulk" elsewhere in this file — English trigger words regardless of locale,
# only the replies are localized.
_PROGRESS_WORDS = {"progress", "status"}
_RESTART_WORDS = {"restart", "start over", "start fresh", "reset"}

# Every state gets grouped under one of the 8 numbered sections so the
# checklist can mark it done / current / pending. Deliberately exhaustive
# (every non-language, non-terminal OnboardingState member appears exactly
# once) rather than a fallback default — a state silently missing from this
# map would make the checklist misreport progress instead of failing loudly.
_SECTION_KEYS: list[tuple[int, str]] = [
    (1, "onboarding.section.business_type"),
    (2, "onboarding.section.products"),
    (3, "onboarding.section.dealers"),
    (4, "onboarding.section.suppliers"),
    (5, "onboarding.section.opening_balance"),
    (6, "onboarding.section.receivables"),
    (7, "onboarding.section.payables"),
    (8, "onboarding.section.briefing_hour"),
]

_STEP_OF_STATE: dict[OnboardingState, int] = {
    OnboardingState.awaiting_business_type: 1,
    OnboardingState.gst_mode_ask: 1,
    OnboardingState.gst_rate_same: 1,
    OnboardingState.import_confirm: 1,
    OnboardingState.product_awaiting_mode: 2,
    OnboardingState.product_awaiting_bulk: 2,
    OnboardingState.product_awaiting_bulk_unit: 2,
    OnboardingState.product_awaiting_bulk_purchase_price: 2,
    OnboardingState.product_awaiting_name: 2,
    OnboardingState.product_awaiting_quantity: 2,
    OnboardingState.product_awaiting_unit: 2,
    OnboardingState.product_awaiting_price: 2,
    OnboardingState.product_awaiting_purchase_price: 2,
    OnboardingState.product_awaiting_gst_rate: 2,
    OnboardingState.dealer_awaiting_mode: 3,
    OnboardingState.dealer_awaiting_bulk: 3,
    OnboardingState.dealer_awaiting_name: 3,
    OnboardingState.dealer_awaiting_phone: 3,
    OnboardingState.dealer_awaiting_credit: 3,
    OnboardingState.supplier_awaiting_mode: 4,
    OnboardingState.supplier_awaiting_bulk: 4,
    OnboardingState.supplier_awaiting_name: 4,
    OnboardingState.supplier_awaiting_phone: 4,
    OnboardingState.supplier_awaiting_credit: 4,
    OnboardingState.awaiting_opening_balance: 5,
    OnboardingState.receivable_ask: 6,
    OnboardingState.receivable_dealer: 6,
    OnboardingState.receivable_new_party_confirm: 6,
    OnboardingState.receivable_amount: 6,
    OnboardingState.receivable_date: 6,
    OnboardingState.payable_ask: 7,
    OnboardingState.payable_supplier: 7,
    OnboardingState.payable_new_party_confirm: 7,
    OnboardingState.payable_amount: 7,
    OnboardingState.payable_date: 7,
    OnboardingState.awaiting_briefing_hour: 8,
}

# Only the states whose prompt is a static (or company-mode-dependent, not
# scratch-dependent) string can be safely re-shown verbatim — the same t()
# key/helper the original question used. Mid-entry states (e.g. "what unit is
# this measured in?" mid product-loop) depend on scratch fields typed earlier
# in that sub-conversation; _reprompt falls back to a generic continue line
# for those rather than half-reconstructing them.
_STATIC_REPROMPT_KEY: dict[OnboardingState, str] = {
    OnboardingState.gst_mode_ask: "onboarding.gst.mode_ask",
    OnboardingState.gst_rate_same: "onboarding.gst.rate_ask",
    OnboardingState.product_awaiting_name: "onboarding.product.first_name",
    OnboardingState.dealer_awaiting_mode: "onboarding.dealers.intro",
    OnboardingState.dealer_awaiting_bulk: "onboarding.dealer.bulk_format",
    OnboardingState.dealer_awaiting_name: "onboarding.dealer.first_name",
    OnboardingState.supplier_awaiting_mode: "onboarding.suppliers.intro",
    OnboardingState.supplier_awaiting_bulk: "onboarding.supplier.bulk_format",
    OnboardingState.supplier_awaiting_name: "onboarding.supplier.first_name",
    OnboardingState.awaiting_opening_balance: "onboarding.opening.ask",
    OnboardingState.receivable_ask: "onboarding.receivable.ask",
    OnboardingState.payable_ask: "onboarding.payable.ask",
    OnboardingState.awaiting_briefing_hour: "onboarding.briefing.ask",
}


def _reprompt(company: Company, state: OnboardingState, loc: Locale) -> str | None:
    """The current question, re-shown verbatim — or None if `state` is a
    mid-entry sub-step with no safe static re-ask (caller falls back to a
    generic continue line)."""
    if state == OnboardingState.product_awaiting_mode:
        # Not _product_intro() — that prefixes the "Step 1 of 8 done" line
        # the checklist above already shows; here just the question itself.
        return t("onboarding.product.intro", loc)
    if state == OnboardingState.product_awaiting_bulk:
        return _bulk_format_message(company, loc)
    key = _STATIC_REPROMPT_KEY.get(state)
    return t(key, loc) if key else None


def _checklist_reply(company: Company, state: OnboardingState, loc: Locale) -> str:
    current_step = _STEP_OF_STATE.get(state, _TOTAL_STEPS)
    lines = []
    for step, key in _SECTION_KEYS:
        name = t(key, loc)
        if step < current_step:
            status_key = "onboarding.status.section_done"
        elif step == current_step:
            status_key = "onboarding.status.section_current"
        else:
            status_key = "onboarding.status.section_pending"
        lines.append(t(status_key, loc, name=name))
    percent = round((current_step - 1) / _TOTAL_STEPS * 100)
    header = t("onboarding.status.title", loc, percent=percent)
    footer = _reprompt(company, state, loc) or t("onboarding.status.footer_generic", loc)
    return (
        f"{header}\n\n"
        + "\n".join(lines)
        + f"\n\n{footer}\n\n{t('onboarding.status.restart_hint', loc)}"
    )


async def _wipe_business_setup(db: AsyncSession, company: Company) -> None:
    """Erase everything the guided setup has created so far and reset the
    business fields it collects, for the "restart" confirm's "yes" branch.

    Invoices must be deleted before dealers/suppliers: Invoice.dealer_id/
    supplier_id are ON DELETE SET NULL (not CASCADE — see app/models/
    invoice.py), so deleting the party first would silently orphan its
    opening-balance invoice instead of removing it. Deleting Invoice first
    cascades InvoiceItem and Payment for free.
    """
    await db.execute(delete(Invoice).where(Invoice.company_id == company.id))
    await db.execute(delete(Dealer).where(Dealer.company_id == company.id))
    await db.execute(delete(Supplier).where(Supplier.company_id == company.id))
    await db.execute(delete(Product).where(Product.company_id == company.id))
    company.business_type = None
    company.gst_rate = Decimal("0")
    company.gst_varies_by_product = False
    company.opening_balance = Decimal("0")
    company.briefing_hour = None


async def handle_onboarding_message(db: AsyncSession, company: Company, text: str) -> str:
    """Advance the guided setup by one message and return the reply. Only
    mutates state/rows — the caller commits.
    """
    state = company.onboarding_state
    stripped = text.strip()
    scratch = dict(company.onboarding_scratch or {})
    # Business-setup prompts below render in the company's chosen locale. The
    # language/script picker itself stays English (it runs before a locale is
    # chosen, and shows each option in its own native script).
    loc = resolve_locale(company)

    # ── Kick-off → language first, so the rest is shown in the chosen locale ──
    if state == OnboardingState.not_started:
        company.onboarding_state = OnboardingState.awaiting_language
        return _LANGUAGE_PROMPT

    # ── Language (step 1 of 2) ───────────────────────────────────────────────
    if state == OnboardingState.awaiting_language:
        choice = stripped.lower()
        language = _LANGUAGE_BY_CHOICE.get(choice) or _LANGUAGE_BY_WORD.get(choice)
        if language is None:
            return "Please reply 1 (English), 2 (Hindi), or 3 (Odia)."
        if language == "en":
            company.preferred_language = "en"
            return _after_language_selected(company, scratch)
        scratch["onb_language"] = language
        company.onboarding_scratch = scratch
        company.onboarding_state = OnboardingState.awaiting_script
        return _script_prompt(language)

    # ── Script / display style (step 2 of 2, Hindi/Odia only) ────────────────
    if state == OnboardingState.awaiting_script:
        language = scratch.get("onb_language", "hi")
        choice = stripped.lower()
        if choice in _NATIVE_WORDS:
            romanized = False
        elif choice in _ROMANIZED_WORDS:
            romanized = True  # recommended default (incl. a blank reply)
        else:
            return "Please reply 1 (Romanized) or 2 (Native script)."
        company.preferred_language = compose_locale(language, romanized=romanized)
        return _after_language_selected(company, scratch)

    # ── Restart confirm (reached via the "restart" keyword below) ───────────
    if state == OnboardingState.restart_confirm:
        prev_value = scratch.get("restart_prev_state", OnboardingState.awaiting_business_type.value)
        prev_state = OnboardingState(prev_value)
        if _is(stripped, "yes", "y"):
            await _wipe_business_setup(db, company)
            company.onboarding_scratch = None
            company.onboarding_state = OnboardingState.awaiting_business_type
            return t("onboarding.restart.done", loc)
        if _is(stripped, "no", "n"):
            scratch.pop("restart_prev_state", None)
            company.onboarding_scratch = scratch or None
            company.onboarding_state = prev_state
            return t("onboarding.restart.cancelled", loc)
        return t("onboarding.yes_no_invalid", loc)

    # ── Cross-cutting: progress checklist & restart, any in-flight
    # business-setup state. Checked ahead of every per-field handler below so
    # neither word is ever swallowed as data (e.g. a dealer name) — same
    # precedence "done"/"skip" already get.
    if state in _STEP_OF_STATE:
        if _is(stripped, *_RESTART_WORDS):
            scratch["restart_prev_state"] = state.value
            company.onboarding_scratch = scratch
            company.onboarding_state = OnboardingState.restart_confirm
            return t("onboarding.restart.confirm", loc)
        if _is(stripped, *_PROGRESS_WORDS):
            return _checklist_reply(company, state, loc)

    # ── 1. Business type ─────────────────────────────────────────────────────
    if state == OnboardingState.awaiting_business_type:
        company.business_type = stripped
        company.onboarding_state = OnboardingState.gst_mode_ask
        return t("onboarding.gst.mode_ask", loc)

    if state == OnboardingState.gst_mode_ask:
        if _is(stripped, "not sure", "skip", "later"):
            return await _after_gst(db, company, loc)
        if _is(stripped, "varies", "vary"):
            company.gst_varies_by_product = True
            return await _after_gst(db, company, loc)
        if _is(stripped, "same"):
            company.onboarding_state = OnboardingState.gst_rate_same
            return t("onboarding.gst.rate_ask", loc)
        return t("onboarding.gst.mode_invalid", loc)

    if state == OnboardingState.gst_rate_same:
        if _is(stripped, "not sure", "skip", "later"):
            return await _after_gst(db, company, loc)
        try:
            rate = parse_gst_rate(stripped)
        except ValueError:
            return t("onboarding.gst.rate_invalid", loc)
        company.gst_rate = rate
        company.gst_varies_by_product = False
        return await _after_gst(db, company, loc)

    # ── Import confirm (reached from _after_gst when a website import left ──
    # ── products/dealers/suppliers/receivables/payables already in place) ───
    if state == OnboardingState.import_confirm:
        if _is(stripped, "yes", "y"):
            return await _route_past_import(db, company, loc)
        if _is(stripped, "no", "n"):
            note = t("onboarding.import_confirm.no_ack", loc)
            return f"{note}\n\n{await _route_past_import(db, company, loc)}"
        return t("onboarding.yes_no_invalid", loc)

    # ── 2. Products (name -> stock quantity, repeatable, or bulk paste) ──────
    if state == OnboardingState.product_awaiting_mode:
        if _is(stripped, "done", "skip"):
            return await _after_products(db, company, loc)
        mode = _classify_entry_mode(stripped)
        if mode == "bulk":
            company.onboarding_state = OnboardingState.product_awaiting_bulk
            return _bulk_format_message(company, loc)
        if mode == "one_by_one":
            company.onboarding_state = OnboardingState.product_awaiting_name
            return t("onboarding.product.first_name", loc)
        return t("onboarding.product.mode_invalid", loc)

    if state == OnboardingState.product_awaiting_bulk:
        if _is(stripped, "done", "skip"):
            return await _after_products(db, company, loc)
        lines = [line for line in stripped.splitlines() if line.strip()]
        if not lines:
            return _bulk_format_message(company, loc)
        parsed_items = []
        for line in lines:
            try:
                parsed_items.append(_parse_bulk_line(line))
            except ValueError as exc:
                return (
                    t("onboarding.bulk_error", loc, error=exc)
                    + "\n\n"
                    + _bulk_format_message(company, loc)
                )
        for item in parsed_items:
            db.add(
                Product(
                    company_id=company.id,
                    name=item["name"],
                    stock_quantity=item["stock"],
                    unit=item["unit"],
                    selling_price=item["selling_price"],
                    purchase_price=item["purchase_price"],
                    gst_rate=item["gst_rate"],
                )
            )
        names = ", ".join(
            _describe_product(item["name"], item["selling_price"], item["unit"])
            for item in parsed_items
        )
        return t("onboarding.product.bulk_added", loc, count=len(parsed_items), names=names)

    if state == OnboardingState.product_awaiting_name:
        if _is(stripped, "done", "skip"):
            return await _after_products(db, company, loc)
        company.onboarding_scratch = {"name": stripped}
        company.onboarding_state = OnboardingState.product_awaiting_quantity
        return t("onboarding.product.quantity_ask", loc, name=stripped)

    if state == OnboardingState.product_awaiting_quantity:
        quantity = Decimal("0")
        if not _is(stripped, "skip"):
            try:
                quantity = parse_amount(stripped)
            except ValueError:
                return t("onboarding.product.quantity_invalid", loc)
        scratch["quantity"] = str(quantity)
        company.onboarding_scratch = scratch
        company.onboarding_state = OnboardingState.product_awaiting_unit
        return t("onboarding.product.unit", loc)

    if state == OnboardingState.product_awaiting_unit:
        unit = None if _is(stripped, "skip") else stripped
        scratch["unit"] = unit
        company.onboarding_scratch = scratch
        company.onboarding_state = OnboardingState.product_awaiting_price
        name = scratch.get("name", "this product")
        return t("onboarding.product.price_ask", loc, name=name)

    if state == OnboardingState.product_awaiting_price:
        price = None
        if not _is(stripped, "skip"):
            try:
                price = parse_amount(stripped)
            except ValueError:
                return t("onboarding.product.price_invalid", loc)
        scratch["price"] = str(price) if price is not None else None
        company.onboarding_scratch = scratch
        company.onboarding_state = OnboardingState.product_awaiting_purchase_price
        name = scratch.get("name", "this product")
        return t("onboarding.product.purchase_ask", loc, name=name)

    if state == OnboardingState.product_awaiting_purchase_price:
        purchase_price = None
        if not _is(stripped, "skip", "done"):
            try:
                purchase_price = parse_amount(stripped)
            except ValueError:
                return t("onboarding.product.purchase_invalid", loc)
        if company.gst_varies_by_product:
            scratch["purchase_price"] = str(purchase_price) if purchase_price is not None else None
            company.onboarding_scratch = scratch
            company.onboarding_state = OnboardingState.product_awaiting_gst_rate
            name = scratch.get("name", "this product")
            return t("onboarding.product.gst_ask", loc, name=name)
        return _finalize_one_by_one_product(db, company, scratch, purchase_price, None, loc)

    if state == OnboardingState.product_awaiting_gst_rate:
        gst_rate = None
        if not _is(stripped, "skip", "not sure", "done"):
            try:
                gst_rate = parse_gst_rate(stripped)
            except ValueError:
                return t("onboarding.product.gst_invalid", loc)
        purchase_price_raw = scratch.get("purchase_price")
        purchase_price = Decimal(purchase_price_raw) if purchase_price_raw is not None else None
        return _finalize_one_by_one_product(db, company, scratch, purchase_price, gst_rate, loc)

    # ── 3. Dealers (mode -> name -> phone -> credit days, repeatable, or bulk) ─
    if state == OnboardingState.dealer_awaiting_mode:
        if _is(stripped, "done", "skip"):
            return await _after_dealers(db, company, loc)
        mode = _classify_entry_mode(stripped)
        if mode == "bulk":
            company.onboarding_state = OnboardingState.dealer_awaiting_bulk
            return t("onboarding.dealer.bulk_format", loc)
        if mode == "one_by_one":
            company.onboarding_state = OnboardingState.dealer_awaiting_name
            return t("onboarding.dealer.first_name", loc)
        return t("onboarding.dealer.mode_invalid", loc)

    if state == OnboardingState.dealer_awaiting_bulk:
        if _is(stripped, "done", "skip"):
            return await _after_dealers(db, company, loc)
        lines = [line for line in stripped.splitlines() if line.strip()]
        if not lines:
            return t("onboarding.dealer.bulk_format", loc)
        parsed_items = []
        for line in lines:
            try:
                parsed_items.append(_parse_bulk_party_line(line))
            except ValueError as exc:
                return (
                    t("onboarding.bulk_error", loc, error=exc)
                    + "\n\n"
                    + t("onboarding.dealer.bulk_format", loc)
                )
        for item in parsed_items:
            db.add(
                Dealer(
                    company_id=company.id,
                    name=item["name"],
                    phone=item["phone"],
                    payment_terms_days=item["credit_days"],
                )
            )
        names = ", ".join(item["name"] for item in parsed_items)
        return t("onboarding.dealer.bulk_added", loc, count=len(parsed_items), names=names)

    if state == OnboardingState.dealer_awaiting_name:
        if _is(stripped, "done", "skip"):
            return await _after_dealers(db, company, loc)
        company.onboarding_scratch = {"name": stripped}
        company.onboarding_state = OnboardingState.dealer_awaiting_phone
        return t("onboarding.party.phone_ask", loc, name=stripped)

    if state == OnboardingState.dealer_awaiting_phone:
        if not _is(stripped, "skip"):
            scratch["phone"] = stripped
        company.onboarding_scratch = scratch
        company.onboarding_state = OnboardingState.dealer_awaiting_credit
        name = scratch.get("name", "them")
        return t("onboarding.dealer.credit_ask", loc, name=name)

    if state == OnboardingState.dealer_awaiting_credit:
        credit = None
        if not _is(stripped, "skip"):
            try:
                credit = int(stripped)
            except ValueError:
                return t("onboarding.party.credit_invalid", loc)
        name = scratch.get("name", "Dealer")
        db.add(
            Dealer(
                company_id=company.id,
                name=name,
                phone=scratch.get("phone"),
                payment_terms_days=credit,
            )
        )
        company.onboarding_scratch = None
        company.onboarding_state = OnboardingState.dealer_awaiting_name
        return t("onboarding.dealer.added", loc, name=name)

    # ── 4. Suppliers (same shape as dealers, mode -> name/bulk) ──────────────
    if state == OnboardingState.supplier_awaiting_mode:
        if _is(stripped, "done", "skip"):
            company.onboarding_state = OnboardingState.awaiting_opening_balance
            return f"{_progress(4, loc)}\n\n{t('onboarding.opening.ask', loc)}"
        mode = _classify_entry_mode(stripped)
        if mode == "bulk":
            company.onboarding_state = OnboardingState.supplier_awaiting_bulk
            return t("onboarding.supplier.bulk_format", loc)
        if mode == "one_by_one":
            company.onboarding_state = OnboardingState.supplier_awaiting_name
            return t("onboarding.supplier.first_name", loc)
        return t("onboarding.supplier.mode_invalid", loc)

    if state == OnboardingState.supplier_awaiting_bulk:
        if _is(stripped, "done", "skip"):
            company.onboarding_state = OnboardingState.awaiting_opening_balance
            return f"{_progress(4, loc)}\n\n{t('onboarding.opening.ask', loc)}"
        lines = [line for line in stripped.splitlines() if line.strip()]
        if not lines:
            return t("onboarding.supplier.bulk_format", loc)
        parsed_items = []
        for line in lines:
            try:
                parsed_items.append(_parse_bulk_party_line(line))
            except ValueError as exc:
                return (
                    t("onboarding.bulk_error", loc, error=exc)
                    + "\n\n"
                    + t("onboarding.supplier.bulk_format", loc)
                )
        for item in parsed_items:
            db.add(
                Supplier(
                    company_id=company.id,
                    name=item["name"],
                    phone=item["phone"],
                    payment_terms_days=item["credit_days"],
                )
            )
        names = ", ".join(item["name"] for item in parsed_items)
        return t("onboarding.supplier.bulk_added", loc, count=len(parsed_items), names=names)

    if state == OnboardingState.supplier_awaiting_name:
        if _is(stripped, "done", "skip"):
            company.onboarding_state = OnboardingState.awaiting_opening_balance
            return f"{_progress(4, loc)}\n\n{t('onboarding.opening.ask', loc)}"
        company.onboarding_scratch = {"name": stripped}
        company.onboarding_state = OnboardingState.supplier_awaiting_phone
        return t("onboarding.party.phone_ask", loc, name=stripped)

    if state == OnboardingState.supplier_awaiting_phone:
        if not _is(stripped, "skip"):
            scratch["phone"] = stripped
        company.onboarding_scratch = scratch
        company.onboarding_state = OnboardingState.supplier_awaiting_credit
        return t("onboarding.supplier.credit_ask", loc, name=scratch.get("name", "they"))

    if state == OnboardingState.supplier_awaiting_credit:
        credit = None
        if not _is(stripped, "skip"):
            try:
                credit = int(stripped)
            except ValueError:
                return "Please send a number of days, e.g. 15 (or 'skip')."
        name = scratch.get("name", "Supplier")
        db.add(
            Supplier(
                company_id=company.id,
                name=name,
                phone=scratch.get("phone"),
                payment_terms_days=credit,
            )
        )
        company.onboarding_scratch = None
        company.onboarding_state = OnboardingState.supplier_awaiting_name
        return t("onboarding.supplier.added", loc, name=name)

    # ── 5. Opening cash ──────────────────────────────────────────────────────
    if state == OnboardingState.awaiting_opening_balance:
        try:
            amount = parse_amount(stripped)
        except ValueError:
            return t("onboarding.opening.invalid", loc)
        company.opening_balance = amount
        return await _after_opening_balance(db, company, loc)

    # ── 6. Outstanding receivables ───────────────────────────────────────────
    if state == OnboardingState.receivable_ask:
        if _is(stripped, "no", "skip", "done"):
            return await _after_receivables(db, company, loc)
        if _is(stripped, "yes"):
            company.onboarding_state = OnboardingState.receivable_dealer
            return t("onboarding.receivable.which", loc)
        return t("onboarding.yes_no_invalid", loc)

    if state == OnboardingState.receivable_dealer:
        company.onboarding_scratch = {"party": stripped}
        existing = await find_party(db, company.id, "receivable", stripped)
        if existing is None:
            company.onboarding_state = OnboardingState.receivable_new_party_confirm
            return t("onboarding.receivable.confirm_new", loc, name=stripped)
        company.onboarding_state = OnboardingState.receivable_amount
        return t("onboarding.receivable.amount_ask", loc, party=stripped)

    if state == OnboardingState.receivable_new_party_confirm:
        party = scratch.get("party", "")
        if _is(stripped, "no", "n"):
            company.onboarding_state = OnboardingState.receivable_dealer
            return t("onboarding.receivable.which", loc)
        if not _is(stripped, "yes", "y"):
            return t("onboarding.yes_no_invalid", loc)
        company.onboarding_state = OnboardingState.receivable_amount
        return t("onboarding.receivable.amount_ask", loc, party=party)

    if state == OnboardingState.receivable_amount:
        try:
            amount = parse_amount(stripped)
        except ValueError:
            return t("onboarding.receivable.amount_invalid", loc)
        scratch["amount"] = str(amount)
        company.onboarding_scratch = scratch
        company.onboarding_state = OnboardingState.receivable_date
        party = scratch.get("party", "them")
        return t("onboarding.receivable.date_ask", loc, party=party)

    if state == OnboardingState.receivable_date:
        today = business_now(company.timezone).date()
        due = _parse_relative_date(stripped, today)
        if due is None:
            return t("onboarding.date_invalid", loc)
        party = scratch.get("party", "Dealer")
        amount = Decimal(scratch["amount"])
        dealer = await find_or_create_party(db, company.id, "receivable", party)
        _add_opening_invoice(
            company_id=company.id,
            direction=InvoiceDirection.receivable,
            dealer_id=dealer.id,
            due_date=due,
            amount=amount,
            tz=company.timezone,
            db=db,
        )
        company.onboarding_scratch = None
        company.onboarding_state = OnboardingState.receivable_ask
        return t("onboarding.receivable.recorded", loc, amount=format_inr(amount), party=party)

    # ── 7. Outstanding payables ──────────────────────────────────────────────
    if state == OnboardingState.payable_ask:
        if _is(stripped, "no", "skip", "done"):
            company.onboarding_state = OnboardingState.awaiting_briefing_hour
            return f"{_progress(7, loc)}\n\n{t('onboarding.briefing.ask', loc)}"
        if _is(stripped, "yes"):
            company.onboarding_state = OnboardingState.payable_supplier
            return t("onboarding.payable.which", loc)
        return t("onboarding.yes_no_invalid", loc)

    if state == OnboardingState.payable_supplier:
        company.onboarding_scratch = {"party": stripped}
        existing = await find_party(db, company.id, "payable", stripped)
        if existing is None:
            company.onboarding_state = OnboardingState.payable_new_party_confirm
            return t("onboarding.payable.confirm_new", loc, name=stripped)
        company.onboarding_state = OnboardingState.payable_amount
        return t("onboarding.payable.amount_ask", loc, party=stripped)

    if state == OnboardingState.payable_new_party_confirm:
        party = scratch.get("party", "")
        if _is(stripped, "no", "n"):
            company.onboarding_state = OnboardingState.payable_supplier
            return t("onboarding.payable.which", loc)
        if not _is(stripped, "yes", "y"):
            return t("onboarding.yes_no_invalid", loc)
        company.onboarding_state = OnboardingState.payable_amount
        return t("onboarding.payable.amount_ask", loc, party=party)

    if state == OnboardingState.payable_amount:
        try:
            amount = parse_amount(stripped)
        except ValueError:
            return t("onboarding.payable.amount_invalid", loc)
        scratch["amount"] = str(amount)
        company.onboarding_scratch = scratch
        company.onboarding_state = OnboardingState.payable_date
        party = scratch.get("party", "them")
        return t("onboarding.payable.date_ask", loc, party=party)

    if state == OnboardingState.payable_date:
        today = business_now(company.timezone).date()
        due = _parse_relative_date(stripped, today)
        if due is None:
            return t("onboarding.date_invalid", loc)
        party = scratch.get("party", "Supplier")
        amount = Decimal(scratch["amount"])
        supplier = await find_or_create_party(db, company.id, "payable", party)
        _add_opening_invoice(
            company_id=company.id,
            direction=InvoiceDirection.payable,
            supplier_id=supplier.id,
            due_date=due,
            amount=amount,
            tz=company.timezone,
            db=db,
        )
        company.onboarding_scratch = None
        company.onboarding_state = OnboardingState.payable_ask
        return t("onboarding.payable.recorded", loc, amount=format_inr(amount), party=party)

    # ── 8. Briefing time -> done ─────────────────────────────────────────────
    if state == OnboardingState.awaiting_briefing_hour:
        try:
            hour = int(stripped)
        except ValueError:
            return t("onboarding.briefing.invalid", loc)
        if not _MIN_BRIEFING_HOUR <= hour <= _MAX_BRIEFING_HOUR:
            return t("onboarding.briefing.range", loc)
        company.briefing_hour = hour
        company.onboarding_state = OnboardingState.completed
        return _finish_message(loc)

    # Unreachable in practice (completed is routed away before reaching here),
    # but never leave a company stuck in an unknown state.
    company.onboarding_state = OnboardingState.completed
    return _finish_message(loc)


def _add_opening_invoice(
    *,
    db: AsyncSession,
    company_id: uuid.UUID,
    direction: InvoiceDirection,
    due_date,
    amount: Decimal,
    tz: str,
    dealer_id: uuid.UUID | None = None,
    supplier_id: uuid.UUID | None = None,
) -> None:
    today = business_now(tz).date()
    db.add(
        Invoice(
            company_id=company_id,
            invoice_number=f"ONB-{uuid.uuid4().hex[:10]}",
            direction=direction,
            dealer_id=dealer_id,
            supplier_id=supplier_id,
            invoice_date=today,
            due_date=due_date,
            subtotal=amount,
            gst_amount=Decimal("0.00"),
            total_amount=amount,
            status=InvoiceStatus.Pending,
            source=InvoiceSource.whatsapp,
        )
    )
