"""Payment import — Phase 3B.

Receipt/Payment vouchers name a party and an amount, never an invoice number
(confirmed against every real voucher in the Phase 3 dataset). So this module
does two things standard CSV importers don't need to:

1. Reuses BaseImporter's contract (map_headers/validate_required/normalise_row)
   for a lightweight canonical payment shape — no format-specific subclasses
   needed, real-world payment exports are far less varied than invoice exports.
2. FIFO-allocates each payment across the party's open invoices, oldest
   invoice_date first, splitting across invoices when one payment covers more
   than the oldest invoice's remaining balance. A payment that outsizes the
   party's *total* open balance (real-world case: a receipt also clears part
   of an opening balance that predates every invoice actually on file, e.g.
   Siddha Mahaveer Agencies in the Phase 3 dataset — one ₹57,747 invoice on
   file against ₹1,10,000 of receipts) still pays off everything currently
   open in full here rather than being rejected wholesale — see
   allocate_payment_fifo's `allow_partial_allocation`.

Idempotency note: the extracted real payment register's printed "No." turned
out to be a recurring ledger/account code (e.g. "35" = bank account), reused
across dozens of genuinely distinct transactions — not a unique document
serial. So dedup here keys on (party, payment_date, amount) instead, checked
against previously-written BusinessEvent payloads. voucher_reference is still
preserved in that payload as metadata, just not used as the dedup key.

allocate_payment_fifo is public (not import-only) — Phase 2A's
app/services/writes/payments.py::record_payment reuses it for WhatsApp-guided
payment recording, passing source=PaymentSource.whatsapp.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date as date_type
from decimal import Decimal
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business_event import BusinessEvent, BusinessEventType
from app.models.invoice import Invoice, InvoiceDirection, InvoiceStatus
from app.models.payment import Payment, PaymentSource
from app.services.importer.base import BaseImporter
from app.services.importer.errors import UnrecognisedFormatError
from app.services.importer.normalizer import (
    normalise_header,
    parse_date,
    parse_positive_amount,
    row_by_normalised_header,
)
from app.services.importer.parties import find_or_create_party
from app.services.importer.result import ImportResult

logger = logging.getLogger(__name__)

Direction = Literal["receivable", "payable"]


class PaymentImporter(BaseImporter):
    """Canonical payment row shape, reusing BaseImporter's header-mapping contract."""

    SOURCE_NAME = "payment"

    REQUIRED_CANONICAL_COLUMNS = {"party_name", "payment_date", "amount"}

    COLUMN_ALIASES: dict[str, str] = {
        # ── Party ───────────────────────────────────────────────────────
        "party_name": "party_name",
        "account": "party_name",
        "particulars": "party_name",
        "customer_name": "party_name",
        "vendor_name": "party_name",
        "dealer_name": "party_name",
        "supplier_name": "party_name",
        # ── Date ────────────────────────────────────────────────────────
        "payment_date": "payment_date",
        "dated": "payment_date",
        "date": "payment_date",
        # ── Amount ──────────────────────────────────────────────────────
        "amount": "amount",
        "amount_paid": "amount",
        "paid_amount": "amount",
        # ── Method (optional) ──────────────────────────────────────────
        "method": "method",
        "through": "method",
        "mode": "method",
        "payment_mode": "method",
        # ── Provenance (optional) ──────────────────────────────────────
        "voucher_reference": "voucher_reference",
        "source_file": "source_file",
    }


def _source_row_key(
    direction: str, party_name: str, payment_date: date_type, amount: Decimal
) -> str:
    return f"{direction}|{party_name.lower()}|{payment_date.isoformat()}|{amount}"


async def _already_imported(db: AsyncSession, company_id: uuid.UUID, source_row_key: str) -> bool:
    existing = await db.scalar(
        select(BusinessEvent.id).where(
            BusinessEvent.company_id == company_id,
            BusinessEvent.event_type == BusinessEventType.payment_received,
            BusinessEvent.payload["source_row_key"].astext == source_row_key,
        )
    )
    return existing is not None


