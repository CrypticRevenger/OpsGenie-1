"""Guided void-payment / void-order workflows.

Undoes the single most-recently WhatsApp-recorded payment or order for a
company — never CSV-imported history, never a pick-from-a-list. Shape:
an instant-command lookup (there's nothing to ask the user to identify —
"most recent" already resolves it) opens a tiny one-step
active_workflow/workflow_scratch flow just to collect an optional reason,
then hands off to the generic PendingOperation YES/NO gate
(app/services/writes/pending_operation.py) the same way every other guided
write does. The actual void happens in app/services/writes/void.py, re-fetched
fresh at confirm time — this module only ever previews.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import resolve_locale, t
from app.models.company import Company
from app.models.invoice import Invoice, InvoiceSource
from app.models.payment import Payment, PaymentSource
from app.models.pending_operation import PendingOperationType
from app.services.money_format import format_inr
from app.services.onboarding_flow import _is
from app.services.writes.pending_operation import create_pending_operation
from app.services.writes.void import _party_name_for_invoice

# ── Void payment ─────────────────────────────────────────────────────────────


async def start_void_payment_workflow(db: AsyncSession, company: Company) -> str:
    """Instant-command entry point ("undo payment"/"void payment")."""
    loc = resolve_locale(company)
    payment = await db.scalar(
        select(Payment)
        .where(Payment.company_id == company.id, Payment.source == PaymentSource.whatsapp)
        .order_by(Payment.created_at.desc())
        .limit(1)
    )
    if payment is None:
        return t("void.payment_none", loc)

    invoice = await db.get(Invoice, payment.invoice_id)
    party_name = await _party_name_for_invoice(db, invoice) if invoice is not None else "them"
    preview = t(
        "void.payment_preview",
        loc,
        amount=format_inr(payment.amount),
        invoice_number=invoice.invoice_number if invoice is not None else "?",
        party=party_name,
    )
    company.active_workflow = "void_payment"
    company.workflow_scratch = {"payment_id": str(payment.id), "preview": preview}
    return t("void.reason_ask", loc, preview=preview)


async def handle_void_payment_workflow_message(
    db: AsyncSession, company: Company, text: str
) -> str:
    stripped = text.strip()
    loc = resolve_locale(company)
    if _is(stripped, "cancel", "stop"):
        company.active_workflow = None
        company.workflow_scratch = None
        return t("workflow.cancelled", loc)

    scratch = dict(company.workflow_scratch or {})
    reason = None if (not stripped or _is(stripped, "skip")) else stripped
    payload = {"payment_id": scratch["payment_id"], "reason": reason}
    preview = scratch.get("preview", "")
    company.active_workflow = None
    company.workflow_scratch = None
    await create_pending_operation(db, company, PendingOperationType.void_payment, payload)
    return t("void.confirm_prompt", loc, preview=preview)


# ── Void order ───────────────────────────────────────────────────────────────


async def start_void_order_workflow(db: AsyncSession, company: Company) -> str:
    """Instant-command entry point ("undo order"/"void order")."""
    loc = resolve_locale(company)
    invoice = await db.scalar(
        select(Invoice)
        .where(
            Invoice.company_id == company.id,
            Invoice.source == InvoiceSource.whatsapp,
        )
        .order_by(Invoice.created_at.desc())
        .limit(1)
    )
    if invoice is None:
        return t("void.order_none", loc)

    has_payment = await db.scalar(select(Payment.id).where(Payment.invoice_id == invoice.id))
    if has_payment is not None:
        return t("void.order_has_payment", loc, invoice_number=invoice.invoice_number)

    dealer_name = await _party_name_for_invoice(db, invoice)
    preview = t(
        "void.order_preview",
        loc,
        invoice_number=invoice.invoice_number,
        dealer=dealer_name,
        total=format_inr(invoice.total_amount),
    )
    company.active_workflow = "void_order"
    company.workflow_scratch = {"invoice_id": str(invoice.id), "preview": preview}
    return t("void.reason_ask", loc, preview=preview)


async def handle_void_order_workflow_message(db: AsyncSession, company: Company, text: str) -> str:
    stripped = text.strip()
    loc = resolve_locale(company)
    if _is(stripped, "cancel", "stop"):
        company.active_workflow = None
        company.workflow_scratch = None
        return t("workflow.cancelled", loc)

    scratch = dict(company.workflow_scratch or {})
    reason = None if (not stripped or _is(stripped, "skip")) else stripped
    payload = {"invoice_id": scratch["invoice_id"], "reason": reason}
    preview = scratch.get("preview", "")
    company.active_workflow = None
    company.workflow_scratch = None
    await create_pending_operation(db, company, PendingOperationType.void_order, payload)
    return t("void.confirm_prompt", loc, preview=preview)
