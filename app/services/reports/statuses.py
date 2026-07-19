"""Invoice-status filters shared by every report builder in this package —
one definition instead of each builder redeclaring the same tuple.
"""

from __future__ import annotations

from app.models.invoice import InvoiceStatus

# A report never shows a Draft (not yet issued) or Cancelled (voided)
# invoice as a real transaction.
EXCLUDED_STATUSES = (InvoiceStatus.Draft, InvoiceStatus.Cancelled)

# "Currently open" — the same three statuses party_outstanding.py and
# company_export.py already treat as unpaid/outstanding.
OPEN_STATUSES = (InvoiceStatus.Pending, InvoiceStatus.Partially_Paid, InvoiceStatus.Overdue)
