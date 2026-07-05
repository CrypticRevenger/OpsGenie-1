"""add_company_active_pending_operation_id

Revision ID: 8524a9dbfe0c
Revises: 2bc6f7619fe6
Create Date: 2026-07-06 03:18:25.798252

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8524a9dbfe0c"
down_revision: str | None = "2bc6f7619fe6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("active_pending_operation_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_companies_active_pending_operation_id",
        "companies",
        "pending_operations",
        ["active_pending_operation_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_companies_active_pending_operation_id", "companies", type_="foreignkey")
    op.drop_column("companies", "active_pending_operation_id")
