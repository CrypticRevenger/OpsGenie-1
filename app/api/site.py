"""Public marketing site — landing page + static legal/contact pages.

No auth (distributors and prospects reach these), no POST handlers (no
contact-form backend exists — the contact page shows plain contact details).
Content lists live in app/content/landing.py (shared with
scripts/build_static_site.py, the Vercel static-site build step) rather than
here, so that build script doesn't need this module's FastAPI import.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.content.landing import (
    BUILT_FOR,
    COMPARISON,
    FAQ,
    HOW_IT_WORKS,
    OUTCOMES,
    PRICING_FEATURES,
)
from app.core.templates import templates

router = APIRouter(tags=["site"])

# Relative on Render, where /onboard is served by this same app.
# scripts/build_static_site.py overrides this to the absolute Render URL when
# pre-rendering these same templates for the separate Vercel static deploy.
ONBOARD_URL = "/onboard"


@router.get("/", response_class=HTMLResponse, summary="Marketing landing page")
async def landing_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "outcomes": OUTCOMES,
            "built_for": BUILT_FOR,
            "how_it_works": HOW_IT_WORKS,
            "comparison": COMPARISON,
            "pricing_features": PRICING_FEATURES,
            "faq": FAQ,
            "onboard_url": ONBOARD_URL,
        },
    )


@router.get("/privacy", response_class=HTMLResponse, summary="Privacy policy")
async def privacy_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "privacy.html", {"onboard_url": ONBOARD_URL})


@router.get("/terms", response_class=HTMLResponse, summary="Terms of service")
async def terms_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "terms.html", {"onboard_url": ONBOARD_URL})


@router.get("/contact", response_class=HTMLResponse, summary="Contact page")
async def contact_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "contact.html", {"onboard_url": ONBOARD_URL})
