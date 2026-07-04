"""Pydantic schemas for the CSV/Excel import endpoint response."""

from __future__ import annotations

from pydantic import BaseModel


class ImportRowError(BaseModel):
    """A single row-level problem, surfaced back to the caller."""

    row: int
    reason: str


class ImportResponse(BaseModel):
    """Summary returned after a CSV/Excel import — mirrors the WhatsApp spec's
    "Import complete — 47 of 50 rows processed" pattern.
    """

    filename: str
    source_format: str
    rows_processed: int
    rows_succeeded: int
    rows_skipped: int
    rows_failed: int
    errors: list[ImportRowError]
