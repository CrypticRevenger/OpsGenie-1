"""add_whatsapp_message_id_to_notification_logs

Revision ID: bb45c43cbb7f
Revises: 146a970a5954
Create Date: 2026-07-04 16:43:12.774582

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bb45c43cbb7f"
down_revision: str | None = "146a970a5954"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("notification_logs", sa.Column("whatsapp_message_id", sa.String(), nullable=True))
    op.create_unique_constraint(
        "uq_notification_logs_whatsapp_message_id", "notification_logs", ["whatsapp_message_id"]
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_notification_logs_whatsapp_message_id", "notification_logs", type_="unique"
    )
    op.drop_column("notification_logs", "whatsapp_message_id")