async def open_invoices_with_outstanding(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    direction: Direction,
    party_id: uuid.UUID,
    invoice_id: uuid.UUID | None = None,
) -> list[tuple[Invoice, Decimal]]:
    """Every open (Pending/Partially_Paid) invoice for one party, oldest
    first, paired with its own remaining balance (total_amount minus
    payments already recorded against it). `invoice_id` narrows to a single
    invoice when the caller already knows which one — same query shape
    either way, so allocate_payment_fifo and the "record payment" guided
    flow's invoice-picker (app/services/workflows/payment_flow.py) share one
    query pattern instead of two near-identical ones.
    """
    party_column = Invoice.dealer_id if direction == "receivable" else Invoice.supplier_id
    stmt = select(Invoice).where(
        Invoice.company_id == company_id,
        Invoice.direction == InvoiceDirection(direction),
        party_column == party_id,
        Invoice.status.in_([InvoiceStatus.Pending, InvoiceStatus.Partially_Paid]),
    )
    if invoice_id is not None:
        stmt = stmt.where(Invoice.id == invoice_id)
    stmt = stmt.order_by(Invoice.invoice_date, Invoice.invoice_number)
    open_invoices = list((await db.execute(stmt)).scalars().all())
    if not open_invoices:
        return []

    # One grouped query for all open invoices' paid-to-date, instead of one
    # SUM query per invoice (was O(rows x open invoices) per payment file).
    invoice_ids = [invoice.id for invoice in open_invoices]
    paid_rows = await db.execute(
        select(Payment.invoice_id, func.sum(Payment.amount))
        .where(Payment.invoice_id.in_(invoice_ids))
        .group_by(Payment.invoice_id)
    )
    paid_by_invoice: dict[uuid.UUID, Decimal] = dict(paid_rows.all())
    return [
        (invoice, invoice.total_amount - paid_by_invoice.get(invoice.id, Decimal("0.00")))
        for invoice in open_invoices
    ]


async def allocate_payment_fifo(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    direction: Direction,
    party_id: uuid.UUID,
    party_name: str,
    amount: Decimal,
    payment_date: date_type,
    method: str,
    voucher_reference: str,
    source_file: str,
    row_number: int,
    source_row_key: str,
    source: PaymentSource = PaymentSource.csv_import,
    created_by: str = "import",
    invoice_id: uuid.UUID | None = None,
    allow_partial_allocation: bool = False,
) -> list[tuple[Invoice, Decimal, Payment]]:
    """Returns the (invoice, amount_allocated, payment) splits actually made —
    the CSV import path ignores this; app/services/writes/payments.py's
    record_payment uses it to report which invoices a WhatsApp-recorded
    payment touched.

    `invoice_id` targets one specific invoice (re-validated fresh here, same
    "never trust the preview" contract as every PendingOperation-backed
    write) instead of spreading the payment across every open invoice —
    set when the WhatsApp guided flow's invoice-picker resolved to (or the
    user explicitly chose) a single invoice. None preserves the original
    FIFO-across-all-open-invoices behavior, unchanged for CSV imports (which
    never name an invoice) and for a party with only one open invoice.

    `allow_partial_allocation` (default False, preserving the original
    all-or-nothing behavior for every existing caller — WhatsApp's
    record_payment and writes/orders.py both leave it off) exists for
    run_payment_import's bulk CSV/PDF path specifically. A live WhatsApp
    conversation has a human to correct an amount that's too big for what's
    on file; a historical import doesn't — rejecting the whole payment there
    just because it doesn't map cleanly onto today's known invoices (e.g. it
    also covers part of an opening balance that predates every invoice
    actually on file for that party) silently overstates that party's
    outstanding forever, even though the source document proves the money
    was genuinely received. When set and the payment exceeds total
    outstanding, this pays off every currently-open invoice for the party in
    full instead of raising; the unmatched remainder is neither invented as
    a phantom invoice payment nor silently dropped — see the caller for how
    it's surfaced.
    """
    if amount <= 0:
        # Defense-in-depth: run_payment_import already guards this with
        # parse_positive_amount before calling here, but without this check
        # amount<=0 would silently return an empty allocation list below
        # (the loop's `if remaining_to_allocate <= 0: break` exits
        # immediately) — zero Payments written, yet the caller would still
        # see a normal empty-but-not-raised return and record a false
        # success. Every caller (CSV import AND writes/payments.py's
        # record_payment) gets this guarantee, not just the guarded one.
        raise ValueError(f"payment amount must be greater than zero (got {amount})")

    invoices_with_outstanding = await open_invoices_with_outstanding(
        db, company_id=company_id, direction=direction, party_id=party_id, invoice_id=invoice_id
    )
    if not invoices_with_outstanding:
        if invoice_id is not None:
            raise ValueError(f"that invoice for {party_name} is no longer open")
        raise ValueError(f"no outstanding invoice on file for {party_name}")

    open_invoices = [invoice for invoice, _outstanding in invoices_with_outstanding]
    remaining_by_invoice: dict[uuid.UUID, Decimal] = {
        invoice.id: outstanding for invoice, outstanding in invoices_with_outstanding
    }

    total_outstanding = sum(remaining_by_invoice.values(), Decimal("0.00"))
    if amount > total_outstanding:
        # total_outstanding <= 0 means every "open" invoice already nets to
        # zero (a rounding edge case) — there is nothing to apply the
        # payment to even in best-effort mode, so this still raises exactly
        # like the no-open-invoice case above rather than "succeeding" at
        # allocating nothing.
        if not allow_partial_allocation or total_outstanding <= 0:
            raise ValueError(
                f"payment exceeds total outstanding for {party_name} "
                f"(outstanding {total_outstanding}, payment {amount})"
            )
        remaining_to_allocate = total_outstanding
    else:
        remaining_to_allocate = amount
    allocations: list[tuple[Invoice, Decimal, Payment]] = []
    for invoice in open_invoices:
        if remaining_to_allocate <= 0:
            break
        balance = remaining_by_invoice[invoice.id]
        if balance <= 0:
            continue
        allocated = min(balance, remaining_to_allocate)

        payment = Payment(
            company_id=company_id,
            invoice_id=invoice.id,
            amount=allocated,
            payment_date=payment_date,
            method=method or None,
            source=source,
        )
        db.add(payment)
        invoice.status = (
            InvoiceStatus.Paid if allocated == balance else InvoiceStatus.Partially_Paid
        )
        allocations.append((invoice, allocated, payment))
        remaining_to_allocate -= allocated

    await db.flush()  # one round-trip to populate every payment.id, not one per split

    for invoice, allocated, payment in allocations:
        db.add(
            BusinessEvent(
                company_id=company_id,
                event_type=BusinessEventType.payment_received,
                entity_type="payment",
                entity_id=payment.id,
                payload={
                    "invoice_number": invoice.invoice_number,
                    "party_name": party_name,
                    "amount": str(allocated),
                    "voucher_reference": voucher_reference,
                    "source_file": source_file,
                    "row_number": row_number,
                    "source_row_key": source_row_key,
                },
                created_by=created_by,
            )
        )

    return allocations


