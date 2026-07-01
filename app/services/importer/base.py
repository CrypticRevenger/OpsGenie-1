"""Abstract base importer — the interface every format-specific importer implements.

Architecture:

    BaseImporter (abstract)
        ├── TallyImporter    — Tally XML/Excel/CSV Sales & Purchase registers
        ├── VyaparImporter   — Vyapar Excel exports
        ├── BusyImporter     — (future) Busy Accounting exports
        └── CanonicalImporter — OpsGenie's own documented CSV format

Each importer is responsible for:
1. Detecting whether it recognises a file's column headers (detect).
2. Mapping source column names to canonical names (map_headers).
3. Asserting that required canonical columns are present (validate_required).
4. Normalising a single row from source column names to canonical column names
   (normalise_row).

Cell-level parsing (dates, amounts) is intentionally delegated to
:mod:`app.services.importer.normalizer` so that it is shared across all
importers.
"""

from __future__ import annotations


class BaseImporter:
    """Defines the interface every format-specific importer must implement.

    Class attributes
    ----------------
    SOURCE_NAME:
        Human-readable source identifier, e.g. ``"tally"``. Used in log
        messages and the API response.

    COLUMN_ALIASES:
        Maps every *normalised* source header variant (lower-case,
        underscores) that this importer recognises to its *canonical*
        column name.  A single canonical column can have many aliases:

        .. code-block:: python

            COLUMN_ALIASES = {
                "voucher_no":   "invoice_number",
                "voucher_no.":  "invoice_number",
                "invoice_no":   "invoice_number",
                "invoice_no.":  "invoice_number",
            }

    REQUIRED_CANONICAL_COLUMNS:
        The set of canonical column names that MUST be resolved from the
        source file before any row is processed.  A missing required column
        rejects the entire import immediately (fail fast, no partial writes).
    """

    SOURCE_NAME: str = ""
    COLUMN_ALIASES: dict[str, str] = {}
    REQUIRED_CANONICAL_COLUMNS: set[str] = set()

    # ── Header detection & mapping ─────────────────────────────────────────

    @classmethod
    def detect(cls, normalised_headers: list[str]) -> bool:
        """Return True if this importer can handle the given file headers.

        The default implementation returns True if *any* of the normalised
        headers appear in COLUMN_ALIASES.  Subclasses may override this
        to require a minimum number of recognisable columns, or to look
        for a "signature" column that uniquely identifies the format.
        """
        return any(h in cls.COLUMN_ALIASES for h in normalised_headers)

    @classmethod
    def map_headers(cls, normalised_headers: list[str]) -> dict[str, str]:
        """Build a mapping of source_header → canonical_name.

        Only headers that appear in COLUMN_ALIASES are included.  Unrecognised
        columns are silently ignored — they may exist in the source file for
        reasons unrelated to OpsGenie.
        """
        return {
            header: cls.COLUMN_ALIASES[header]
            for header in normalised_headers
            if header in cls.COLUMN_ALIASES
        }

    @classmethod
    def validate_required(cls, header_map: dict[str, str]) -> list[str]:
        """Return a list of required canonical columns that are missing.

        An empty list means the file has everything needed to proceed.
        A non-empty list should cause the entire import to be rejected.
        """
        resolved_canonical = set(header_map.values())
        return sorted(cls.REQUIRED_CANONICAL_COLUMNS - resolved_canonical)

    @classmethod
    def normalise_row(
        cls,
        raw_row: dict[str, str],
        header_map: dict[str, str],
    ) -> dict[str, str]:
        """Map a raw source row to a canonical column dict.

        Parameters
        ----------
        raw_row:
            ``{source_column_name: cell_value}`` as read from the file.
        header_map:
            Output of :meth:`map_headers`.

        Returns
        -------
        dict[str, str]
            ``{canonical_column_name: cell_value}``.  Only canonical columns
            present in *header_map* are included.
        """
        return {
            canonical: raw_row[source]
            for source, canonical in header_map.items()
            if source in raw_row
        }

    # ── Metadata ──────────────────────────────────────────────────────────

    @classmethod
    def describe(cls) -> str:
        """Return a short human-readable description for logging."""
        return f"{cls.__name__}(source={cls.SOURCE_NAME!r})"
