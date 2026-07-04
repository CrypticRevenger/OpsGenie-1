"""Generic paginated response wrapper — Phase 6.

One shape shared by every list endpoint (companies, dealers, suppliers,
invoices, payments) rather than a bare array per endpoint, so a client only
has to learn the pattern once.
"""

from __future__ import annotations

import math
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """A single page of results plus enough metadata to know how many pages exist."""

    items: list[T]
    total: int
    page: int
    limit: int
    pages: int

    @classmethod
    def create(cls, *, items: list[T], total: int, page: int, limit: int) -> Page[T]:
        """Compute `pages` once here so no caller has to do the ceil() math itself."""
        pages = math.ceil(total / limit) if total else 0
        return cls(items=items, total=total, page=page, limit=limit, pages=pages)