async def run_payment_import(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    direction: Direction,
    filename: str,
    headers: list[str],
    rows: list[dict[str, str]],
    result: ImportResult,
) -> ImportResult:
    normalised_headers = [normalise_header(h) for h in headers]
    header_map = PaymentImporter.map_headers(normalised_headers)
    missing = PaymentImporter.validate_required(header_map)
    if missing:
        raise UnrecognisedFormatError(f"Missing required columns: {', '.join(missing)}")

    for row_number, raw_row in enumerate(rows, start=1):
        try:
            pdf_parse_error = raw_row.get("_pdf_parse_error", "").strip()
            if pdf_parse_error:
                raise ValueError(pdf_parse_error)
            normalised_row = row_by_normalised_header(raw_row, headers)
            canonical = PaymentImporter.normalise_row(normalised_row, header_map)

            # PaymentImporter has no 'direction' column alias (unlike
            # CanonicalImporter for invoices) — every row in a payments file
            # uses the direction supplied by the endpoint, no per-row override.
            row_direction: Direction = direction

            party_name = canonical["party_name"].strip()
            if not party_name:
                raise ValueError("party_name is required")
            payment_date = parse_date(canonical["payment_date"])
            amount = parse_positive_amount(canonical["amount"])
            method = canonical.get("method", "").strip()
            voucher_reference = canonical.get("voucher_reference", "").strip()
            source_file = canonical.get("source_file", "").strip() or filename

            source_row_key = _source_row_key(row_direction, party_name, payment_date, amount)
            if await _already_imported(db, company_id, source_row_key):
                result.add_skipped(row_number, f"payment for {party_name} already imported")
                continue

            # Deliberately outside the SAVEPOINT below: the party record should
            # exist going forward even if this particular payment can't be
            # allocated (e.g. no invoice on file yet) — that's real progress,
            # not a failed write to discard.
            party = await find_or_create_party(db, company_id, row_direction, party_name)

            async with db.begin_nested():
                allocations = await allocate_payment_fifo(
                    db,
                    company_id=company_id,
                    direction=row_direction,
                    party_id=party.id,
                    party_name=party_name,
                    amount=amount,
                    payment_date=payment_date,
                    method=method,
                    voucher_reference=voucher_reference,
                    source_file=source_file,
                    row_number=row_number,
                    source_row_key=source_row_key,
                    allow_partial_allocation=True,
                )
            applied = sum(
                (allocated for _invoice, allocated, _payment in allocations), Decimal("0.00")
            )
            if applied < amount:
                # allocate_payment_fifo capped this payment at the party's
                # total_outstanding rather than rejecting it outright (see
                # its docstring) — the shortfall genuinely couldn't be matched
                # to any open invoice on file. Not a row failure (the
                # matchable part was applied for real), but must stay
                # traceable rather than a silent, unexplained gap between
                # what this receipt said and what got recorded.
                logger.warning(
                    "Payment row %d in %s: only %s of %s matched an open invoice for "
                    "%s (%s left over, not recorded against any invoice)",
                    row_number,
                    filename,
                    applied,
                    amount,
                    party_name,
                    amount - applied,
                )
            result.add_success()
        except Exception as exc:  # noqa: BLE001 - row-level isolation is intentional
            logger.warning("Payment row %d failed in %s: %s", row_number, filename, exc)
            result.add_failure(row_number, str(exc), raw_value=str(raw_row))

    await db.commit()
    return result
