"""Numbered query menu — V0.1 Step 12.

Four canned reports built purely from an already-computed Snapshot (Phase
5A) — no new business logic, risk scoring, or thresholds invented here.
Pure functions, no DB/network access, same testability pattern as
app/services/recommendations.py.

SPEC's own illustrative "Collections" example blends two concepts (7-day
expected collections + overdue-dealer risk labels) that aren't unified in
today's data model. Reply 2 here is the 7-day expected-collections window
(matching the Snapshot field it's built from); risk-labeled overdue-dealer
detail lives in Reply 4, reusing the risk_level Phase 5A already computes.
"""

from __future__ import annotations

from datetime import date

from app.i18n import Locale, t
from app.services.command_router import CommandRouter
from app.services.money_format import format_inr, format_signed_inr
from app.services.snapshot import Snapshot, is_cash_sufficient

MENU_PROMPT = "Reply 1 Cash, 2 Collections, 3 Suppliers, 4 Dealer Risk"

UNKNOWN_INPUT_REPLY = f"I didn't understand that.\n{MENU_PROMPT}\nOr send your Tally export file."
UNKNOWN_INPUT_NOTIFICATION_TYPE = "whatsapp_unknown_input"


def _due_phrase(due_date: date, today: date, loc: Locale) -> str:
    delta_days = (due_date - today).days
    if delta_days == 0:
        return t("reports.due.today", loc)
    # Weekday name only up to 6 days out — at exactly 7 days, due_date falls
    # on the same weekday as today, so "due Monday" would be ambiguous
    # (today or next week); fall back to an explicit date instead. The weekday
    # name / ISO date are interpolated (not translated), only "due" is words.
    if 0 < delta_days <= 6:
        return t("reports.due.weekday", loc, day=due_date.strftime("%A"))
    return t("reports.due.date", loc, date=due_date.isoformat())


def _late_payment_phrase(count: int, loc: Locale) -> str:
    if count == 0:
        return t("reports.late.none", loc)
    if count == 1:
        return t("reports.late.one", loc)
    return t("reports.late.many", loc, count=count)


def build_cash_position_report(snapshot: Snapshot) -> str:
    # Labels come from the catalog in the company's locale (snapshot.locale);
    # ₹ amounts are interpolated via money_format, never translated.
    loc = snapshot.locale
    lines = [
        t("reports.cash.header", loc),
        "",
        t("reports.cash.available_now", loc, amount=format_inr(snapshot.cash_available_today)),
        t(
            "reports.cash.expected_in",
            loc,
            amount=format_inr(snapshot.expected_collections_7d_total),
        ),
        t("reports.cash.due_out", loc, amount=format_inr(snapshot.expected_payments_7d_total)),
        t("reports.cash.net_expected", loc, amount=format_signed_inr(snapshot.net_cash_position)),
        t("reports.cash.shortage", loc)
        if snapshot.cash_deficit
        else t("reports.cash.no_shortage", loc),
    ]
    return "\n".join(lines)


def build_collections_report(snapshot: Snapshot) -> str:
    loc = snapshot.locale
    today = snapshot.generated_at.date()
    if not snapshot.expected_collections_7d:
        body = [t("reports.collections.none", loc)]
    else:
        body = [
            f"{c.dealer_name} — {format_inr(c.amount)} — {_due_phrase(c.due_date, today, loc)}"
            for c in snapshot.expected_collections_7d
        ]
    lines = [
        t("reports.collections.header", loc),
        "",
        *body,
        "",
        t(
            "reports.collections.total",
            loc,
            amount=format_inr(snapshot.expected_collections_7d_total),
        ),
    ]
    return "\n".join(lines)


def build_suppliers_report(snapshot: Snapshot) -> str:
    loc = snapshot.locale
    today = snapshot.generated_at.date()
    if not snapshot.expected_payments_7d:
        body = [t("reports.suppliers.none", loc)]
    else:
        body = []
        for payment in snapshot.expected_payments_7d:
            line = (
                f"{payment.supplier_name} — {format_inr(payment.amount)} — "
                f"{_due_phrase(payment.due_date, today, loc)}"
            )
            if payment.urgent:
                sufficient = is_cash_sufficient(snapshot.cash_available_today, payment.amount)
                key = "reports.suppliers.cash_ok" if sufficient else "reports.suppliers.cash_short"
                line += f" — {t(key, loc)}"
            body.append(line)
    lines = [
        t("reports.suppliers.header", loc),
        "",
        *body,
        "",
        t("reports.suppliers.total", loc, amount=format_inr(snapshot.expected_payments_7d_total)),
    ]
    return "\n".join(lines)


def build_dealer_risk_report(snapshot: Snapshot) -> str:
    loc = snapshot.locale
    header = t("reports.risk.header", loc)
    if not snapshot.overdue_dealers:
        return "\n".join([header, "", t("reports.risk.none", loc)])

    buckets: dict[str, list] = {"High": [], "Medium": [], "Low": []}
    for dealer in snapshot.overdue_dealers:
        buckets[dealer.risk_level].append(dealer)

    _risk_label_key = {
        "High": "reports.risk.high",
        "Medium": "reports.risk.medium",
        "Low": "reports.risk.low",
    }
    sections = []
    for level in ("High", "Medium", "Low"):
        dealers = buckets[level]
        if not dealers:
            continue
        section_lines = [t(_risk_label_key[level], loc)]
        for dealer in dealers:
            section_lines.append(
                t(
                    "reports.risk.dealer_line",
                    loc,
                    name=dealer.dealer_name,
                    amount=format_inr(dealer.outstanding),
                    days=dealer.days_overdue,
                    late=_late_payment_phrase(dealer.late_payment_count_6mo, loc),
                )
            )
        sections.append("\n".join(section_lines))
    return "\n\n".join([header, *sections])


menu_router: CommandRouter[Snapshot] = CommandRouter()
menu_router.register(
    "1", notification_type="query_menu_cash", build_reply=build_cash_position_report
)
menu_router.register(
    "2", notification_type="query_menu_collections", build_reply=build_collections_report
)
menu_router.register(
    "3", notification_type="query_menu_suppliers", build_reply=build_suppliers_report
)
menu_router.register(
    "4", notification_type="query_menu_dealer_risk", build_reply=build_dealer_risk_report
)
# Slash-command aliases for the same four reports — same handlers, just a
# guessable form so /help's list works without the user memorizing numbers.
menu_router.register(
    "/cash", notification_type="query_menu_cash", build_reply=build_cash_position_report
)
menu_router.register(
    "/collections", notification_type="query_menu_collections", build_reply=build_collections_report
)
menu_router.register(
    "/suppliers", notification_type="query_menu_suppliers", build_reply=build_suppliers_report
)
menu_router.register(
    "/dealer_risk", notification_type="query_menu_dealer_risk", build_reply=build_dealer_risk_report
)
