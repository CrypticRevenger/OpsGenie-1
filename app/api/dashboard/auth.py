"""Dashboard login/logout — the only two routes NOT behind
require_dashboard_session (see app/api/dashboard/__init__.py).
"""

from __future__ import annotations

from fastapi import APIRouter, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.config import get_settings
from app.core.dashboard_auth import clear_session_cookie, issue_session_cookie, verify_password
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
    if not verify_password(password):
        return templates.TemplateResponse(
            request,
            "dashboard/login.html",
            {"error": "Incorrect password."},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    settings = get_settings()
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    issue_session_cookie(response, is_development=settings.is_development)
    return response


@router.post("/logout", summary="Clear the dashboard session")
async def logout() -> RedirectResponse:
    response = RedirectResponse(url="/dashboard/login", status_code=status.HTTP_303_SEE_OTHER)
    clear_session_cookie(response)
    return response
