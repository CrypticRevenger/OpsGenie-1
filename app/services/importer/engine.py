"""ImportEngine — the missing link between the importer architecture and the database.

Everything upstream of this module (``detector``, ``BaseImporter`` subclasses,
``normalizer``, ``ImportResult``, ``log_writer``) already existed and is reused
unchanged. This module is what actually turns parsed rows into ``Invoice`` /
``Payment`` records.

Design invariants (see SPEC.md ImportService + the Phase 3 plan):

* One bad row never fails the whole file — each row runs inside its own
  SAVEPOINT (``db.begin_nested()``); a failure rolls back only that row and
  processing continues. The whole file commits once, at the end.
* Imports are idempotent — re-uploading the same file must not create
  duplicate Invoices/Payments. Invoices dedupe on the existing
  ``(company_id, invoice_number)`` unique constraint. Payments dedupe on a
  composite natural key (see ``payment_row.py`` for why ``voucher_reference``
  alone is not reliable for this).
* LLMs never enter this path — every number here traces to a specific
  imported row.
"""

from __future__ import annotations

import csv
import io
import logging
import uuid
import zipfile
from datetime import date as date_type
from datetime import datetime as datetime_type
from datetime import timedelta
from decimal import Decimal
from typing import Literal

import openpyxl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business_event import BusinessEvent, BusinessEventType
from app.models.dealer import Dealer
from app.models.invoice import Invoice, InvoiceDirection, InvoiceSource, InvoiceStatus
from app.models.supplier import Supplier
from app.services.importer.detector import detect_importer
from app.services.importer.errors import UnrecognisedFormatError, UnsupportedFileError
from app.services.importer.normalizer import (
    normalise_header,
    parse_amount,
    parse_date,
    row_by_normalised_header,
)
from app.services.importer.parties import find_or_create_party
from app.services.importer.result import ImportResult

logger = logging.getLogger(__name__)

Direction = Literal["receivable", "payable"]
FileKind = Literal["invoices", "payments", "products"]

__all__ = [
    "UnrecognisedFormatError",
    "UnsupportedFileError",
    "parse_file",
    "run_import",
]


# ── File parsing ─────────────────────────────────────────────────────────────


def _stringify_cell(value: object) -> str:
    """Stringify one Excel cell for downstream parsing.

    openpyxl deserialises date-formatted cells as ``datetime.datetime`` even
    when the cell holds no time component — ``str()`` on that produces
    "2026-01-05 00:00:00", which normalizer.parse_date's anchored regexes
    reject outright. Dates/datetimes are converted to their ISO date part
    explicitly so a genuine Excel date cell parses the same as a typed-out
    "2026-01-05" string cell.
    """
    if isinstance(value, datetime_type):
        return value.date().isoformat()
    if isinstance(value, date_type):
        return value.isoformat()
    if value is None:
        return ""
    return str(value)


def parse_file(contents: bytes, filename: str) -> tuple[list[str], list[dict[str, str]]]:
    """Parse a CSV or Excel file into (headers, rows), keyed by the *original* header text.

    Cell values are stringified so downstream parsing (``normalizer.parse_date`` /
    ``parse_amount``) always receives text, regardless of source format.

    Raises UnsupportedFileError for anything that isn't a well-formed .csv/.xlsx
    (wrong extension, undecodable bytes, corrupt workbook) — callers should
    treat this as a clean whole-file rejection, not a crash.
    """
    lower = filename.lower()
    if lower.endswith(".csv"):
        try:
            text = contents.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = contents.decode("cp1252")
            except UnicodeDecodeError as exc:
                raise UnsupportedFileError(
                    f"Could not decode {filename!r} as UTF-8 or Windows-1252 text. "
                    "Please re-save the file as UTF-8 CSV."
                ) from exc
        reader = csv.DictReader(io.StringIO(text))
        headers = list(reader.fieldnames or [])
        rows = [{k: (v or "") for k, v in row.items()} for row in reader]
        return headers, rows
    if lower.endswith(".xlsx"):
        try:
            workbook = openpyxl.load_workbook(io.BytesIO(contents), read_only=True, data_only=True)
        except (zipfile.BadZipFile, KeyError) as exc:
            raise UnsupportedFileError(f"{filename!r} is not a valid Excel (.xlsx) file.") from exc
        worksheet = workbook.active
        rows_iter = worksheet.iter_rows(values_only=True)
        try:
            header_row = next(rows_iter)
        except StopIteration:
            return [], []
        headers = [str(h) if h is not None else "" for h in header_row]
        rows = []
        for raw_row in rows_iter:
            if all(cell is None for cell in raw_row):
                continue  # skip fully blank trailing rows
            row = {
                headers[i]: _stringify_cell(raw_row[i])
                for i in range(len(headers))
                if i < len(raw_row)
            }
            rows.append(row)
        return headers, rows
    raise UnsupportedFileError(f"Unsupported file type: {filename!r}. Expected .csv or .xlsx.")


def _resolve_due_date(
    invoice_date: date_type, due_date_raw: str, party: Dealer | Supplier
) -> date_type:
    """No invented payment terms: use the real due_date if given, else the party's
    real payment_terms_days if configured, else due-on-receipt (net-0) — never a
    guessed default like "30 days".
    """
    if due_date_raw.strip():
        return parse_date(due_date_raw)
    if party.payment_terms_days:
        return invoice_date + timedelta(days=party.payment_terms_days)
    return invoice_date


# ── Invoice import (Phase 3A) ────────────────────────────────────────────────


