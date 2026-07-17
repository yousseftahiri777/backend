import logging
import asyncio
from fastapi import APIRouter
from app.schemas import ContactSchema
from app.config import settings
import httpx

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/contact", status_code=202)
async def submit_contact(payload: ContactSchema):
    logger.info("Contact form from %s (%s)", payload.name, payload.email)

    if settings.GOOGLE_SHEETS_WEBHOOK_URL and "YOUR_SCRIPT_ID" not in settings.GOOGLE_SHEETS_WEBHOOK_URL:
        asyncio.create_task(_forward_to_webhook(payload))

    return {"accepted": True}


async def _forward_to_webhook(payload: ContactSchema) -> None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                settings.GOOGLE_SHEETS_WEBHOOK_URL,
                json={
                    "type": "contact",
                    "name": payload.name,
                    "email": payload.email,
                    "message": payload.message,
                },
            )
    except Exception as exc:
        logger.error("Contact webhook failed: %s", exc)
