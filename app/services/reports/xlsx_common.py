"""Shared openpyxl styling primitives for every generated workbook.

Extracted verbatim from app/services/company_export.py (the original
all-time workbook) so the new period-scoped reports in this package render
with the exact same look — bold/frozen/filterable headers, sized columns,
₹/date number formats — instead of a second, drifting copy of the same
styling code. company_export.py imports these back rather than redefining
them, so its own output is byte-for-byte unchanged.
"""

from __future__ import annotations

from datetime import datetime

from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

HEADER_FONT = Font(bold=True, color="FFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
TOTAL_FONT = Font(bold=True)
TOTAL_FILL = PatternFill("solid", fgColor="D9E1F2")

MONEY_FMT = "₹#,##0.00"
QTY_FMT = "#,##0.##"
DATE_FMT = "dd-mmm-yyyy"
NUMBER_FORMATS = {"money": MONEY_FMT, "qty": QTY_FMT, "date": DATE_FMT}

# Columns that need to be wider than the default heuristic to hold their
# typical content without truncating in the sheet view.
WIDE_COLUMNS = {"Details", "Notes", "Address", "Invoice Number", "Business Name"}


def s(value: object) -> str | None:
    """Render an enum/UUID/None as a plain string cell value."""
    if value is None:
        return None
    return str(value)


def autosize(ws: Worksheet, headers: list[str]) -> None:
    for idx, header in enumerate(headers, start=1):
        letter = get_column_letter(idx)
        width = 34 if header in WIDE_COLUMNS else max(len(header) + 6, 14)
        ws.column_dimensions[letter].width = width


def write_header(ws: Worksheet, headers: list[str]) -> None:
    """Bold white-on-blue header row, frozen and filterable, plus sized
    columns — every sheet in every workbook uses this same look. In
    write_only mode, sheet-level properties like freeze_panes only take
    effect if set before the first append(), so this must run before the
    header row is written.
    """
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}1"
    autosize(ws, headers)
    cells = []
    for header in headers:
        cell = WriteOnlyCell(ws, value=header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cells.append(cell)
    ws.append(cells)


def row(ws: Worksheet, values: list, formats: list[str | None]) -> None:
    """Append a data row, wrapping only the cells that need a number format —
    plain values pass through untouched.
    """
    cells = []
    for value, fmt in zip(values, formats, strict=True):
        if fmt is None or value is None:
            cells.append(value)
            continue
        cell = WriteOnlyCell(ws, value=value)
        cell.number_format = NUMBER_FORMATS[fmt]
        cells.append(cell)
    ws.append(cells)


def total_row(ws: Worksheet, values: list, formats: list[str | None]) -> None:
    """Bold, shaded total row — values/formats align positionally with the
    sheet's header, so callers pass None for any column that isn't summed.
    """
    cells = []
    for value, fmt in zip(values, formats, strict=True):
        cell = WriteOnlyCell(ws, value=value)
        cell.font = TOTAL_FONT
        cell.fill = TOTAL_FILL
        if fmt is not None and value is not None:
            cell.number_format = NUMBER_FORMATS[fmt]
        cells.append(cell)
    ws.append(cells)


def write_meta_block(
    ws: Worksheet,
    *,
    report_name: str,
    company_name: str,
    period_label: str,
    generated_at: datetime,
    row_count: int,
) -> None:
    """A small label/value block at the top of a report's primary sheet —
    which report, which company, which period, how many rows, generated
    when — so opening the file (or forwarding it) never leaves the reader
    guessing what they're looking at. Same two-column style
    company_export.py's own Company sheet already uses.
    """
    ws.column_dimensions["A"].width = 20
    ws.column_dimensions["B"].width = 44
    meta_font = Font(bold=True)
    for label, value in [
        ("Report", report_name),
        ("Company", company_name),
        ("Period", period_label),
        ("Rows", row_count),
        ("Generated At", generated_at.isoformat()),
    ]:
        label_cell = WriteOnlyCell(ws, value=label)
        label_cell.font = meta_font
        ws.append([label_cell, value])
    ws.append([])
