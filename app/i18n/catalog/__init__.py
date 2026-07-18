"""Per-locale message catalogs, keyed by locale code.

English (``en``) is the complete source of truth; the other catalogs mirror
its keys and English is the runtime fallback for any key missing from a
non-English catalog. tests/test_i18n.py enforces key parity + placeholder
consistency across all catalogs.
"""

from __future__ import annotations

from app.i18n.catalog import en, hi_deva, hi_latn, or_latn, or_orya

CATALOGS: dict[str, dict[str, str]] = {
    "en": en.MESSAGES,
    "hi-Deva": hi_deva.MESSAGES,
    "hi-Latn": hi_latn.MESSAGES,
    "or-Orya": or_orya.MESSAGES,
    "or-Latn": or_latn.MESSAGES,
}
