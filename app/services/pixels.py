import hashlib
import logging
import time
import httpx
from app.config import settings

logger = logging.getLogger(__name__)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode()).hexdigest()


async def send_fb_capi(event_data: dict) -> None:
    if not settings.FB_ACCESS_TOKEN or not settings.FB_PIXEL_ID:
        return

    url = f"https://graph.facebook.com/v21.0/{settings.FB_PIXEL_ID}/events"
    user_data = event_data.get("user_data", {})

    hashed_user_data = {}
    if user_data.get("ph"):
        hashed_user_data["ph"] = [_sha256(user_data["ph"])]
    if user_data.get("em"):
        hashed_user_data["em"] = [_sha256(user_data["em"])]
    if user_data.get("client_ip_address"):
        hashed_user_data["client_ip_address"] = user_data["client_ip_address"]
    if user_data.get("client_user_agent"):
        hashed_user_data["client_user_agent"] = user_data["client_user_agent"]
    if user_data.get("fbc"):
        hashed_user_data["fbc"] = user_data["fbc"]
    if user_data.get("fbp"):
        hashed_user_data["fbp"] = user_data["fbp"]

    payload = {
        "data": [
            {
                "event_name": event_data.get("event_name", "Purchase"),
                "event_id": event_data.get("event_id", ""),
                "event_time": event_data.get("event_time", int(time.time())),
                "event_source_url": "https://lamabeauty.shop",
                "action_source": "website",
                "user_data": hashed_user_data,
                "custom_data": event_data.get("custom_data", {}),
            }
        ],
        "access_token": settings.FB_ACCESS_TOKEN,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            logger.info("FB CAPI event sent: %s", event_data.get("event_name"))
    except Exception as exc:
        logger.error("FB CAPI failed: %s", exc)


async def send_tiktok_events(event_data: dict) -> None:
    if not settings.TIKTOK_ACCESS_TOKEN or not settings.TIKTOK_PIXEL_ID:
        return

    url = "https://business-api.tiktok.com/open_api/v1.3/event/track/"
    user_data = event_data.get("user_data", {})
    custom_data = event_data.get("custom_data", {})

    properties = {}
    if custom_data.get("currency"):
        properties["currency"] = custom_data["currency"]
    if custom_data.get("value") is not None:
        properties["value"] = custom_data["value"]
    if custom_data.get("order_id"):
        properties["order_id"] = custom_data["order_id"]

    context = {
        "ad": {},
        "page": {"url": "https://lamabeauty.shop"},
        "ip": user_data.get("client_ip_address", ""),
        "user_agent": user_data.get("client_user_agent", ""),
    }

    contact = {}
    if user_data.get("ph"):
        contact["phone_number"] = _sha256(user_data["ph"])
    if user_data.get("em"):
        contact["email"] = _sha256(user_data["em"])

    payload = {
        "pixel_code": settings.TIKTOK_PIXEL_ID,
        "event": event_data.get("event_name", "Purchase"),
        "event_id": event_data.get("event_id", ""),
        "timestamp": str(event_data.get("event_time", int(time.time()))),
        "context": context,
        "properties": properties,
        "type": "track",
    }
    if contact:
        payload["context"]["user"] = contact

    headers = {"Access-Token": settings.TIKTOK_ACCESS_TOKEN}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            logger.info("TikTok event sent: %s", event_data.get("event_name"))
    except Exception as exc:
        logger.error("TikTok Events API failed: %s", exc)


async def send_snap_capi(event_data: dict) -> None:
    if not settings.SNAP_ACCESS_TOKEN or not settings.SNAP_PIXEL_ID:
        return

    url = "https://tr.snapchat.com/v2/conversion"
    user_data = event_data.get("user_data", {})
    custom_data = event_data.get("custom_data", {})

    hashed_phone = _sha256(user_data["ph"]) if user_data.get("ph") else None
    hashed_email = _sha256(user_data["em"]) if user_data.get("em") else None

    snap_user_data = {
        "client_ip_address": user_data.get("client_ip_address", ""),
    }
    if hashed_phone:
        snap_user_data["phone_number"] = hashed_phone
    if hashed_email:
        snap_user_data["email"] = hashed_email

    payload = {
        "pixel_id": settings.SNAP_PIXEL_ID,
        "event_conversion_type": "WEB",
        "event_type": event_data.get("event_name", "PURCHASE").upper(),
        "event_tag": event_data.get("event_id", ""),
        "timestamp": event_data.get("event_time", int(time.time())) * 1000,
        "hashed_data_fields": snap_user_data,
        "price": custom_data.get("value"),
        "currency": custom_data.get("currency", "SAR"),
        "order_id": custom_data.get("order_id"),
    }

    headers = {"Authorization": f"Bearer {settings.SNAP_ACCESS_TOKEN}"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            logger.info("Snapchat CAPI event sent: %s", event_data.get("event_name"))
    except Exception as exc:
        logger.error("Snapchat CAPI failed: %s", exc)
