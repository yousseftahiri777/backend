import logging
import asyncio
from fastapi import APIRouter, Request
from app.schemas import ContactSchema
from app.config import settings
from app.services.geo import require_trusted_proxy
import httpx

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/contact", status_code=202)
async def submit_contact(payload: ContactSchema, request: Request):
    require_trusted_proxy(request)
    logger.info("Contact form accepted")

    if settings.CONTACT_WEBHOOK_URL:
        asyncio.create_task(_forward_to_webhook(payload))

    return {"accepted": True}


async def _forward_to_webhook(payload: ContactSchema) -> None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                settings.CONTACT_WEBHOOK_URL,
                json={
                    "type": "contact",
                    "name": payload.name,
                    "email": payload.email,
                    "message": payload.message,
                },
            )
    except Exception as exc:
        logger.error("Contact webhook failed: %s", exc)
