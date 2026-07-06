"""Server-rendered admin dashboard — password-gated browser UI over the same
business logic the JSON admin API (app/api/admin/) exposes. auth.py's
login/logout routes are the only ones NOT behind require_dashboard_session;
every other sub-router is wrapped with it here, mirroring how admin_router
itself is wrapped with require_api_key once in app/main.py.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse

from app.api.dashboard.auth import router as auth_router
from app.api.dashboard.briefing import router as briefing_router
from app.api.dashboard.companies import router as companies_router
from app.api.dashboard.dealers import router as dealers_router
from app.api.dashboard.faqs import router as faqs_router
from app.api.dashboard.followup import router as followup_router
from app.api.dashboard.imports import router as imports_router
from app.api.dashboard.invoices import router as invoices_router
from app.api.dashboard.payments import router as payments_router
from app.api.dashboard.products import router as products_router
from app.api.dashboard.suppliers import router as suppliers_router
from app.core.dashboard_auth import require_dashboard_session

router = APIRouter(prefix="/dashboard")

router.include_router(auth_router)
router.include_router(
    companies_router,
    prefix="/companies",
    tags=["dashboard:companies"],
    dependencies=[Depends(require_dashboard_session)],
)

# Every sub-router below already carries its own "/companies/{company_id}/..."
# prefix (see each file), so they're included flat rather than nested under
# companies_router — only the session dependency is shared here, mirroring
# how admin_router itself is wrapped with require_api_key once in app/main.py.
for _router in [
    dealers_router,
    suppliers_router,
    products_router,
    faqs_router,
    invoices_router,
    payments_router,
    briefing_router,
    followup_router,
    imports_router,
]:
    router.include_router(_router, dependencies=[Depends(require_dashboard_session)])


@router.get("", dependencies=[Depends(require_dashboard_session)])
async def dashboard_root() -> RedirectResponse:
    """Redirect the bare /dashboard URL to the company list."""
    return RedirectResponse(url="/dashboard/companies")
