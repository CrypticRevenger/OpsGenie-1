"""Webhook receivers — external services call these directly (no X-API-Key)."""

from fastapi import APIRouter

from app.api.webhooks.whatsapp import router as whatsapp_router

router = APIRouter(prefix="/webhooks")

router.include_router(whatsapp_router)
