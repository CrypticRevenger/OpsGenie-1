"""Import result dataclasses — format-independent.

These are returned by every importer regardless of whether the source
file was CSV, Excel, or any future format.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RowError:
    """A single row-level failure captured during import."""

    row_number: int  # 1-indexed (header is row 0)
    reason: str
    raw_value: str = ""  # the offending cell or line, for debugging


@dataclass
class ImportResult:
    """Aggregated result returned after processing an entire file.

    Callers inspect this to write the ImportLog and build the API response.
    """

    filename: str
    source_format: str  # "csv" | "excel"
    rows_processed: int = 0
    rows_succeeded: int = 0
    rows_failed: int = 0
    errors: list[RowError] = field(default_factory=list)

    def add_success(self) -> None:
        self.rows_processed += 1
        self.rows_succeeded += 1

    def add_failure(self, row_number: int, reason: str, raw_value: str = "") -> None:
        self.rows_processed += 1
        self.rows_failed += 1
        self.errors.append(RowError(row_number, reason, raw_value))

    @property
    def error_detail_json(self) -> list[dict]:
        """Serialisable list suitable for ImportLog.error_detail_json (JSONB)."""
        return [
            {
                "row": e.row_number,
                "reason": e.reason,
                "raw_value": e.raw_value,
            }
            for e in self.errors
        ]

    @property
    def success(self) -> bool:
        return self.rows_failed == 0

    @property
    def partial(self) -> bool:
        return self.rows_succeeded > 0 and self.rows_failed > 0
