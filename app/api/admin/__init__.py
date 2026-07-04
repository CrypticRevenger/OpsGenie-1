"""Admin API package — assembles company, dealer, supplier routers."""

from fastapi import APIRouter

from app.api.admin.briefing import router as briefing_router
from app.api.admin.cashflow import router as cashflow_router
from app.api.admin.companies import router as companies_router
from app.api.admin.dealers import router as dealers_router
from app.api.admin.followup import router as followup_router
from app.api.admin.imports import router as imports_router
from app.api.admin.invoices import router as invoices_router
from app.api.admin.payments import router as payments_router
from app.api.admin.suppliers import router as suppliers_router

router = APIRouter(prefix="/admin")

router.include_router(companies_router)
router.include_router(dealers_router)
router.include_router(suppliers_router)
router.include_router(imports_router)
router.include_router(invoices_router)
router.include_router(payments_router)
router.include_router(cashflow_router)
router.include_router(briefing_router)
router.include_router(followup_router)
