"""Shared-key admin authentication — Phase 6.

A single static API key protects every /admin/* route (see app/main.py,
where this is wired as a router-level dependency). There is no User model,
login flow, or session state — this is still a single-founder tool, per
SPEC.md: "Authentication / API keys | When external users are onboarded."
"""

from __future__ import annotations

import logging
import secrets

from fastapi import Header, HTTPException, status

from app.core.config import get_settings

logger = logging.getLogger(__name__)


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Reject the request unless X-API-Key matches ADMIN_API_KEY.

    Fails closed: an unconfigured key rejects every request rather than
    silently allowing traffic through. The client-facing message is always
    the same generic "Unauthorized" regardless of the reason (missing key,
    wrong key, or server not configured) — the specific reason is logged
    server-side only, so a caller probing the API can't distinguish "the
    server is misconfigured" from "my key is wrong" from the response alone.
    """
    settings = get_settings()
    if not settings.admin_api_key:
        logger.warning("Rejected request: ADMIN_API_KEY is not configured on the server.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    if not x_api_key or not secrets.compare_digest(x_api_key, settings.admin_api_key):
        logger.warning("Rejected request: missing or invalid X-API-Key.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
