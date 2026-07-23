"""Dashboard login/logout — the only two routes NOT behind
require_dashboard_session (see app/api/dashboard/__init__.py).
"""

from __future__ import annotations

from fastapi import APIRouter, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.config import get_settings
from app.core.dashboard_auth import (
    DashboardLoginRateLimited,
    check_login_rate_limit,
    clear_session_cookie,
    issue_session_cookie,
    record_failed_login,
    record_successful_login,
    verify_password,
)
from app.core.templates import templates

router = APIRouter()


@router.get("/login", response_class=HTMLResponse, summary="Dashboard login form")
async def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "dashboard/login.html", {"error": None})


@router.post(
    "/login",
    summary="Verify the dashboard password and start a session",
    response_model=None,
)
async def login_submit(
    request: Request, password: str = Form(...)
) -> HTMLResponse | RedirectResponse:
    try:
        check_login_rate_limit(request)
    except DashboardLoginRateLimited:
        return templates.TemplateResponse(
            request,
            "dashboard/login.html",
            {"error": "Too many attempts. Try again in a few minutes."},
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )
    if not verify_password(password):
        record_failed_login(request)
        return templates.TemplateResponse(
            request,
            "dashboard/login.html",
            {"error": "Incorrect password."},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    record_successful_login(request)
    settings = get_settings()
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    issue_session_cookie(response, is_development=settings.is_development)
    return response


@router.post("/logout", summary="Clear the dashboard session")
async def logout() -> RedirectResponse:
    response = RedirectResponse(url="/dashboard/login", status_code=status.HTTP_303_SEE_OTHER)
    clear_session_cookie(response)
    return response
