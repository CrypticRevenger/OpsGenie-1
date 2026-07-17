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

import re
import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company, OnboardingState
from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceDirection, InvoiceSource, InvoiceStatus
from app.models.product import Product
from app.models.supplier import Supplier
from app.services.followup import _parse_relative_date
from app.services.importer.normalizer import parse_amount
from app.services.importer.parties import find_or_create_party
from app.services.money_format import format_inr
from app.services.snapshot import business_now

_TOTAL_STEPS = 9

# The briefing hour also gates the notification window (scheduler only runs
# checks from this hour on), so it's clamped to sane morning hours rather than
# any 0-23 — a briefing at 00:00 or 23:00 would distort that gate.
_MIN_BRIEFING_HOUR = 5
_MAX_BRIEFING_HOUR = 11

# Preferred language for the agent/briefing (Company.preferred_language). Stored
# as a human-readable name the LLM prompt reads naturally; free text is accepted
# for anything beyond the two common choices.
_LANGUAGES = {"english": "English", "en": "English", "hindi": "Hindi", "hi": "Hindi"}


def _normalize_language(raw: str) -> str:
    return _LANGUAGES.get(raw.strip().lower(), raw.strip().title() or "English")


_INTRO = (
    "👋 Welcome to OpsGenie! Let's set up your business — it takes about 5 minutes, "
    "and you can stop and continue anytime.\n\n"
    "First: what kind of business do you run? (e.g. FMCG Distributor, Pharma Distributor)"
)


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
        "Or reply 1 Cash · 2 Collections · 3 Suppliers · 4 Dealer Risk anytime.\n\n"
        "Reply help anytime to see everything I can do."
    )


def _is(word: str, *options: str) -> bool:
    return word.strip().lower() in options


def _format_quantity(quantity: Decimal) -> str:
    """Render a stock quantity without parse_amount's forced 2-decimal padding
    (e.g. Decimal("100.00") -> "100")."""
    text = format(quantity, "f").rstrip("0").rstrip(".")
    return text or "0"


# ── Bulk product entry ───────────────────────────────────────────────────────
# A distributor pasting a whole price list (e.g. "Rice - 400, Dal - 450") in
# one message used to be swallowed whole as a single product *name* by the
# one-at-a-time flow below — this gives bulk pasting its own parser so each
# item is matched and saved as its own Product row.

_BULK_MODE_WORDS = {"bulk", "all at once", "at once", "together", "list", "in bulk"}
_ONE_BY_ONE_MODE_WORDS = {"one by one", "one at a time", "individually", "single", "one"}

_BULLET_PREFIX_RE = re.compile(r"^[-*•]+\s*")
# A per-item "name <sep> price" suffix, e.g. "Rice - 400", "Dal: 450",
# "Jeans @500", "Rice - Rs 400 each". Requires the tail after the last
# separator to be a bare number so a hyphenated name with no price (e.g.
# "T-Shirt") never matches.
_ITEM_PRICE_RE = re.compile(
    r"^(?P<name>.+?)\s*[-:@]\s*(?:rs\.?|inr|₹)?\s*(?P<price>\d[\d,]*(?:\.\d+)?)"
    r"\s*(?:each|/-|/each)?$",
    re.IGNORECASE,
)
# A shared price applying to every item in the message, e.g. a trailing
# "500 each" line/phrase rather than a per-item price.
_SHARED_EACH_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*each\b", re.IGNORECASE)


def _classify_product_mode(text: str) -> str | None:
    normalized = text.strip().lower()
    if normalized in _BULK_MODE_WORDS:
        return "bulk"
    if normalized in _ONE_BY_ONE_MODE_WORDS:
        return "one_by_one"
    return None


def _split_bulk_items(text: str) -> list[str]:
    """Newlines always separate items; within a line, commas do too — matches
    both a pasted one-per-line list and the "Rice - 400, Dal - 450" shape.
    """
    parts: list[str] = []
    for line in text.splitlines():
        parts.extend(line.split(","))
    return [p.strip() for p in parts if p.strip()]


def _parse_bulk_products(text: str) -> list[tuple[str, Decimal | None]]:
    """Parse a free-form bulk product message into (name, price) pairs. Price
    is None when the item carries no price (e.g. a plain name-only list) —
    the caller still saves the product, just without selling_price set.
    """
    shared_match = _SHARED_EACH_RE.search(text)
    shared_price: Decimal | None = None
    if shared_match:
        try:
            shared_price = parse_amount(shared_match.group(1))
        except ValueError:
            shared_price = None

    items: list[tuple[str, Decimal | None]] = []
    for raw_item in _split_bulk_items(text):
        item = _BULLET_PREFIX_RE.sub("", raw_item).strip()
        if not item:
            continue
        match = _ITEM_PRICE_RE.match(item)
        if match:
            name = match.group("name").strip()
            try:
                price = parse_amount(match.group("price"))
            except ValueError:
                price = shared_price
        else:
            # No per-item price — this item may just be the message's shared
            # "<amount> each" declaration on its own line, not a product.
            name = _SHARED_EACH_RE.sub("", item).strip(" -:@").strip()
            if not name:
                continue
            price = shared_price
        if name:
            items.append((name, price))
    return items


def _describe_product(name: str, price: Decimal | None, unit: str | None = None) -> str:
    bits = [format_inr(price)] if price is not None else []
    if unit:
        bits.append(unit)
    return f"{name} ({', '.join(bits)})" if bits else name


