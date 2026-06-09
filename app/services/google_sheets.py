import json
import logging
from datetime import datetime
import httpx
from app.config import settings

logger = logging.getLogger(__name__)


async def send_to_sheets(order_data: dict) -> None:
    if not settings.GOOGLE_SHEETS_WEBHOOK_URL:
        logger.warning("GOOGLE_SHEETS_WEBHOOK_URL not configured, skipping.")
        return

    items = order_data.get("items", [])
    item_count = sum(item.get("qty", 1) for item in items) if items else 0
    if item_count <= 1:
        package_tier = 1
    elif item_count == 2:
        package_tier = 2
    else:
        package_tier = 3

    payload = {
        "timestamp": datetime.utcnow().isoformat(),
        "orderId": order_data.get("orderId", ""),
        "customerName": order_data.get("customerName", ""),
        "phone": order_data.get("phone", ""),
        "city": order_data.get("city", ""),
        "items": json.dumps(items, ensure_ascii=False),
        "packageTier": package_tier,
        "upsellAccepted": order_data.get("upsellAccepted", False),
        "totalPaid": order_data.get("total", 0),
        "ipAddress": order_data.get("ipAddress", ""),
        "status": order_data.get("status", "pending_confirmation"),
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                settings.GOOGLE_SHEETS_WEBHOOK_URL,
                json=payload,
            )
            response.raise_for_status()
            logger.info("Google Sheets webhook sent for order %s", payload["orderId"])
    except Exception as exc:
        logger.error("Google Sheets webhook failed for order %s: %s", payload.get("orderId"), exc)
