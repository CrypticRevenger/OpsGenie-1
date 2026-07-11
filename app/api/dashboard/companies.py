"""Dashboard company routes — list/create/detail hub + the three
subscription-lifecycle actions (activate/pause/delete). Every write here
calls straight into the corresponding app/api/admin/companies.py function
in-process (no HTTP round-trip) so the dashboard never re-implements
business logic that already lives in the JSON admin API.
"""

from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.exceptions import HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.briefing import get_latest_briefing as api_get_latest_briefing
from app.api.admin.cashflow import get_cashflow as api_get_cashflow
from app.api.admin.companies import (
    activate_subscription as api_activate_subscription,
)
from app.api.admin.companies import (
    create_company as api_create_company,
)
from app.api.admin.companies import (
    deactivate_subscription as api_deactivate_subscription,
)
from app.api.admin.companies import (
    delete_company as api_delete_company,
)
from app.api.admin.companies import (
    get_company as api_get_company,
)
from app.api.admin.companies import (
    list_companies as api_list_companies,
)
from app.api.admin.daily_snapshot import get_month_summary as api_get_month_summary
from app.api.admin.daily_snapshot import get_today_snapshot as api_get_today_snapshot
from app.api.admin.dealers import list_dealers as api_list_dealers
from app.api.admin.faq import list_faqs as api_list_faqs
from app.api.admin.invoices import list_invoices as api_list_invoices
from app.api.admin.payments import list_payments as api_list_payments
from app.api.admin.products import list_products as api_list_products
from app.api.admin.suppliers import list_suppliers as api_list_suppliers
from app.core.config import get_settings
from app.core.templates import templates
from app.db.session import get_db
from app.models.company import Company
from app.models.product import Product
from app.schemas.company import CompanyCreate
from app.services.snapshot import business_now

router = APIRouter()

# Big enough that a real pilot company's full catalogue/dealer list/etc.
# fits on one page — this hub deliberately doesn't paginate sub-resources,
# unlike the JSON admin API's list endpoints.
_HUB_LIST_LIMIT = 200


def _format_briefing_hour(company: Company) -> str:
    """Render the hour the scheduler actually dispatches this company's
    morning briefing at (app/core/scheduler.py compares local hour ==
    briefing_hour), 12h-clock, business-local. Falls back to the global
    BRIEFING_HOUR default and says so when the company hasn't overridden it
    (set during onboarding — see app/services/onboarding_flow.py).
    """
    hour = company.briefing_hour
    is_default = hour is None
    if is_default:
        hour = get_settings().briefing_hour
    period = "AM" if hour < 12 else "PM"
    display_hour = hour % 12 or 12
    suffix = " (default)" if is_default else ""
    return f"{display_hour}:00 {period} {company.timezone}{suffix}"


@router.get("", response_class=HTMLResponse, summary="Company list")
async def companies_list(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    page = await api_list_companies(page=1, limit=200, db=db)

    # A per-company product count so the list gives a hint of catalogue size
    # without opening every company's detail hub (which is where the full
    # "Inventory Products" table already lives) — one grouped query, not N+1.
    company_ids = [c.id for c in page.items]
    product_counts: dict[uuid.UUID, int] = {}
    if company_ids:
        result = await db.execute(
            select(Product.company_id, func.count())
            .where(Product.company_id.in_(company_ids))
            .group_by(Product.company_id)
        )
        product_counts = dict(result.all())

    briefing_hours = {c.id: _format_briefing_hour(c) for c in page.items}

    return templates.TemplateResponse(
        request,
        "dashboard/companies_list.html",
        {
            "companies": page.items,
            "product_counts": product_counts,
            "briefing_hours": briefing_hours,
            "error": None,
        },
    )


@router.get("/new", response_class=HTMLResponse, summary="Create-company form")
async def company_new_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "dashboard/company_new.html", {"error": None})


