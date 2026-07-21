"""add early-warning alert enum values (cash/stock/pre-due forecasts)

Adds the ActivityEntityType/ActivityEventType/BusinessEventType members
needed for the three new proactive forecast alerts: cash-shortage forecast
(company-level, BusinessEvent dedup only), stock-out forecast (per-product,
needs a new "product" ActivityEntityType), and pre-due invoice nudge
(per-dealer, reuses the existing "dealer" ActivityEntityType). See
app/services/notifications.py's check_cash_shortage_forecast/
check_stock_out_forecasts/check_predue_invoice_nudges.

Revision ID: e2a5f8c14d76
Revises: 7d1b678eb1e3
Create Date: 2026-07-22

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e2a5f8c14d76"
down_revision: str | None = "7d1b678eb1e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Autogenerate doesn't detect additions to a native Postgres enum type —
    # hand-written, per the project's migration playbook.
    op.execute("ALTER TYPE activityentitytype ADD VALUE IF NOT EXISTS 'product'")
    op.execute("ALTER TYPE activityeventtype ADD VALUE IF NOT EXISTS 'stock_out_forecast_sent'")
    op.execute("ALTER TYPE activityeventtype ADD VALUE IF NOT EXISTS 'predue_nudge_sent'")
    op.execute("ALTER TYPE businesseventtype ADD VALUE IF NOT EXISTS 'cash_shortage_forecast_sent'")
    op.execute("ALTER TYPE businesseventtype ADD VALUE IF NOT EXISTS 'stock_out_forecast_sent'")
    op.execute("ALTER TYPE businesseventtype ADD VALUE IF NOT EXISTS 'predue_nudge_sent'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE — additive, no-op-if-unused,
    # not worth a full type rebuild.
    pass
