"""add_missing_foreign_key_indexes

Every company-scoped table already had an index on company_id except three,
and the two party columns invoices are looked up by (dealer_id/supplier_id)
had none at all — so a per-party outstanding balance, a ledger, a statement
PDF, and the register builders all seq-scanned `invoices`, and the FK's own
ON DELETE SET NULL scanned it again per deleted party.

Composite where a second column is always part of the same predicate:

- invoices (dealer_id, status) / (supplier_id, status): every party query in
  party_outstanding.py, payment_row.py::open_invoices_with_outstanding,
  reports/ledger.py and dealer_self_service.py filters the party column plus
  a status set. The party column leads, so the FK's delete-time scan is
  covered too.
- import_logs (company_id, imported_at): snapshot.py::data_freshness_hours
  runs `max(imported_at) where company_id = ?` on every snapshot build — i.e.
  once per company per scheduler tick.
- notification_logs (company_id, sent_at): instant_reports.py's Delivery
  Status report reads the most recent rows for one company, ordered by
  sent_at desc.

invoice_items.invoice_id and cash_snapshots.company_id are plain single-column
indexes — they are only ever looked up by that column alone (the invoice-item
join and the correlated NOT EXISTS in reports/registers.py).

Revision ID: b4d7f0a29c15
Revises: 249e71e7c5e9
Create Date: 2026-08-01 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4d7f0a29c15"
down_revision: str | None = "249e71e7c5e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_invoices_dealer_status", "invoices", ["dealer_id", "status"])
    op.create_index("ix_invoices_supplier_status", "invoices", ["supplier_id", "status"])
    op.create_index("ix_invoice_items_invoice_id", "invoice_items", ["invoice_id"])
    op.create_index("ix_import_logs_company_imported", "import_logs", ["company_id", "imported_at"])
    op.create_index(
        "ix_notification_logs_company_sent", "notification_logs", ["company_id", "sent_at"]
    )
    op.create_index("ix_cash_snapshots_company_id", "cash_snapshots", ["company_id"])


def downgrade() -> None:
    op.drop_index("ix_cash_snapshots_company_id", table_name="cash_snapshots")
    op.drop_index("ix_notification_logs_company_sent", table_name="notification_logs")
    op.drop_index("ix_import_logs_company_imported", table_name="import_logs")
    op.drop_index("ix_invoice_items_invoice_id", table_name="invoice_items")
    op.drop_index("ix_invoices_supplier_status", table_name="invoices")
    op.drop_index("ix_invoices_dealer_status", table_name="invoices")
