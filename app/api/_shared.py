"""Small shared helpers used across more than one API route file.

Not app/api/dashboard/_shared.py — that one is dashboard-only (redirect/error
conventions for the server-rendered browser flow); this is for anything the
JSON admin API, the signed public export endpoint, and the dashboard all need
identically.
"""

from __future__ import annotations

from urllib.parse import quote


def content_disposition(filename: str) -> str:
    """A `Content-Disposition: attachment` header value safe for any
    business_name, including the Odia/Devanagari names this product ships
    multilingual support for.

    HTTP header values are latin-1 only — Starlette raises a UnicodeEncodeError
    (a 500) the moment a header value contains a character outside that range,
    which every one of this app's three Excel/PDF export entry points hit
    unguarded by building `filename="{business_name}..."` directly. RFC 6266's
    `filename*=UTF-8''<percent-encoded>` form carries the real name for clients
    that support it, alongside an ASCII-safe `filename=` fallback (non-latin-1
    characters replaced) for the ones that don't.
    """
    ascii_fallback = filename.encode("ascii", errors="replace").decode("ascii")
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(filename)}"
