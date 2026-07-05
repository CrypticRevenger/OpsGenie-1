"""add_pending_operations_and_workflow_fields

Revision ID: 2bc6f7619fe6
Revises: 13ad66fd41d2
Create Date: 2026-07-06 00:14:30.155544

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "2bc6f7619fe6"
down_revision: str | None = "13ad66fd41d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PENDING_OPERATION_TYPE_ENUM = sa.Enum(
    "record_payment",
    name="pendingoperationtype",
    create_constraint=True,
)


def upgrade() -> None:
    op.add_column("companies", sa.Column("active_workflow", sa.String(), nullable=True))
    op.add_column("companies", sa.Column("workflow_scratch", JSONB(), nullable=True))

    # No separate explicit .create() call here (unlike the add_column-based
    # enum migrations elsewhere in this repo) — op.create_table()'s own DDL
    # emission already creates the enum type as part of creating the table;
    # calling .create() first as well causes a duplicate "CREATE TYPE" and a
    # DuplicateObjectError.
    op.create_table(
        "pending_operations",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("operation_type", _PENDING_OPERATION_TYPE_ENUM, nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_pending_operations_company_id",
        "pending_operations",
        ["company_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_pending_operations_company_id", table_name="pending_operations")
    op.drop_table("pending_operations")
    _PENDING_OPERATION_TYPE_ENUM.drop(op.get_bind(), checkfirst=True)

    op.drop_column("companies", "workflow_scratch")
    op.drop_column("companies", "active_workflow")
