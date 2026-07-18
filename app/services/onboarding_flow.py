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
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import compose_locale, resolve_locale, t
from app.i18n.languages import get_locale
from app.models.company import Company, OnboardingState
from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceDirection, InvoiceSource, InvoiceStatus
from app.models.product import Product
from app.models.supplier import Supplier
from app.services.followup import _parse_relative_date
from app.services.gst import parse_gst_rate
from app.services.importer.normalizer import parse_amount
from app.services.importer.parties import find_or_create_party
from app.services.money_format import format_inr
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


_INTRO = (
    "👋 Welcome to OpsGenie! Let's set up your business — it takes about 5 minutes, "
    "and you can stop and continue anytime.\n\n"
    "First: what kind of business do you run? (e.g. FMCG Distributor, Pharma Distributor)"
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
    if relanguage:
        company.onboarding_state = OnboardingState.completed
        locale = resolve_locale(company)
        return t("onboarding.language_changed", locale, language=locale.display_name)
    company.onboarding_state = OnboardingState.awaiting_business_type
    return _INTRO


def _progress(step: int) -> str:
    return f"✅ Step {step} of {_TOTAL_STEPS} done."


def _finish_message() -> str:
    return (
        "🎉 Setup complete!\n\n"
        "From tomorrow morning I'll send you your daily briefing. You can ask me anything, "
        "like:\n"
        "• Cash position\n"
        "• How much does Ram owe?\n"
        "• Supplier dues\n"
        "• Dealer risk\n\n"
        "Reply menu anytime to tap through your options, or /help to see everything I can do "
        "as a full list."
    )


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


# ── Bulk product entry ───────────────────────────────────────────────────────
# A distributor pasting a whole price list (e.g. "Rice - 400, Dal - 450") in
# one message used to be swallowed whole as a single product *name* by the
# one-at-a-time flow below — this gives bulk pasting its own parser so each
# item is matched and saved as its own Product row.

_BULK_MODE_WORDS = {"bulk", "all at once", "at once", "together", "list", "in bulk"}
_ONE_BY_ONE_MODE_WORDS = {"one by one", "one at a time", "individually", "single", "one"}

_SKIP_FIELD_WORDS = {"skip", "none", "-", ""}


def _classify_product_mode(text: str) -> str | None:
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
    return (
        f"Added product: {name} ({_format_quantity(quantity)}{unit_suffix} in stock). "
        "Send another, or 'done'."
    )


_UNIT_PROMPT = "What unit is this measured in? (e.g. kg, pcs, box, litre, or 'skip')"

_PRODUCT_INTRO = (
    f"{_progress(1)}\n\n"
    "Now let's add your products. Reply 'one by one' to add them individually, "
    "or 'bulk' to send them all at once with full details "
    "(e.g. Rice, 300, 400, kg, 100, 5). Reply 'done' to skip."
)

_BULK_FORMAT_PROMPT = (
    "Send your products one per line, in this format:\n"
    "Name, Purchase Price, Selling Price, Unit, Stock, GST%\n"
    "e.g.\n"
    "Rice, 300, 400, kg, 100, 5\n"
    "Dal, 320, 450, kg, 50, 12\n"
    "Use 'skip' for any field you don't want to set "
    "(e.g. Rice, skip, 400, kg, 100, skip). Reply 'done' when finished."
)


async def handle_onboarding_message(db: AsyncSession, company: Company, text: str) -> str:
    """Advance the guided setup by one message and return the reply. Only
    mutates state/rows — the caller commits.
    """
    state = company.onboarding_state
    stripped = text.strip()
    scratch = dict(company.onboarding_scratch or {})

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

    # ── 1. Business type ─────────────────────────────────────────────────────
    if state == OnboardingState.awaiting_business_type:
        company.business_type = stripped
        company.onboarding_state = OnboardingState.gst_mode_ask
        return (
            "Do all your products have the same GST rate, or does it vary by product? "
            "Reply 'same', 'varies', or 'not sure' to decide later."
        )

    if state == OnboardingState.gst_mode_ask:
        if _is(stripped, "not sure", "skip", "later"):
            company.onboarding_state = OnboardingState.product_awaiting_mode
            return _PRODUCT_INTRO
        if _is(stripped, "varies", "vary"):
            company.gst_varies_by_product = True
            company.onboarding_state = OnboardingState.product_awaiting_mode
            return _PRODUCT_INTRO
        if _is(stripped, "same"):
            company.onboarding_state = OnboardingState.gst_rate_same
            return "What's your GST rate? (e.g. 5, 12, 18, or 0 if exempt)"
        return "Please reply 'same', 'varies', or 'not sure'."

    if state == OnboardingState.gst_rate_same:
        if _is(stripped, "not sure", "skip", "later"):
            company.onboarding_state = OnboardingState.product_awaiting_mode
            return _PRODUCT_INTRO
        try:
            rate = parse_gst_rate(stripped)
        except ValueError:
            return (
                "Please send a number between 0 and 100, e.g. 18 "
                "(or 'not sure' to decide later)."
            )
        company.gst_rate = rate
        company.gst_varies_by_product = False
        company.onboarding_state = OnboardingState.product_awaiting_mode
        return _PRODUCT_INTRO

    # ── 2. Products (name -> stock quantity, repeatable, or bulk paste) ──────
    if state == OnboardingState.product_awaiting_mode:
        if _is(stripped, "done", "skip"):
            company.onboarding_state = OnboardingState.dealer_awaiting_name
            return (
                f"{_progress(2)}\n\n"
                "Let's add your dealers (customers). Send the first dealer's name, or 'done'."
            )
        mode = _classify_product_mode(stripped)
        if mode == "bulk":
            company.onboarding_state = OnboardingState.product_awaiting_bulk
            return _BULK_FORMAT_PROMPT
        if mode == "one_by_one":
            company.onboarding_state = OnboardingState.product_awaiting_name
            return "Send your first product's name (e.g. Rice), or 'done' to skip."
        return "Please reply 'one by one' or 'bulk' — or 'done' to skip adding products."

    if state == OnboardingState.product_awaiting_bulk:
        if _is(stripped, "done", "skip"):
            company.onboarding_state = OnboardingState.dealer_awaiting_name
            return (
                f"{_progress(2)}\n\n"
                "Let's add your dealers (customers). Send the first dealer's name, or 'done'."
            )
        lines = [line for line in stripped.splitlines() if line.strip()]
        if not lines:
            return _BULK_FORMAT_PROMPT
        parsed_items = []
        for line in lines:
            try:
                parsed_items.append(_parse_bulk_line(line))
            except ValueError as exc:
                return f"Couldn't read that: {exc}\n\n{_BULK_FORMAT_PROMPT}"
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
        return (
            f"Added {len(parsed_items)} product(s): {names}. "
            "Send more, or reply 'done' when finished."
        )

    if state == OnboardingState.product_awaiting_name:
        if _is(stripped, "done", "skip"):
            company.onboarding_state = OnboardingState.dealer_awaiting_name
            return (
                f"{_progress(2)}\n\n"
                "Let's add your dealers (customers). Send the first dealer's name, or 'done'."
            )
        company.onboarding_scratch = {"name": stripped}
        company.onboarding_state = OnboardingState.product_awaiting_quantity
        return f"How much {stripped} do you have in stock right now? (e.g. 100, or 'skip')"

    if state == OnboardingState.product_awaiting_quantity:
        quantity = Decimal("0")
        if not _is(stripped, "skip"):
            try:
                quantity = parse_amount(stripped)
            except ValueError:
                return "Please send a number, e.g. 100 (or 'skip')."
        scratch["quantity"] = str(quantity)
        company.onboarding_scratch = scratch
        company.onboarding_state = OnboardingState.product_awaiting_unit
        return _UNIT_PROMPT

    if state == OnboardingState.product_awaiting_unit:
        unit = None if _is(stripped, "skip") else stripped
        scratch["unit"] = unit
        company.onboarding_scratch = scratch
        company.onboarding_state = OnboardingState.product_awaiting_price
        name = scratch.get("name", "this product")
        return f"What's the selling price for {name}? (e.g. 400, or 'skip')"

    if state == OnboardingState.product_awaiting_price:
        price = None
        if not _is(stripped, "skip"):
            try:
                price = parse_amount(stripped)
            except ValueError:
                return "Please send a number, e.g. 400 (or 'skip')."
        scratch["price"] = str(price) if price is not None else None
        company.onboarding_scratch = scratch
        company.onboarding_state = OnboardingState.product_awaiting_purchase_price
        name = scratch.get("name", "this product")
        return f"What's the purchase price (cost price) for {name}? (e.g. 300, or 'skip')"

    if state == OnboardingState.product_awaiting_purchase_price:
        purchase_price = None
        if not _is(stripped, "skip", "done"):
            try:
                purchase_price = parse_amount(stripped)
            except ValueError:
                return "Please send a number, e.g. 300 (or 'skip')."
        if company.gst_varies_by_product:
            scratch["purchase_price"] = str(purchase_price) if purchase_price is not None else None
            company.onboarding_scratch = scratch
            company.onboarding_state = OnboardingState.product_awaiting_gst_rate
            name = scratch.get("name", "this product")
            return f"What's the GST% for {name}? (e.g. 5, 12, 18, or 'skip' to decide later)"
        return _finalize_one_by_one_product(db, company, scratch, purchase_price, None)

    if state == OnboardingState.product_awaiting_gst_rate:
        gst_rate = None
        if not _is(stripped, "skip", "not sure", "done"):
            try:
                gst_rate = parse_gst_rate(stripped)
            except ValueError:
                return (
                    "Please send a number between 0 and 100, e.g. 18 "
                    "(or 'skip' to decide later)."
                )
        purchase_price_raw = scratch.get("purchase_price")
        purchase_price = Decimal(purchase_price_raw) if purchase_price_raw is not None else None
        return _finalize_one_by_one_product(db, company, scratch, purchase_price, gst_rate)

    # ── 3. Dealers (name -> phone -> credit days, repeatable) ────────────────
    if state == OnboardingState.dealer_awaiting_name:
        if _is(stripped, "done", "skip"):
            company.onboarding_state = OnboardingState.supplier_awaiting_name
            return (
                f"{_progress(3)}\n\nNow your suppliers. Send the first supplier's name, or 'done'."
            )
        company.onboarding_scratch = {"name": stripped}
        company.onboarding_state = OnboardingState.dealer_awaiting_phone
        return f"Phone number for {stripped}? (or 'skip')"

    if state == OnboardingState.dealer_awaiting_phone:
        if not _is(stripped, "skip"):
            scratch["phone"] = stripped
        company.onboarding_scratch = scratch
        company.onboarding_state = OnboardingState.dealer_awaiting_credit
        name = scratch.get("name", "them")
        return f"How many credit days do you give {name}? (e.g. 15, or 'skip')"

    if state == OnboardingState.dealer_awaiting_credit:
        credit = None
        if not _is(stripped, "skip"):
            try:
                credit = int(stripped)
            except ValueError:
                return "Please send a number of days, e.g. 15 (or 'skip')."
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
        return f"Added dealer {name}. Next dealer's name, or 'done'."

    # ── 4. Suppliers (same shape) ────────────────────────────────────────────
    if state == OnboardingState.supplier_awaiting_name:
        if _is(stripped, "done", "skip"):
            company.onboarding_state = OnboardingState.awaiting_opening_balance
            return f"{_progress(4)}\n\nHow much cash is currently in your business? (e.g. 320000)"
        company.onboarding_scratch = {"name": stripped}
        company.onboarding_state = OnboardingState.supplier_awaiting_phone
        return f"Phone number for {stripped}? (or 'skip')"

    if state == OnboardingState.supplier_awaiting_phone:
        if not _is(stripped, "skip"):
            scratch["phone"] = stripped
        company.onboarding_scratch = scratch
        company.onboarding_state = OnboardingState.supplier_awaiting_credit
        return f"How many days does {scratch.get('name', 'they')} give you to pay? (e.g. 15/'skip')"

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
        return f"Added supplier {name}. Next supplier's name, or 'done'."

    # ── 5. Opening cash ──────────────────────────────────────────────────────
    if state == OnboardingState.awaiting_opening_balance:
        try:
            amount = parse_amount(stripped)
        except ValueError:
            return "Please send an amount, e.g. 320000."
        company.opening_balance = amount
        company.onboarding_state = OnboardingState.receivable_ask
        return f"{_progress(5)}\n\nDo any dealers currently owe you money? (yes/no)"

    # ── 6. Outstanding receivables ───────────────────────────────────────────
    if state == OnboardingState.receivable_ask:
        if _is(stripped, "no", "skip", "done"):
            company.onboarding_state = OnboardingState.payable_ask
            return f"{_progress(6)}\n\nDo you have any supplier payments pending? (yes/no)"
        if _is(stripped, "yes"):
            company.onboarding_state = OnboardingState.receivable_dealer
            return "Which dealer owes you? (name)"
        return "Please reply yes or no."

    if state == OnboardingState.receivable_dealer:
        company.onboarding_scratch = {"party": stripped}
        company.onboarding_state = OnboardingState.receivable_amount
        return f"How much does {stripped} owe you? (e.g. 42000)"

    if state == OnboardingState.receivable_amount:
        try:
            amount = parse_amount(stripped)
        except ValueError:
            return "Please send an amount, e.g. 42000."
        scratch["amount"] = str(amount)
        company.onboarding_scratch = scratch
        company.onboarding_state = OnboardingState.receivable_date
        party = scratch.get("party", "them")
        return f"When do you expect payment from {party}? (e.g. Friday, 15 days, or next week)"

    if state == OnboardingState.receivable_date:
        today = business_now(company.timezone).date()
        due = _parse_relative_date(stripped, today)
        if due is None:
            return "Sorry, I didn't get that date. Try e.g. Friday, 15 days, or next week."
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
        return f"Recorded {format_inr(amount)} from {party}. Any other dealer owe you? (yes/no)"

    # ── 7. Outstanding payables ──────────────────────────────────────────────
    if state == OnboardingState.payable_ask:
        if _is(stripped, "no", "skip", "done"):
            company.onboarding_state = OnboardingState.awaiting_briefing_hour
            return (
                f"{_progress(7)}\n\n"
                "Last step — what time should I send your morning briefing? Reply 7, 8, or 9."
            )
        if _is(stripped, "yes"):
            company.onboarding_state = OnboardingState.payable_supplier
            return "Which supplier do you owe? (name)"
        return "Please reply yes or no."

    if state == OnboardingState.payable_supplier:
        company.onboarding_scratch = {"party": stripped}
        company.onboarding_state = OnboardingState.payable_amount
        return f"How much do you owe {stripped}? (e.g. 82000)"

    if state == OnboardingState.payable_amount:
        try:
            amount = parse_amount(stripped)
        except ValueError:
            return "Please send an amount, e.g. 82000."
        scratch["amount"] = str(amount)
        company.onboarding_scratch = scratch
        company.onboarding_state = OnboardingState.payable_date
        party = scratch.get("party", "them")
        return f"When is the payment to {party} due? (e.g. Friday, 15 days, or next week)"

    if state == OnboardingState.payable_date:
        today = business_now(company.timezone).date()
        due = _parse_relative_date(stripped, today)
        if due is None:
            return "Sorry, I didn't get that date. Try e.g. Friday, 15 days, or next week."
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
        return f"Recorded {format_inr(amount)} to {party}. Any other supplier pending? (yes/no)"

    # ── 8. Briefing time -> done ─────────────────────────────────────────────
    if state == OnboardingState.awaiting_briefing_hour:
        try:
            hour = int(stripped)
        except ValueError:
            return "Please reply with an hour, e.g. 7, 8, or 9."
        if not _MIN_BRIEFING_HOUR <= hour <= _MAX_BRIEFING_HOUR:
            return "Please choose a morning hour between 5 and 11 (e.g. 7, 8, or 9)."
        company.briefing_hour = hour
        company.onboarding_state = OnboardingState.completed
        return _finish_message()

    # Unreachable in practice (completed is routed away before reaching here),
    # but never leave a company stuck in an unknown state.
    company.onboarding_state = OnboardingState.completed
    return _finish_message()


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
