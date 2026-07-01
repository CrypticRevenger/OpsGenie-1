"""Reusable SQLAlchemy ORM mixins.

These add common columns (id, created_at) without repeating them in every
model.  The database schema is unchanged — the same columns are produced.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column


class UUIDMixin:
    """UUID primary key using PostgreSQL-native uuid type.

    Uses :func:`uuid.uuid4` as the default so every insert gets a unique id
    even before the row reaches the database.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    """Appends a server-controlled ``created_at`` timestamp.

    ``server_default=func.now()`` means the database sets the value on INSERT,
    keeping the application layer out of time management.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