@router.post("/new", summary="Create a company", response_model=None)
async def company_create(
    request: Request,
    business_name: str = Form(...),
    owner_name: str = Form(...),
    whatsapp_number: str = Form(...),
    email: str = Form(""),
    business_type: str = Form(""),
    preferred_language: str = Form("en"),
    timezone: str = Form("Asia/Kolkata"),
    opening_balance: str = Form("0"),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    try:
        payload = CompanyCreate(
            business_name=business_name,
            owner_name=owner_name,
            whatsapp_number=whatsapp_number,
            email=email or None,
            business_type=business_type or None,
            preferred_language=preferred_language,
            timezone=timezone,
            opening_balance=Decimal(opening_balance or "0"),
        )
    except (ValidationError, InvalidOperation) as exc:
        return templates.TemplateResponse(
            request,
            "dashboard/company_new.html",
            {"error": str(exc)},
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    try:
        company = await api_create_company(payload, db)
    except HTTPException as exc:
        return templates.TemplateResponse(
            request,
            "dashboard/company_new.html",
            {"error": exc.detail},
            status_code=exc.status_code,
        )
    return RedirectResponse(
        url=f"/dashboard/companies/{company.id}", status_code=status.HTTP_303_SEE_OTHER
    )


@router.get("/{company_id}", response_class=HTMLResponse, summary="Company detail hub")
async def company_detail(
    request: Request,
    company_id: uuid.UUID,
    error: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    company = await api_get_company(company_id, db)

    dealers_page = await api_list_dealers(company_id, page=1, limit=_HUB_LIST_LIMIT, db=db)
    suppliers_page = await api_list_suppliers(company_id, page=1, limit=_HUB_LIST_LIMIT, db=db)
    products_page = await api_list_products(company_id, page=1, limit=_HUB_LIST_LIMIT, db=db)
    faqs_page = await api_list_faqs(company_id, page=1, limit=_HUB_LIST_LIMIT, db=db)
    invoices_page = await api_list_invoices(
        company_id,
        direction=None,
        status_filter=None,
        dealer_id=None,
        supplier_id=None,
        page=1,
        limit=_HUB_LIST_LIMIT,
        db=db,
    )
    payments_page = await api_list_payments(
        company_id,
        dealer_id=None,
        supplier_id=None,
        invoice_id=None,
        page=1,
        limit=_HUB_LIST_LIMIT,
        db=db,
    )

    try:
        briefing = await api_get_latest_briefing(company_id, db)
    except HTTPException:
        # No briefing generated yet — the template just shows a "Generate"
        # prompt instead of a 404 bubbling up to the whole hub page.
        briefing = None

    cashflow = await api_get_cashflow(company_id, db)

    today_local = business_now(company.timezone).date()
    daily_snapshot = await api_get_today_snapshot(company_id, db)
    month_summary = await api_get_month_summary(
        company_id, year=today_local.year, month=today_local.month, db=db
    )

    # Payments only carry invoice_id, and invoices only carry dealer_id/
    # supplier_id — build name lookups once here so the template can show
    # "Ram Traders" instead of a bare UUID without a per-row query.
    dealer_names = {d.id: d.name for d in dealers_page.items}
    supplier_names = {s.id: s.name for s in suppliers_page.items}
    invoice_numbers = {inv.id: inv.invoice_number for inv in invoices_page.items}

    return templates.TemplateResponse(
        request,
        "dashboard/company_detail.html",
        {
            "company": company,
            "dealers": dealers_page.items,
            "suppliers": suppliers_page.items,
            "products": products_page.items,
            "faqs": faqs_page.items,
            "invoices": invoices_page.items,
            "payments": payments_page.items,
            "dealer_names": dealer_names,
            "supplier_names": supplier_names,
            "invoice_numbers": invoice_numbers,
            "briefing": briefing,
            "briefing_hour_display": _format_briefing_hour(company),
            "cashflow": cashflow,
            "daily_snapshot": daily_snapshot,
            "month_summary": month_summary,
            "error": error,
        },
    )


@router.post("/{company_id}/activate", summary="Activate a company's subscription")
async def company_activate(
    company_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> RedirectResponse:
    await api_activate_subscription(company_id, db)
    return RedirectResponse(
        url=f"/dashboard/companies/{company_id}", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/{company_id}/deactivate", summary="Pause a company's subscription")
async def company_deactivate(
    company_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> RedirectResponse:
    await api_deactivate_subscription(company_id, db)
    return RedirectResponse(
        url=f"/dashboard/companies/{company_id}", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/{company_id}/delete", summary="Permanently delete a company")
async def company_delete(
    company_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> RedirectResponse:
    await api_delete_company(company_id, db)
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
