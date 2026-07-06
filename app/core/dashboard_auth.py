"""Password-gated session auth for the server-rendered admin dashboard
(app/api/dashboard/) — distinct from require_api_key (app/core/auth.py),
which gates the JSON admin API via a static X-API-Key header a browser can't
attach on normal navigation.

Deliberately simple: one shared secret (DASHBOARD_PASSWORD), no rotation or
per-session expiry beyond a fixed cookie lifetime — the same trust model as
ADMIN_API_KEY itself. Acceptable for a solo-founder internal tool; easy to
harden later (real per-user accounts, short-lived tokens) if this ever stops
being a single-operator tool.
"""

from __future__ import annotations

import hashlib
import secrets

from fastapi import Request
from starlette.responses import Response

from app.core.config import get_settings

SESSION_COOKIE_NAME = "opsgenie_dashboard_session"
SESSION_MAX_AGE_SECONDS = 14 * 24 * 60 * 60  # 14 days


class DashboardAuthRequired(Exception):
    """Raised by require_dashboard_session when the session cookie is
    missing, wrong, or DASHBOARD_PASSWORD isn't configured. Handled in
    app/core/exceptions.py to redirect to the login page instead of
    returning a JSON error — this is a browser flow, not an API caller.
    """


def _session_token(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(password: str) -> bool:
    """Fails closed: an unconfigured DASHBOARD_PASSWORD always rejects,
    same convention as require_api_key.
    """
    settings = get_settings()
    if not settings.dashboard_password:
        return False
    return secrets.compare_digest(password, settings.dashboard_password)


def issue_session_cookie(response: Response, *, is_development: bool) -> None:
    settings = get_settings()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=_session_token(settings.dashboard_password or ""),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=not is_development,
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME)


async def require_dashboard_session(request: Request) -> None:
    settings = get_settings()
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if not settings.dashboard_password or not cookie or not secrets.compare_digest(
        cookie, _session_token(settings.dashboard_password)
    ):
        raise DashboardAuthRequired()