async def _import_invoice_row(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    endpoint_direction: Direction,
    row_number: int,
    raw_row: dict[str, str],
    canonical: dict[str, str],
    voucher_reference: str,
    source_file: str,
    result: ImportResult,
) -> None:
    row_direction_raw = canonical.get("direction", "").strip().lower()
    row_direction: Direction = row_direction_raw or endpoint_direction  # type: ignore[assignment]
    if row_direction not in ("receivable", "payable"):
        raise ValueError(f"invalid direction '{row_direction_raw}'")
    if row_direction_raw and row_direction_raw != endpoint_direction:
        raise ValueError(
            f"row direction '{row_direction_raw}' conflicts with "
            f"requested import direction '{endpoint_direction}'"
        )

    invoice_number = canonical["invoice_number"].strip()
    if not invoice_number:
        raise ValueError("invoice_number is required")
    party_name = canonical["party_name"].strip()
    if not party_name:
        raise ValueError("party_name is required")

    invoice_date = parse_date(canonical["invoice_date"])
    total_amount = parse_amount(canonical["total_amount"])
    gst_amount = (
        parse_amount(canonical["gst_amount"])
        if canonical.get("gst_amount", "").strip()
        else Decimal("0.00")
    )
    subtotal = (
        parse_amount(canonical["subtotal"])
        if canonical.get("subtotal", "").strip()
        else total_amount - gst_amount
    )

    party = await find_or_create_party(db, company_id, row_direction, party_name)
    due_date = _resolve_due_date(invoice_date, canonical.get("due_date", ""), party)

    existing = await db.scalar(
        select(Invoice).where(
            Invoice.company_id == company_id,
            Invoice.invoice_number == invoice_number,
        )
    )
    if existing is not None:
        party_id = party.id
        existing_party_id = (
            existing.dealer_id if row_direction == "receivable" else existing.supplier_id
        )
        if (
            existing.invoice_date == invoice_date
            and existing.total_amount == total_amount
            and existing.direction == InvoiceDirection(row_direction)
            and existing_party_id == party_id
        ):
            result.add_skipped(row_number, f"invoice {invoice_number} already imported")
            return
        raise ValueError(f"invoice {invoice_number} already exists with different data")

    invoice = Invoice(
        company_id=company_id,
        invoice_number=invoice_number,
        direction=InvoiceDirection(row_direction),
        dealer_id=party.id if row_direction == "receivable" else None,
        supplier_id=party.id if row_direction == "payable" else None,
        invoice_date=invoice_date,
        due_date=due_date,
        subtotal=subtotal,
        gst_amount=gst_amount,
        total_amount=total_amount,
        status=InvoiceStatus.Pending,
        source=InvoiceSource.csv_import,
    )
    db.add(invoice)
    await db.flush()

    db.add(
        BusinessEvent(
            company_id=company_id,
            event_type=BusinessEventType.invoice_created,
            entity_type="invoice",
            entity_id=invoice.id,
            payload={
                "invoice_number": invoice_number,
                "voucher_reference": voucher_reference,
                "source_file": source_file,
                "row_number": row_number,
                "party_name": party_name,
                "total_amount": str(total_amount),
            },
            created_by="import",
        )
    )
    result.add_success()


async def run_import(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    direction: Direction | None,
    file_kind: FileKind,
    filename: str,
    contents: bytes,
) -> ImportResult:
    """Parse and persist a CSV/Excel file. Raises UnsupportedFileError /
    UnrecognisedFormatError for whole-file rejections; per-row problems are
    captured in the returned ImportResult, never raised.

    ``direction`` is required for "invoices"/"payments" (receivable vs.
    payable) but ignored for "products" — products have no direction, so
    callers importing a product/stock file pass None.
    """
    source_format = "csv" if filename.lower().endswith(".csv") else "excel"
    result = ImportResult(filename=filename, source_format=source_format)

    headers, rows = parse_file(contents, filename)

    if file_kind == "products":
        from app.services.importer.product_row import run_product_import

        return await run_product_import(
            db,
            company_id=company_id,
            filename=filename,
            headers=headers,
            rows=rows,
            result=result,
        )

    if file_kind == "payments":
        from app.services.importer.payment_row import run_payment_import

        return await run_payment_import(
            db,
            company_id=company_id,
            direction=direction,
            filename=filename,
            headers=headers,
            rows=rows,
            result=result,
        )

    importer_cls = detect_importer(headers)
    if importer_cls is None:
        raise UnrecognisedFormatError(
            "No importer recognised this file's columns. "
            "Expected a Tally, Vyapar, or OpsGenie canonical export."
        )
    normalised_headers = [normalise_header(h) for h in headers]
    header_map = importer_cls.map_headers(normalised_headers)
    missing = importer_cls.validate_required(header_map)
    if missing:
        raise UnrecognisedFormatError(f"Missing required columns: {', '.join(missing)}")

    for row_number, raw_row in enumerate(rows, start=1):
        try:
            async with db.begin_nested():
                normalised_row = row_by_normalised_header(raw_row, headers)
                canonical = importer_cls.normalise_row(normalised_row, header_map)
                voucher_reference = (
                    canonical.get("voucher_reference", "").strip()
                    or canonical.get("invoice_number", "").strip()
                )
                source_file = canonical.get("source_file", "").strip() or filename
                await _import_invoice_row(
                    db,
                    company_id=company_id,
                    endpoint_direction=direction,
                    row_number=row_number,
                    raw_row=raw_row,
                    canonical=canonical,
                    voucher_reference=voucher_reference,
                    source_file=source_file,
                    result=result,
                )
        except Exception as exc:  # noqa: BLE001 - row-level isolation is intentional
            logger.warning("Row %d failed in %s: %s", row_number, filename, exc)
            result.add_failure(row_number, str(exc), raw_value=str(raw_row))

    await db.commit()
    return result
