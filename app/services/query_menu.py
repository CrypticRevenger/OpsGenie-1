"""Numbered query menu — SPEC.md V0.1 Step 12.

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

from app.services.command_router import CommandRouter
from app.services.money_format import format_inr, format_signed_inr
from app.services.snapshot import Snapshot, is_cash_sufficient

MENU_PROMPT = "Reply 1 Cash, 2 Collections, 3 Suppliers, 4 Dealer Risk"

UNKNOWN_INPUT_REPLY = f"I didn't understand that.\n{MENU_PROMPT}\nOr send your Tally export file."
UNKNOWN_INPUT_NOTIFICATION_TYPE = "whatsapp_unknown_input"


def _due_phrase(due_date: date, today: date) -> str:
    delta_days = (due_date - today).days
    if delta_days == 0:
        return "due today"
    # Weekday name only up to 6 days out — at exactly 7 days, due_date falls
    # on the same weekday as today, so "due Monday" would be ambiguous
    # (today or next week); fall back to an explicit date instead.
    if 0 < delta_days <= 6:
        return f"due {due_date.strftime('%A')}"
    return f"due {due_date.isoformat()}"


def _late_payment_phrase(count: int) -> str:
    if count == 0:
        return "pays on time"
    if count == 1:
        return "1 late payment in 6 months"
    return f"{count} late payments in 6 months"


def build_cash_position_report(snapshot: Snapshot) -> str:
    lines = [
        "💰 Cash Position",
        "",
        f"Available now: {format_inr(snapshot.cash_available_today)}",
        f"Expected in (7 days): {format_inr(snapshot.expected_collections_7d_total)}",
        f"Due out (7 days): {format_inr(snapshot.expected_payments_7d_total)}",
        f"Net expected: {format_signed_inr(snapshot.net_cash_position)}",
        "Shortage expected this week."
        if snapshot.cash_deficit
        else "No shortage expected this week.",
    ]
    return "\n".join(lines)


def build_collections_report(snapshot: Snapshot) -> str:
    today = snapshot.generated_at.date()
    if not snapshot.expected_collections_7d:
        body = ["No collections expected in the next 7 days."]
    else:
        body = [
            f"{c.dealer_name} — {format_inr(c.amount)} — {_due_phrase(c.due_date, today)}"
            for c in snapshot.expected_collections_7d
        ]
    lines = [
        "📥 Outstanding Collections",
        "",
        *body,
        "",
        f"Total expected this week: {format_inr(snapshot.expected_collections_7d_total)}",
    ]
    return "\n".join(lines)


def build_suppliers_report(snapshot: Snapshot) -> str:
    today = snapshot.generated_at.date()
    if not snapshot.expected_payments_7d:
        body = ["No supplier payments due in the next 7 days."]
    else:
        body = []
        for payment in snapshot.expected_payments_7d:
            line = (
                f"{payment.supplier_name} — {format_inr(payment.amount)} — "
                f"{_due_phrase(payment.due_date, today)}"
            )
            if payment.urgent:
                sufficient = is_cash_sufficient(snapshot.cash_available_today, payment.amount)
                line += " — cash sufficient" if sufficient else " — cash may be insufficient"
            body.append(line)
    lines = [
        "📤 Supplier Payments Due",
        "",
        *body,
        "",
        f"Total due this week: {format_inr(snapshot.expected_payments_7d_total)}",
    ]
    return "\n".join(lines)


def build_dealer_risk_report(snapshot: Snapshot) -> str:
    header = "⚠ Dealer Risk Summary"
    if not snapshot.overdue_dealers:
        return "\n".join([header, "", "No overdue dealers right now."])

    buckets: dict[str, list] = {"High": [], "Medium": [], "Low": []}
    for dealer in snapshot.overdue_dealers:
        buckets[dealer.risk_level].append(dealer)

    sections = []
    for level in ("High", "Medium", "Low"):
        dealers = buckets[level]
        if not dealers:
            continue
        section_lines = [f"{level} Risk:"]
        for dealer in dealers:
            section_lines.append(
                f"{dealer.dealer_name} — {format_inr(dealer.outstanding)} overdue "
                f"({dealer.days_overdue}d) — {_late_payment_phrase(dealer.late_payment_count_6mo)}"
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