_UNIT_PROMPT = "What unit is this measured in? (e.g. kg, pcs, box, litre, or 'skip')"
_BULK_UNIT_PROMPT = (
    "What unit are these measured in? (e.g. kg, pcs, box, litre — applies to all of "
    "these, or 'skip' if it varies)"
)
_BULK_PURCHASE_PRICE_PROMPT = (
    "Want to add purchase prices (what you pay your supplier) too? Reply in the same "
    "format (Rice - 300, Dal - 320), or 'skip' if you don't want to track them."
)


async def handle_onboarding_message(db: AsyncSession, company: Company, text: str) -> str:
    """Advance the guided setup by one message and return the reply. Only
    mutates state/rows — the caller commits.
    """
    state = company.onboarding_state
    stripped = text.strip()
    scratch = dict(company.onboarding_scratch or {})

    # ── Kick-off ────────────────────────────────────────────────────────────
    if state == OnboardingState.not_started:
        company.onboarding_state = OnboardingState.awaiting_business_type
        return _INTRO

    # ── 1. Business type ─────────────────────────────────────────────────────
    if state == OnboardingState.awaiting_business_type:
        company.business_type = stripped
        company.onboarding_state = OnboardingState.product_awaiting_mode
        return (
            f"{_progress(1)}\n\n"
            "Now let's add your products. Reply 'one by one' to add them individually, "
            "or 'bulk' to send them all at once with prices "
            "(e.g. Rice - 400, Dal - 450). Reply 'done' to skip."
        )

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
            return (
                "Send all your products now — one per line or comma-separated, with an "
                "optional price (e.g. Rice - 400, Dal - 450). Reply 'done' when finished."
            )
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
        parsed = _parse_bulk_products(stripped)
        if not parsed:
            return (
                "I couldn't find any products in that message. List them one per line or "
                "comma-separated, with an optional price (e.g. Rice - 400, Dal - 450)."
            )
        company.onboarding_scratch = {
            "pending_bulk": [
                [name, str(price) if price is not None else None] for name, price in parsed
            ]
        }
        company.onboarding_state = OnboardingState.product_awaiting_bulk_unit
        return _BULK_UNIT_PROMPT

    if state == OnboardingState.product_awaiting_bulk_unit:
        unit = None if _is(stripped, "skip") else stripped
        company.onboarding_scratch = {"pending_bulk": scratch.get("pending_bulk", []), "unit": unit}
        company.onboarding_state = OnboardingState.product_awaiting_bulk_purchase_price
        return _BULK_PURCHASE_PRICE_PROMPT

    if state == OnboardingState.product_awaiting_bulk_purchase_price:
        unit = scratch.get("unit")
        pending = [
            (item[0], Decimal(item[1]) if item[1] is not None else None)
            for item in scratch.get("pending_bulk", [])
        ]
        purchase_prices: dict[str, Decimal] = {}
        if not _is(stripped, "skip", "no", "none", "done"):
            purchase_prices = {
                name.lower(): price
                for name, price in _parse_bulk_products(stripped)
                if price is not None
            }
        for name, price in pending:
            db.add(
                Product(
                    company_id=company.id,
                    name=name,
                    selling_price=price,
                    unit=unit,
                    purchase_price=purchase_prices.get(name.lower()),
                )
            )
        names = ", ".join(_describe_product(name, price, unit) for name, price in pending)
        company.onboarding_scratch = None
        company.onboarding_state = OnboardingState.product_awaiting_bulk
        return (
            f"Added {len(pending)} product(s): {names}. "
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
        company.onboarding_state = OnboardingState.product_awaiting_purchase_price
        name = scratch.get("name", "this product")
        return f"What's the purchase price (cost price) for {name}? (e.g. 30, or 'skip')"

    if state == OnboardingState.product_awaiting_purchase_price:
        purchase_price = None
        if not _is(stripped, "skip", "done"):
            try:
                purchase_price = parse_amount(stripped)
            except ValueError:
                return "Please send a number, e.g. 30 (or 'skip')."
        name = scratch.get("name", "Product")
        quantity = Decimal(scratch.get("quantity", "0"))
        unit = scratch.get("unit")
        db.add(
            Product(
                company_id=company.id,
                name=name,
                stock_quantity=quantity,
                unit=unit,
                purchase_price=purchase_price,
            )
        )
        company.onboarding_scratch = None
        company.onboarding_state = OnboardingState.product_awaiting_name
        unit_suffix = f" {unit}" if unit else ""
        return (
            f"Added product: {name} ({_format_quantity(quantity)}{unit_suffix} in stock). "
            "Send another, or 'done'."
        )

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
        return f"When do you expect payment from {party}? (e.g. Friday, 15 days)"

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
            company.onboarding_state = OnboardingState.awaiting_language
            return (
                f"{_progress(7)}\n\nWhich language should I message you in? Reply English or Hindi."
            )
        if _is(stripped, "yes"):
            company.onboarding_state = OnboardingState.payable_supplier
            return "Which supplier do you owe? (name)"
        return "Please reply yes or no."

    # ── 8. Preferred language ────────────────────────────────────────────────
    if state == OnboardingState.awaiting_language:
        company.preferred_language = _normalize_language(stripped)
        company.onboarding_state = OnboardingState.awaiting_briefing_hour
        return (
            f"{_progress(8)}\n\n"
            "Last step — what time should I send your morning briefing? Reply 7, 8, or 9."
        )

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
        return f"When is the payment to {scratch.get('party', 'them')} due? (e.g. Friday, 15 days)"

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

    # ── 9. Briefing time -> done ─────────────────────────────────────────────
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
