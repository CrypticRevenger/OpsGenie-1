"""Admin API package — assembles company, dealer, supplier routers."""

from fastapi import APIRouter

from app.api.admin.companies import router as companies_router
from app.api.admin.dealers import router as dealers_router
from app.api.admin.suppliers import router as suppliers_router

router = APIRouter(prefix="/admin")

router.include_router(companies_router)
router.include_router(dealers_router)
router.include_router(suppliers_router)
