import logging
from datetime import datetime
import httpx
from app.config import settings
from app.phone_utils import format_ksa_phone_international
from app.product_catalog import get_product_sku

logger = logging.getLogger(__name__)


def _parse_created_at(order_data: dict) -> datetime:
    raw = order_data.get("createdAt")
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, str) and raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            pass
    return datetime.utcnow()


def build_sheets_payload(order_data: dict) -> dict:
    """Build payload matching Orders sheet columns."""
    items = order_data.get("items") or []
    created_at = _parse_created_at(order_data)

    product_names = "/".join(str(item.get("nameAr") or item.get("productId") or "") for item in items)
    skus = "/".join(get_product_sku(str(item.get("productId", ""))) for item in items)
    quantities = "/".join(str(item.get("qty", 1)) for item in items)

    return {
        "date": created_at.strftime("%d/%m/%Y"),
        "orderId": order_data.get("orderId", ""),
        "country": "KSA",
        "name": order_data.get("customerName", ""),
        "phone": format_ksa_phone_international(order_data.get("phone", "")),
        "product": product_names,
        "sku": skus,
        "quantity": quantities,
        "totalPrice": order_data.get("total", 0),
        "currency": "SAR",
        "status": "",
    }


async def send_to_sheets(order_data: dict) -> None:
    if not settings.GOOGLE_SHEETS_WEBHOOK_URL:
        logger.warning("GOOGLE_SHEETS_WEBHOOK_URL not configured, skipping.")
        return

    payload = build_sheets_payload(order_data)

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.post(
                settings.GOOGLE_SHEETS_WEBHOOK_URL,
                json=payload,
            )
            response.raise_for_status()
            logger.info("Google Sheets webhook sent for order %s", payload["orderId"])
    except Exception as exc:
        logger.error("Google Sheets webhook failed for order %s: %s", payload.get("orderId"), exc)
