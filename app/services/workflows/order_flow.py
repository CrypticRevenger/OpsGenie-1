"""Guided create-order workflow — Phase 2B.

Dealer? -> (confirm-add if unknown) -> repeatable product loop (product name
-> price if not on file -> quantity) -> preview -> PendingOperation ->
YES/NO (handled by app/services/writes/pending_operation.py, not here). Same
state-machine shape as app/services/workflows/payment_flow.py: state lives in
Company.active_workflow ("create_order") + Company.workflow_scratch (this
flow's own step + collected fields), mutated in place, never committed here.

Orders are sales to dealers only (the receivable side) — unlike
record_payment, a brand-new dealer or product CAN proceed here, since an
order is exactly what gives a new dealer their first invoice and a new
product its catalogue entry. The dealer/product rows themselves are created
at confirm time inside app/services/writes/orders.py::create_order, not
here — this flow only collects and previews raw input.

"cancel"/"stop" are recognized at every step, matching payment_flow.py's
universal exit (an active workflow outranks the menu, so a user needs a
guaranteed way out).
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import Locale, resolve_locale, t
from app.models.company import Company
from app.models.dealer import Dealer
from app.models.pending_operation import PendingOperationType
from app.models.product import Product
from app.services.duplicate_check import find_similar_order
from app.services.gst import parse_gst_rate
from app.services.importer.normalizer import parse_amount
from app.services.invoice_ocr import ExtractedInvoice
from app.services.money_format import format_inr
from app.services.onboarding_flow import _is
from app.services.party_outstanding import calculate_party_outstanding
from app.services.snapshot import business_now
from app.services.writes.pending_operation import create_pending_operation

# Invoice-photo OCR pre-fill (app/services/invoice_ocr.py) — a per-field
# suggestion is only offered as a "reply YES" shortcut above this confidence;
# below it (or a missing value), the step just asks its plain question, same
# as if no photo had ever been sent. One tunable constant rather than baked
# into each of the helpers below.
_SUGGESTION_CONFIDENCE_THRESHOLD = 0.75


def _suggested_value(guess: dict | None) -> str | None:
    if not guess:
        return None
    value = guess.get("value")
    confidence = guess.get("confidence") or 0
    if value and confidence >= _SUGGESTION_CONFIDENCE_THRESHOLD:
        return str(value)
    return None


async def _match_dealer(db: AsyncSession, company_id, name: str) -> Dealer | None:
    return await db.scalar(
        select(Dealer).where(
            Dealer.company_id == company_id, func.lower(Dealer.name) == name.lower()
        )
    )


async def _match_product(db: AsyncSession, company_id, name: str) -> Product | None:
    return await db.scalar(
        select(Product).where(
            Product.company_id == company_id, func.lower(Product.name) == name.lower()
        )
    )


def start_order_workflow(company: Company) -> str:
    """Sets active_workflow + the first step's scratch and returns the
    opening question verbatim — called both by the webhook's keyword-match
    branch and (like payment_flow.py) any future agent starter tool.
    """
    company.active_workflow = "create_order"
    company.workflow_scratch = {"step": "awaiting_dealer"}
    return t("order.start", resolve_locale(company))


def start_order_workflow_from_ocr(company: Company, extraction: ExtractedInvoice) -> str:
    """OCR-triggered counterpart to start_order_workflow (app/services/
    invoice_ocr.py's extract_invoice_from_image). Same active_workflow value
    ("create_order") as the plain flow — no new _WORKFLOW_HANDLERS or
    PendingOperationType entry needed — only workflow_scratch differs: it's
    seeded with the raw per-field extraction (ocr_queue) so
    handle_order_workflow_message's step-scoped suggestion logic below can
    offer it, one field at a time, exactly like a plain guided flow with
    smart defaults pre-typed in.
    """
    company.active_workflow = "create_order"
    loc = resolve_locale(company)
    scratch: dict = {
        "step": "awaiting_dealer",
        "ocr_queue": [item.model_dump() for item in extraction.items],
    }
    dealer_suggestion = _suggested_value(extraction.dealer_name.model_dump())
    if dealer_suggestion:
        scratch["ocr_suggestions"] = {"awaiting_dealer": dealer_suggestion}
        company.workflow_scratch = scratch
        return t("order.ocr_dealer_ask", loc, dealer=dealer_suggestion)
    company.workflow_scratch = scratch
    return t("order.ocr_no_dealer", loc)


def _advance_to_awaiting_product(scratch: dict, loc: Locale, plain_key: str, **plain_kwargs) -> str:
    """Sets step="awaiting_product" and, if there's a queued OCR item,
    surfaces its product-name guess as a suggestion (when confident enough) —
    called from every place that currently transitions into this step, so an
    OCR-originated flow keeps offering the next queued item automatically.
    Peeks the queue (doesn't pop) — the item is only consumed once its
    quantity is actually recorded, see the awaiting_quantity branch below.
    """
    scratch["step"] = "awaiting_product"
    queue = scratch.get("ocr_queue") or []
    if not queue:
        scratch.pop("ocr_current_item", None)
        return t(plain_key, loc, **plain_kwargs)
    item = queue[0]
    scratch["ocr_current_item"] = item
    suggestion = _suggested_value(item.get("product_name"))
    if suggestion is None:
        return t(plain_key, loc, **plain_kwargs)
    ocr_suggestions = dict(scratch.get("ocr_suggestions") or {})
    ocr_suggestions["awaiting_product"] = suggestion
    scratch["ocr_suggestions"] = ocr_suggestions
    return t("order.ocr_product_ask", loc, product=suggestion)


def _advance_to_awaiting_price(scratch: dict, loc: Locale, plain_key: str, **plain_kwargs) -> str:
    """Same idea as _advance_to_awaiting_product, for the price field of
    whatever item is currently in scratch["ocr_current_item"] — independently
    gated from the product-name suggestion, since a photo can have a crisp
    product name next to an illegible price.
    """
    scratch["step"] = "awaiting_price"
    item = scratch.get("ocr_current_item")
    suggestion = _suggested_value(item.get("price")) if item else None
    if suggestion is None:
        return t(plain_key, loc, **plain_kwargs)
    ocr_suggestions = dict(scratch.get("ocr_suggestions") or {})
    ocr_suggestions["awaiting_price"] = suggestion
    scratch["ocr_suggestions"] = ocr_suggestions
    return t(
        "order.ocr_price_ask",
        loc,
        product=plain_kwargs.get("product", ""),
        price=format_inr(Decimal(suggestion)),
    )


def _advance_to_awaiting_quantity(
    scratch: dict, loc: Locale, plain_key: str, **plain_kwargs
) -> str:
    """Same idea, for the quantity field of scratch["ocr_current_item"]."""
    scratch["step"] = "awaiting_quantity"
    item = scratch.get("ocr_current_item")
    suggestion = _suggested_value(item.get("quantity")) if item else None
    if suggestion is None:
        return t(plain_key, loc, **plain_kwargs)
    ocr_suggestions = dict(scratch.get("ocr_suggestions") or {})
    ocr_suggestions["awaiting_quantity"] = suggestion
    scratch["ocr_suggestions"] = ocr_suggestions
    return t(
        "order.ocr_quantity_ask",
        loc,
        product=plain_kwargs.get("product", ""),
        unit=plain_kwargs.get("unit", "units"),
        quantity=suggestion,
    )


def compute_order_math(
    items: list[dict], company_gst_rate: Decimal
) -> tuple[Decimal, Decimal, Decimal]:
    """subtotal, gst_amount, total — the exact math writes/orders.py::
    create_order re-derives at confirm time, duplicated here in pure form
    (no db, no i18n) so both the initial preview and the post-ADVANCE
    re-render in pending_operation.py can get the current total (e.g. to
    validate an advance against it) without needing the full item-line
    rendering render_order_preview below does.
    """
    subtotal = Decimal("0.00")
    gst_amount = Decimal("0.00")
    for item in items:
        price = Decimal(item["price"]) if item.get("price") is not None else Decimal("0.00")
        quantity = Decimal(item["quantity"])
        line_total = (price * quantity).quantize(Decimal("0.01"))
        item_gst_raw = item.get("gst_rate")
        line_gst_rate = Decimal(item_gst_raw) if item_gst_raw is not None else company_gst_rate
        subtotal += line_total
        gst_amount += (line_total * line_gst_rate / Decimal("100")).quantize(Decimal("0.01"))
    return subtotal, gst_amount, subtotal + gst_amount


def render_order_preview(
    *,
    dealer_name: str,
    items: list[dict],
    company_gst_rate: Decimal,
    advance_paid: Decimal,
    duplicate_invoice_number: str | None,
    credit_limit_breach: dict | None,
    loc: Locale,
) -> str:
    """Builds the full preview text from scratch every call — item lines,
    Subtotal/GST/Total, Payment Made/Balance Due (always shown, even when
    advance_paid is 0, so the ADVANCE option is contextually visible on
    every order, not just when one exists), and the two advisory warnings
    rendered fresh from their cached facts rather than cached as text —
    deliberately, so a locale change mid-conversation can never show stale
    wording for a fact (a duplicate invoice number, a credit-limit breach)
    that's still true. Called both for the first preview (order_flow.py)
    and to redraw it after an advance amount is entered
    (writes/pending_operation.py) — same output either way, given the same
    inputs, since nothing here touches the DB.
    """
    lines = []
    subtotal = Decimal("0.00")
    gst_amount = Decimal("0.00")
    line_rates: set[Decimal] = set()
    for item in items:
        price = Decimal(item["price"]) if item.get("price") is not None else Decimal("0.00")
        quantity = Decimal(item["quantity"])
        line_total = (price * quantity).quantize(Decimal("0.01"))
        item_gst_raw = item.get("gst_rate")
        line_gst_rate = Decimal(item_gst_raw) if item_gst_raw is not None else company_gst_rate
        line_gst_amount = (line_total * line_gst_rate / Decimal("100")).quantize(Decimal("0.01"))
        subtotal += line_total
        gst_amount += line_gst_amount
        line_rates.add(line_gst_rate)
        lines.append(
            t(
                "order.line",
                loc,
                quantity=quantity,
                product=item["product_name"],
                price=format_inr(price),
                total=format_inr(line_total),
            )
        )

    total = subtotal + gst_amount
    total_lines = [t("order.subtotal", loc, amount=format_inr(subtotal))]
    if gst_amount > 0:
        rate_label = f" ({next(iter(line_rates))}%)" if len(line_rates) == 1 else ""
        total_lines.append(
            t("order.gst", loc, rate_label=rate_label, amount=format_inr(gst_amount))
        )
    total_lines.append(t("order.total", loc, amount=format_inr(total)))
    balance_due = total - advance_paid
    total_lines.append(t("order.payment_made", loc, amount=format_inr(advance_paid)))
    total_lines.append(t("order.balance_due", loc, amount=format_inr(balance_due)))

    warning_lines: list[str] = []
    if duplicate_invoice_number is not None:
        warning_lines.append(t("order.duplicate_warning", loc, number=duplicate_invoice_number))
    if credit_limit_breach is not None:
        warning_lines.append(
            t(
                "order.credit_limit_warning",
                loc,
                dealer=credit_limit_breach["dealer"],
                prospective=format_inr(Decimal(credit_limit_breach["prospective"])),
                limit=format_inr(Decimal(credit_limit_breach["limit"])),
            )
        )

    return (
        t("order.preview_header", loc, dealer=dealer_name)
        + "\n"
        + "\n".join(lines)
        + "\n"
        + "\n".join(total_lines)
        + ("\n" + "\n".join(warning_lines) if warning_lines else "")
        + "\n"
        + t("order.preview_footer", loc)
    )


async def _preview_and_finalize(
    db: AsyncSession, company: Company, scratch: dict, loc: Locale
) -> tuple[str, dict]:
    """Builds the confirmation preview text and the PendingOperation payload
    from the collected raw items — never a precomputed total on its own, but
    a preview naturally has to show one; execute-time re-derives everything
    fresh against current prices/stock rather than trusting this text.

    Also surfaces two advisory, non-blocking warnings (mirroring
    writes/orders.py's negative_stock_warnings "flag, never block" tier) when
    the dealer already exists in the DB — a brand-new, not-yet-confirmed
    dealer has no row/credit_limit/history to check against, so both are
    skipped for one: a likely-duplicate order (same dealer/date/total as an
    existing invoice) and a credit-limit breach (this order would push the
    dealer's outstanding past their credit_limit, when one is on file). Only
    these two facts (not any rendered text) go into the payload — see
    render_order_preview's docstring for why.
    """
    dealer_name = scratch["dealer_name"]
    items = scratch["items"]
    _subtotal, _gst_amount, total = compute_order_math(items, company.gst_rate)

    duplicate_invoice_number: str | None = None
    credit_limit_breach: dict | None = None
    dealer = await _match_dealer(db, company.id, dealer_name)
    if dealer is not None:
        today = business_now(company.timezone).date()
        duplicate = await find_similar_order(
            db, company_id=company.id, dealer_id=dealer.id, invoice_date=today, total_amount=total
        )
        if duplicate is not None:
            duplicate_invoice_number = duplicate.invoice_number

        if dealer.credit_limit is not None:
            prospective_total = (
                await calculate_party_outstanding(db, direction="receivable", party_id=dealer.id)
                + total
            )
            if prospective_total > dealer.credit_limit:
                credit_limit_breach = {
                    "dealer": dealer.name,
                    "prospective": str(prospective_total),
                    "limit": str(dealer.credit_limit),
                }

    preview = render_order_preview(
        dealer_name=dealer_name,
        items=items,
        company_gst_rate=company.gst_rate,
        advance_paid=Decimal("0.00"),
        duplicate_invoice_number=duplicate_invoice_number,
        credit_limit_breach=credit_limit_breach,
        loc=loc,
    )
    payload = {
        "dealer_name": dealer_name,
        "items": items,
        "advance_paid": None,
        "duplicate_invoice_number": duplicate_invoice_number,
        "credit_limit_breach": credit_limit_breach,
    }
    return preview, payload


async def handle_order_workflow_message(db: AsyncSession, company: Company, text: str) -> str:
    """Advance the guided create-order flow by one message. Only mutates
    state/rows — the caller (the webhook) commits.
    """
    stripped = text.strip()
    loc = resolve_locale(company)

    if _is(stripped, "cancel", "stop"):
        company.active_workflow = None
        company.workflow_scratch = None
        return t("workflow.cancelled", loc)

    scratch = dict(company.workflow_scratch or {})
    step = scratch.get("step")

    # Invoice-photo OCR pre-fill: a step-scoped, single-use suggestion. If the
    # current step has a pending suggestion (offered by start_order_workflow_
    # from_ocr or one of the _advance_to_awaiting_* helpers below) and the
    # user's reply is a bare "yes"/"y", swap it in for `stripped` so every
    # branch below runs completely unchanged — as if the suggested value had
    # been typed. Popped whether or not it's actually consumed, so it's never
    # reapplied at a later, differently-named step (this is also what keeps
    # it from colliding with "yes"/"no" meaning something else entirely at
    # awaiting_new_dealer_confirm/awaiting_new_product_confirm below — those
    # steps never have an entry in ocr_suggestions).
    ocr_suggestions = dict(scratch.get("ocr_suggestions") or {})
    suggested = ocr_suggestions.pop(step, None)
    scratch["ocr_suggestions"] = ocr_suggestions
    if suggested is not None and _is(stripped, "yes", "y"):
        stripped = suggested

    if step == "awaiting_dealer":
        if not stripped:
            return t("order.need_dealer", loc)
        dealer = await _match_dealer(db, company.id, stripped)
        if dealer is not None:
            scratch["dealer_name"] = dealer.name
            scratch["items"] = []
            message = _advance_to_awaiting_product(
                scratch, loc, "order.dealer_found", dealer=dealer.name
            )
            company.workflow_scratch = scratch
            return message
        scratch["dealer_name"] = stripped
        scratch["step"] = "awaiting_new_dealer_confirm"
        company.workflow_scratch = scratch
        return t("order.add_new_dealer", loc, dealer=stripped)

    if step == "awaiting_new_dealer_confirm":
        if _is(stripped, "no", "n"):
            company.active_workflow = None
            company.workflow_scratch = None
            return t("workflow.cancelled", loc)
        if not _is(stripped, "yes", "y"):
            return t("workflow.yes_no", loc)
        scratch["items"] = []
        message = _advance_to_awaiting_product(
            scratch, loc, "order.new_dealer_added", dealer=scratch["dealer_name"]
        )
        company.workflow_scratch = scratch
        return message

    if step == "awaiting_product":
        if _is(stripped, "done"):
            if not scratch.get("items"):
                return t("order.need_one_product", loc)
            preview, payload = await _preview_and_finalize(db, company, scratch, loc)
            await create_pending_operation(db, company, PendingOperationType.create_order, payload)
            company.active_workflow = None
            company.workflow_scratch = None
            return preview
        if not stripped:
            return t("order.need_product", loc)
        product = await _match_product(db, company.id, stripped)
        if product is not None and company.gst_varies_by_product and product.gst_rate is None:
            # Blocked, not defaulted — falling back to company.gst_rate here
            # would silently invoice at 0% (company.gst_rate is 0 in this
            # mode). Stay on this same step so a different product name or
            # "cancel" both still work.
            return t("order.product_gst_missing", loc, product=product.name)
        if product is not None and product.selling_price is not None:
            scratch["current_product"] = {
                "name": product.name,
                "price": str(product.selling_price),
                "gst_rate": str(product.gst_rate) if product.gst_rate is not None else None,
            }
            unit = product.unit or "units"
            message = _advance_to_awaiting_quantity(
                scratch, loc, "order.quantity_ask", unit=unit, product=product.name
            )
            company.workflow_scratch = scratch
            return message
        if product is not None:
            # On file but no price recorded yet (common for products the
            # guided onboarding conversation created with a name only).
            scratch["current_product"] = {
                "name": product.name,
                "price": None,
                "gst_rate": str(product.gst_rate) if product.gst_rate is not None else None,
            }
            message = _advance_to_awaiting_price(
                scratch, loc, "order.price_ask", product=product.name
            )
            company.workflow_scratch = scratch
            return message
        scratch["current_product"] = {"name": stripped, "price": None}
        scratch["step"] = "awaiting_new_product_confirm"
        company.workflow_scratch = scratch
        return t("order.add_new_product", loc, product=stripped)

    if step == "awaiting_new_product_confirm":
        if _is(stripped, "no", "n"):
            scratch["current_product"] = None
            queue = scratch.get("ocr_queue")
            if queue:
                # Don't re-offer the same (evidently wrong) OCR product-name
                # guess again once the user has declined creating it — its
                # price/quantity guesses, if any, are still offered once a
                # corrected product name is entered for this same item.
                queue[0] = dict(queue[0])
                queue[0]["product_name"] = {"value": None, "confidence": 0.0}
            message = _advance_to_awaiting_product(scratch, loc, "order.new_product_declined")
            company.workflow_scratch = scratch
            return message
        if not _is(stripped, "yes", "y"):
            return t("workflow.yes_no", loc)
        name = scratch["current_product"]["name"]
        if company.gst_varies_by_product:
            # A brand-new product has no gst_rate yet — orders.py::create_order
            # blocks (never guesses) when gst_varies_by_product and the
            # resolved product's rate is None, same "block, not defaulted"
            # rule the awaiting_product step already enforces for an
            # *existing* catalogue product above. Ask here too, or this
            # company could never actually finish an order that introduces a
            # new product — it would always fail at the very last step.
            scratch["step"] = "awaiting_new_product_gst_rate"
            company.workflow_scratch = scratch
            return t("order.new_product_gst_ask", loc, product=name)
        message = _advance_to_awaiting_price(scratch, loc, "order.price_ask", product=name)
        company.workflow_scratch = scratch
        return message

    if step == "awaiting_new_product_gst_rate":
        try:
            gst_rate = parse_gst_rate(stripped)
        except ValueError:
            return t("gst.rate_invalid", loc)
        current = dict(scratch["current_product"])
        current["gst_rate"] = str(gst_rate)
        scratch["current_product"] = current
        name = current["name"]
        message = _advance_to_awaiting_price(scratch, loc, "order.price_ask", product=name)
        company.workflow_scratch = scratch
        return message

    if step == "awaiting_price":
        try:
            price = parse_amount(stripped)
        except ValueError:
            return t("order.price_invalid", loc)
        if price <= 0:
            return t("order.price_positive", loc)
        current = dict(scratch["current_product"])
        current["price"] = str(price)
        scratch["current_product"] = current
        message = _advance_to_awaiting_quantity(
            scratch, loc, "order.quantity_ask", unit="units", product=current["name"]
        )
        company.workflow_scratch = scratch
        return message

    if step == "awaiting_quantity":
        try:
            quantity = parse_amount(stripped)
        except ValueError:
            return t("order.quantity_invalid", loc)
        if quantity <= 0:
            return t("order.quantity_positive", loc)
        current = scratch["current_product"]
        items = list(scratch.get("items", []))
        items.append(
            {
                "product_name": current["name"],
                "quantity": str(quantity),
                "price": current.get("price"),
                "gst_rate": current.get("gst_rate"),
            }
        )
        scratch["items"] = items
        scratch["current_product"] = None
        if scratch.get("ocr_current_item") is not None:
            # This item is now committed — consume it off the queue so the
            # next awaiting_product transition offers the next one.
            scratch["ocr_queue"] = (scratch.get("ocr_queue") or [])[1:]
            scratch["ocr_current_item"] = None
        message = _advance_to_awaiting_product(
            scratch, loc, "order.item_added", quantity=quantity, product=current["name"]
        )
        company.workflow_scratch = scratch
        return message

    # Unreachable in practice (every step above is exhaustive for this flow),
    # but never leave a company stuck on a workflow step this code can't run.
    company.active_workflow = None
    company.workflow_scratch = None
    return t("workflow.error_restart", loc, trigger="new order")
