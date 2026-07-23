"""Password-gated session auth for the server-rendered admin dashboard
(app/api/dashboard/) — distinct from require_api_key (app/core/auth.py),
which gates the JSON admin API via a static X-API-Key header a browser can't
attach on normal navigation.

One shared secret (DASHBOARD_PASSWORD) — the same trust model as
ADMIN_API_KEY itself, still acceptable for a solo-founder internal tool. The
session token itself, though, is a signed, server-verified-expiry HMAC (same
construction as app/services/onboarding_token.py's capability token) rather
than a bare sha256(password): that old scheme's cookie value WAS
sha256(password) verbatim, so a leaked cookie was directly offline-
brute-forceable back to the real password, and it never actually expired —
SESSION_MAX_AGE_SECONDS only told the *browser* when to drop the cookie,
nothing stopped a replayed/extracted cookie being valid forever. Real
per-user accounts / revocable tokens are still out of scope for a
single-operator tool — see check_login_rate_limit below for the other real
gap this closes (no rate limit on login attempts).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque

from fastapi import Request
from starlette.responses import Response

from app.core.config import get_settings

SESSION_COOKIE_NAME = "opsgenie_dashboard_session"
SESSION_MAX_AGE_SECONDS = 14 * 24 * 60 * 60  # 14 days

# In-process sliding-window login limiter. No shared store (Redis etc.)
# exists anywhere in this app; at pilot scale (a single Render web process,
# a solo-founder login) an in-memory limiter is a proportionate fix for a
# route that otherwise has zero brute-force protection — a multi-process
# deployment would need a real shared store instead. Only failed attempts
# count, so a legitimate user mistyping their own password a few times is
# never locked out.
_LOGIN_RATE_LIMIT_MAX_ATTEMPTS = 5
_LOGIN_RATE_LIMIT_WINDOW_SECONDS = 15 * 60
_login_attempts: dict[str, deque[float]] = defaultdict(deque)


class DashboardAuthRequired(Exception):
    """Raised by require_dashboard_session when the session cookie is
    missing, wrong, or DASHBOARD_PASSWORD isn't configured. Handled in
    app/core/exceptions.py to redirect to the login page instead of
    returning a JSON error — this is a browser flow, not an API caller.
    """


class DashboardLoginRateLimited(Exception):
    """Raised by check_login_rate_limit when a client has made too many
    failed login attempts recently — handled inline in
    app/api/dashboard/auth.py's login route (a 429 re-render, not a
    redirect, since DashboardAuthRequired's redirect handler is for the
    session-cookie case, not this one).
    """


def _sign(expires_at: int, secret: str) -> str:
    return hmac.new(
        secret.encode("utf-8"), f"dashboard-session:{expires_at}".encode(), hashlib.sha256
    ).hexdigest()


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
    secret = settings.dashboard_password or ""
    expires_at = int(time.time()) + SESSION_MAX_AGE_SECONDS
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=f"{expires_at}.{_sign(expires_at, secret)}",
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
    if not settings.dashboard_password or not cookie:
        raise DashboardAuthRequired()
    expires_at_raw, sep, signature = cookie.partition(".")
    if not sep:
        raise DashboardAuthRequired()
    try:
        expires_at = int(expires_at_raw)
    except ValueError:
        raise DashboardAuthRequired() from None
    if time.time() > expires_at:
        raise DashboardAuthRequired()
    if not hmac.compare_digest(_sign(expires_at, settings.dashboard_password), signature):
        raise DashboardAuthRequired()


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def check_login_rate_limit(request: Request) -> None:
    """Call before verifying a login attempt. Raises DashboardLoginRateLimited
    if this client has already made _LOGIN_RATE_LIMIT_MAX_ATTEMPTS failed
    attempts within the trailing window.
    """
    now = time.time()
    attempts = _login_attempts[_client_key(request)]
    while attempts and now - attempts[0] > _LOGIN_RATE_LIMIT_WINDOW_SECONDS:
        attempts.popleft()
    if len(attempts) >= _LOGIN_RATE_LIMIT_MAX_ATTEMPTS:
        raise DashboardLoginRateLimited()


def record_failed_login(request: Request) -> None:
    _login_attempts[_client_key(request)].append(time.time())


def record_successful_login(request: Request) -> None:
    _login_attempts.pop(_client_key(request), None)


def reset_login_rate_limit() -> None:
    """Test-only escape hatch — _login_attempts is module-level state that
    would otherwise leak failed attempts across unrelated test functions.
    """
    _login_attempts.clear()
