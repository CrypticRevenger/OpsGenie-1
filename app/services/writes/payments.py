"""record_payment — Phase 2A deterministic write service.

Called only from app/services/writes/pending_operation.py's
execute_pending_operation, at confirm time. Reuses the exact FIFO allocator
the CSV importer already relies on (app/services/importer/payment_row.py::
allocate_payment_fifo) — same money math, same open-invoice selection, same
raise-on-no-open-invoice / raise-on-exceeds-outstanding behavior. The only
difference from a CSV row is source=PaymentSource.whatsapp and a synthetic,
always-unique source_row_key (the CSV dedup-by-key mechanism doesn't apply
here — the PendingOperation confirm gate plus the webhook's own Meta-message-
id dedup are what prevent a WhatsApp write from being double-processed).

Never commits — the caller (execute_pending_operation) commits once, same
contract as every other write-touching service in this codebase.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.payment import PaymentSource
from app.services.importer.parties import Direction, find_or_create_party
from app.services.importer.payment_row import allocate_payment_fifo
from app.services.party_outstanding import calculate_party_outstanding


@dataclass(frozen=True)
class RecordPaymentResult:
    party_name: str
    amount_allocated: Decimal
    invoice_numbers: list[str]
    remaining_outstanding: Decimal


async def record_payment(
    db: AsyncSession,
    company: Company,
    *,
    direction: Direction,
    party_name: str,
    amount: Decimal,
    payment_date: date_type,
) -> RecordPaymentResult:
    """Record a WhatsApp-guided payment against a party's open invoices.

    Raises ValueError (via allocate_payment_fifo) if the party has no open
    invoice on file, or if amount exceeds their total outstanding — the
    caller turns this into a friendly reply rather than committing bad data.
    """
    party = await find_or_create_party(db, company.id, direction, party_name)

    allocations = await allocate_payment_fifo(
        db,
        company_id=company.id,
        direction=direction,
        party_id=party.id,
        party_name=party_name,
        amount=amount,
        payment_date=payment_date,
        method="",
        voucher_reference="",
        source_file="whatsapp",
        row_number=0,
        source_row_key=f"whatsapp:{uuid.uuid4()}",
        source=PaymentSource.whatsapp,
        created_by="whatsapp_workflow",
    )

    remaining = await calculate_party_outstanding(db, direction=direction, party_id=party.id)

    return RecordPaymentResult(
        party_name=party_name,
        amount_allocated=amount,
        invoice_numbers=[invoice.invoice_number for invoice, _allocated, _payment in allocations],
        remaining_outstanding=remaining,
    )
