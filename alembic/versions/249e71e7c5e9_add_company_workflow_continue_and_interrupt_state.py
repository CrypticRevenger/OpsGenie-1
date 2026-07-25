"""add_company_workflow_continue_and_interrupt_state

Revision ID: 249e71e7c5e9
Revises: a3c8e5f0d194
Create Date: 2026-07-25 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "249e71e7c5e9"
down_revision: str | None = "a3c8e5f0d194"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "companies", sa.Column("active_workflow_start_trigger", sa.String(), nullable=True)
    )
    op.add_column(
        "companies", sa.Column("pending_workflow_interrupt", sa.String(), nullable=True)
    )
    op.add_column("companies", sa.Column("pending_continue_prompt", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("companies", "pending_continue_prompt")
    op.drop_column("companies", "pending_workflow_interrupt")
    op.drop_column("companies", "active_workflow_start_trigger")
