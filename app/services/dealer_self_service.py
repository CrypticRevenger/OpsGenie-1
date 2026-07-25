"""Dealer self-service over WhatsApp — read-only, Phases 1-2.

A dealer texts the distributor's own WhatsApp number directly and gets back
their own outstanding balance / next due date / last payment (Phase 1), or a
signed download link to their own ledger statement (Phase 2), without ever
going through the founder. This is a structurally separate path from the
founder's command ladder in app/api/webhooks/whatsapp.py: it never touches
Company.active_workflow / onboarding_state / active_pending_operation_id /
pending_follow_up_invoice_id (the founder's own conversation-state pointers),
is fully stateless (every reply computed fresh from live data, nothing to
resume after a crash beyond the webhook's existing message-dedup), and never
reaches the LLM — every reply is a fixed, deterministic formatter over real
data, same philosophy as app/services/instant_reports.py.

Opt-in per company (Company.dealer_self_service_enabled, default False) — the
founder's own decision to expose financial data to inbound senders identified
only by phone number. See find_dealer_company's docstring for why an
ambiguous phone match is refused rather than resolved.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.i18n import resolve_locale, t
from app.models.company import Company
from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceDirection, InvoiceStatus
from app.models.payment import Payment
from app.services.company_export import generate_export_link
from app.services.money_format import format_inr
from app.services.party_outstanding import calculate_party_outstanding
from app.services.reports.period import resolve_period
from app.services.reports.registry import REPORTS
from app.services.snapshot import business_now

# Duplicated locally rather than imported from party_outstanding.py's private
# _OPEN_STATUSES — this codebase already repeats this exact tuple verbatim in
# snapshot.py/company_export.py rather than reaching into another module's
# private name, so this follows the same established precedent.
_OPEN_STATUSES = (InvoiceStatus.Pending, InvoiceStatus.Partially_Paid, InvoiceStatus.Overdue)


@dataclass(frozen=True)
class DealerMatch:
    company: Company
    dealer: Dealer


class Ambiguous:
    """Sentinel: the inbound phone matches a Dealer row in more than one
    company (or more than one dealer row at all — see find_dealer_company).
    """


async def find_dealer_company(db: AsyncSession, phone: str) -> DealerMatch | Ambiguous | None:
    """Resolve an inbound WhatsApp sender (already normalized to the same
    E.164-ish form Dealer.phone is stored in — see
    app/api/webhooks/whatsapp.py::_normalize_to_e164) to the (company,
    dealer) it belongs to. Scoped to companies that have opted into dealer
    self-service and are still an active subscriber; a company that hasn't
    enabled this returns no match here, same as any other unrecognized
    sender.

    A phone matching more than one Dealer row — whether under the same
    company or, worse, two different companies — is a real (if vanishingly
    rare at pilot scale) cross-company data-leak risk: silently picking
    "the first one" could hand one dealer's own balance to a phone that
    also happens to be on file for a completely different business. So this
    never resolves an ambiguous match automatically — the caller must treat
    Ambiguous as "do not proceed," never as "proceed with the first match."
    """
    rows = (
        await db.execute(
            select(Dealer, Company)
            .join(Company, Company.id == Dealer.company_id)
            .where(
                Dealer.phone == phone,
                Company.dealer_self_service_enabled.is_(True),
                Company.subscription_active.is_(True),
            )
        )
    ).all()
    if not rows:
        return None
    if len(rows) > 1:
        return Ambiguous()
    dealer, company = rows[0]
    return DealerMatch(company=company, dealer=dealer)


async def dealer_balance_reply(db: AsyncSession, company: Company, dealer: Dealer) -> str:
    """Hi <dealer>, here's your account with <business>: outstanding / next
    due / last payment — each optional line omitted (not zero-filled) when
    there's nothing to show, rather than a dozen template variants for every
    combination. Scoped to this one dealer only via calculate_party_outstanding
    (already company/party-scoped, unchanged) and dealer_id-filtered queries
    below — structurally unable to leak another dealer's or the company's
    aggregate data.
    """
    loc = resolve_locale(company)
    outstanding = await calculate_party_outstanding(db, direction="receivable", party_id=dealer.id)

    next_due = await db.scalar(
        select(Invoice.due_date)
        .where(
            Invoice.dealer_id == dealer.id,
            Invoice.direction == InvoiceDirection.receivable,
            Invoice.status.in_(_OPEN_STATUSES),
        )
        .order_by(Invoice.due_date.asc())
        .limit(1)
    )

    last_payment = (
        await db.execute(
            select(Payment.amount, Payment.payment_date)
            .join(Invoice, Invoice.id == Payment.invoice_id)
            .where(
                Invoice.dealer_id == dealer.id,
                Invoice.direction == InvoiceDirection.receivable,
            )
            .order_by(Payment.payment_date.desc(), Payment.created_at.desc())
            .limit(1)
        )
    ).first()

    lines = [
        t(
            "dealer.balance.header",
            loc,
            dealer_name=dealer.name,
            business_name=company.business_name,
        )
    ]
    if outstanding > 0:
        lines.append(t("dealer.balance.outstanding", loc, amount=format_inr(outstanding)))
    else:
        lines.append(t("dealer.balance.no_outstanding", loc))
    if next_due is not None:
        lines.append(t("dealer.balance.next_due", loc, date=next_due.strftime("%d %b %Y")))
    if last_payment is not None:
        amount, payment_date = last_payment
        lines.append(
            t(
                "dealer.balance.last_payment",
                loc,
                amount=format_inr(amount),
                date=payment_date.strftime("%d %b %Y"),
            )
        )
    return "\n".join(lines)


def _current_month_str(company: Company) -> str:
    today = business_now(company.timezone).date()
    return f"{today.year:04d}-{today.month:02d}"


async def dealer_statement_reply(db: AsyncSession, company: Company, dealer: Dealer) -> str:
    """Phase 2 — ledger/statement PDF on request. Same signed-export-link
    mechanism `_report_link_reply` (app/api/webhooks/whatsapp.py) uses for
    the founder, scoped to just this one dealer's own ledger via `party_id`.

    Unlike the founder's own report links, `party_id` here is a real access-
    control boundary rather than a convenience: the export link's signature
    covers `party_id` (see company_export.py::generate_export_link), so this
    dealer can never edit the resulting link's `party` query param to reach
    another dealer's or the company's own data — verify_export_link rejects
    a link whose party doesn't match what was actually signed.
    """
    settings = get_settings()
    loc = resolve_locale(company)
    if not settings.export_link_secret or not settings.public_base_url:
        return t("dealer.statement.not_configured", loc, business_name=company.business_name)

    spec = REPORTS["ledger"]
    month = _current_month_str(company)
    period_label = resolve_period(month_str=month).label

    excel_link = generate_export_link(
        company,
        base_url=settings.public_base_url,
        report="ledger",
        month=month,
        party_id=dealer.id,
    )
    lines = [f"Excel: {excel_link}"]
    if spec.build_pdf is not None:
        pdf_link = generate_export_link(
            company,
            base_url=settings.public_base_url,
            report="ledger",
            format="pdf",
            month=month,
            party_id=dealer.id,
        )
        lines.append(f"PDF: {pdf_link}")

    return t(
        "dealer.statement.ready",
        loc,
        business_name=company.business_name,
        period=period_label,
        ttl=settings.export_link_ttl_minutes,
        links="\n".join(lines),
    )


def dealer_help_reply(company: Company) -> str:
    """Deliberately minimal — just the real commands, not a padded list. The
    less a dealer has to remember, the better.
    """
    return t("dealer.help", resolve_locale(company))


async def _dealer_help_command(db: AsyncSession, company: Company, dealer: Dealer) -> str:
    return dealer_help_reply(company)


# Deterministic exact-match dispatch, same spirit as _INSTANT_COMMANDS in
# app/api/webhooks/whatsapp.py but intentionally a separate, much smaller
# table — never merged with the founder's, since a dealer must never reach
# any founder-only command through this path.
_DEALER_COMMANDS: dict[str, Callable[[AsyncSession, Company, Dealer], Awaitable[str]]] = {
    "balance": dealer_balance_reply,
    "my balance": dealer_balance_reply,
    "outstanding": dealer_balance_reply,
    "dues": dealer_balance_reply,
    "how much do i owe": dealer_balance_reply,
    "statement": dealer_statement_reply,
    "my statement": dealer_statement_reply,
    "ledger": dealer_statement_reply,
    "my ledger": dealer_statement_reply,
    "help": _dealer_help_command,
}


async def handle_dealer_message(
    db: AsyncSession, company: Company, dealer: Dealer, text: str
) -> str:
    """Resolve a dealer-origin message. Never raises, never touches the LLM,
    never falls through to anything the founder's ladder can reach.
    """
    handler = _DEALER_COMMANDS.get(text.strip().lower())
    if handler is not None:
        return await handler(db, company, dealer)
    return t("dealer.unrecognized", resolve_locale(company))
