"""Format detector — identifies which importer handles a given set of headers.

Usage
-----
::

    from app.services.importer.detector import detect_importer

    importer_cls = detect_importer(headers)
    if importer_cls is None:
        # unsupported format — reject the file

Design
------
Detection order matters.  CanonicalImporter is tried first because its
detection criterion (presence of the 'direction' column) is unambiguous.
TallyImporter is tried second because it is the primary target format.
VyaparImporter is tried third.

Adding a new importer (e.g. BusyImporter):
  1. Create ``app/services/importer/busy.py`` implementing ``BaseImporter``.
  2. Import it here and add it to ``REGISTERED_IMPORTERS`` in priority order.
  That's it.  No other file changes required.
"""

from __future__ import annotations

import logging

from app.services.importer.base import BaseImporter
from app.services.importer.canonical import CanonicalImporter
from app.services.importer.normalizer import normalise_header
from app.services.importer.tally import TallyImporter
from app.services.importer.vyapar import VyaparImporter

logger = logging.getLogger(__name__)

# ── Registry — order determines priority ──────────────────────────────────────
# Canonical is first because its detection criterion is unambiguous.
# Format-specific importers follow in descending specificity.
REGISTERED_IMPORTERS: list[type[BaseImporter]] = [
    CanonicalImporter,
    TallyImporter,
    VyaparImporter,
    # Add BusyImporter, ZohoImporter, etc. here
]


def detect_importer(raw_headers: list[str]) -> type[BaseImporter] | None:
    """Return the first importer class that recognises the file's headers.

    Parameters
    ----------
    raw_headers:
        Column headers as read directly from the file (any case, any spacing).

    Returns
    -------
    type[BaseImporter] | None
        The matched importer class, or ``None`` if no registered importer
        recognises the file.
    """
    normalised = [normalise_header(h) for h in raw_headers]

    for importer_cls in REGISTERED_IMPORTERS:
        if importer_cls.detect(normalised):
            logger.info(
                "Detected format: %s (headers: %s)",
                importer_cls.SOURCE_NAME,
                normalised,
            )
            return importer_cls

    logger.warning(
        "No importer matched headers: %s",
        normalised,
    )
    return None
