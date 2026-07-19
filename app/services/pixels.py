import hashlib
import logging
import time
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.phone_utils import format_ksa_phone_international

logger = logging.getLogger(__name__)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode()).hexdigest()


def _is_sha256_hex(value: str) -> bool:
    cleaned = (value or "").strip().lower()
    return len(cleaned) == 64 and all(c in "0123456789abcdef" for c in cleaned)


def _tiktok_phone_hash(phone: str) -> str:
    """Hash E.164 (+9665…) once; leave already-hashed values alone."""
    cleaned = (phone or "").strip()
    if _is_sha256_hex(cleaned):
        return cleaned.lower()
    if cleaned.startswith("+"):
        e164 = cleaned
    else:
        digits = format_ksa_phone_international(cleaned)
        e164 = f"+{digits}" if digits else cleaned
    return _sha256(e164)


def _tiktok_contents(custom_data: dict) -> list[dict]:
    raw = custom_data.get("contents")
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        content_id = item.get("content_id") or item.get("productId") or item.get("id")
        if not content_id:
            continue
        entry: dict = {
            "content_id": str(content_id),
            "content_type": item.get("content_type") or "product",
        }
        if item.get("nameAr") or item.get("content_name"):
            entry["content_name"] = str(item.get("content_name") or item.get("nameAr"))
        qty = item.get("quantity") if item.get("quantity") is not None else item.get("qty")
        if qty is not None:
            entry["quantity"] = int(qty)
        if item.get("price") is not None:
            entry["price"] = float(item["price"])
        out.append(entry)
    return out


async def send_fb_capi(event_data: dict) -> None:
    if not settings.FB_ACCESS_TOKEN or not settings.FB_PIXEL_ID:
        return

    url = f"https://graph.facebook.com/v21.0/{settings.FB_PIXEL_ID}/events"
    user_data = event_data.get("user_data", {})

    hashed_user_data = {}
    if user_data.get("ph"):
        ph = str(user_data["ph"])
        hashed_user_data["ph"] = [ph.lower() if _is_sha256_hex(ph) else _sha256(ph)]
    if user_data.get("em"):
        em = str(user_data["em"])
        hashed_user_data["em"] = [em.lower() if _is_sha256_hex(em) else _sha256(em)]
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


def _build_tiktok_user(user_data: dict) -> dict:
    user: dict = {}
    if user_data.get("ph"):
        user["phone"] = _tiktok_phone_hash(str(user_data["ph"]))
    if user_data.get("em"):
        em = str(user_data["em"]).strip().lower()
        user["email"] = em if _is_sha256_hex(em) else _sha256(em)
    if user_data.get("client_ip_address"):
        user["ip"] = user_data["client_ip_address"]
    if user_data.get("client_user_agent"):
        user["user_agent"] = user_data["client_user_agent"]
    return user


def _build_tiktok_properties(custom_data: dict) -> dict:
    properties: dict = {}
    if custom_data.get("currency"):
        properties["currency"] = custom_data["currency"]
    if custom_data.get("value") is not None:
        properties["value"] = float(custom_data["value"])
    if custom_data.get("order_id"):
        properties["order_id"] = str(custom_data["order_id"])
    contents = _tiktok_contents(custom_data)
    if contents:
        properties["contents"] = contents
        properties["content_type"] = "product"
    content_ids = custom_data.get("content_ids")
    if isinstance(content_ids, list) and content_ids:
        properties["content_ids"] = [str(x) for x in content_ids]
    elif contents:
        properties["content_ids"] = [c["content_id"] for c in contents]
    return properties


async def _post_tiktok(url: str, payload: dict, label: str) -> bool:
    headers = {
        "Access-Token": settings.TIKTOK_ACCESS_TOKEN,
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(url, json=payload, headers=headers)
        try:
            body = response.json()
        except Exception:
            body = {"raw": (response.text or "")[:500]}
        ok = response.status_code < 400 and body.get("code", 0) == 0
        if ok:
            logger.info("TikTok %s OK: %s", label, body.get("message", "ok"))
            return True
        logger.error(
            "TikTok %s failed: status=%s body=%s",
            label,
            response.status_code,
            body,
        )
        return False


async def send_tiktok_events(event_data: dict) -> None:
    """Send web event to TikTok Events API (server). Never raise — logs only."""
    if not settings.TIKTOK_ACCESS_TOKEN or not settings.TIKTOK_PIXEL_ID:
        logger.warning(
            "TikTok CAPI skipped: missing %s",
            "TIKTOK_ACCESS_TOKEN"
            if not settings.TIKTOK_ACCESS_TOKEN
            else "TIKTOK_PIXEL_ID",
        )
        return

    event_name = event_data.get("event_name", "Purchase")
    event_id = str(event_data.get("event_id") or "")
    event_time = int(event_data.get("event_time", int(time.time())))
    user_data = event_data.get("user_data") or {}
    custom_data = event_data.get("custom_data") or {}
    user = _build_tiktok_user(user_data)
    properties = _build_tiktok_properties(custom_data)
    page_url = "https://lamabeauty.shop"

    # Events API 2.0 (what Events Manager Test events expects for Server)
    v2_payload: dict = {
        "event_source": "web",
        "event_source_id": settings.TIKTOK_PIXEL_ID,
        "data": [
            {
                "event": event_name,
                "event_time": event_time,
                "event_id": event_id,
                "user": user,
                "properties": properties,
                "page": {"url": page_url},
            }
        ],
    }
    if settings.TIKTOK_TEST_EVENT_CODE:
        v2_payload["test_event_code"] = settings.TIKTOK_TEST_EVENT_CODE

    try:
        ok = await _post_tiktok(
            "https://business-api.tiktok.com/open_api/v1.3/event/track/",
            v2_payload,
            f"event/track {event_name} id={event_id}",
        )
        if ok:
            logger.info("TikTok event sent: %s event_id=%s", event_name, event_id)
            return
    except Exception as exc:
        logger.error("TikTok event/track exception: %s", exc)

    # Fallback: classic Pixel Track API (same access token / pixel)
    iso_ts = datetime.fromtimestamp(event_time, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    classic_payload: dict = {
        "pixel_code": settings.TIKTOK_PIXEL_ID,
        "event": event_name,
        "event_id": event_id,
        "timestamp": iso_ts,
        "context": {
            "ip": user_data.get("client_ip_address") or "",
            "user_agent": user_data.get("client_user_agent") or "",
            "page": {"url": page_url},
            "user": user,
        },
        "properties": properties,
    }
    if settings.TIKTOK_TEST_EVENT_CODE:
        classic_payload["test_event_code"] = settings.TIKTOK_TEST_EVENT_CODE

    try:
        ok = await _post_tiktok(
            "https://business-api.tiktok.com/open_api/v1.3/pixel/track/",
            classic_payload,
            f"pixel/track {event_name} id={event_id}",
        )
        if ok:
            logger.info(
                "TikTok event sent via pixel/track: %s event_id=%s",
                event_name,
                event_id,
            )
    except Exception as exc:
        logger.error("TikTok pixel/track exception: %s", exc)


async def send_snap_capi(event_data: dict) -> None:
    if not settings.SNAP_ACCESS_TOKEN or not settings.SNAP_PIXEL_ID:
        return

    url = "https://tr.snapchat.com/v2/conversion"
    user_data = event_data.get("user_data", {})
    custom_data = event_data.get("custom_data", {})

    hashed_phone = None
    if user_data.get("ph"):
        hashed_phone = _tiktok_phone_hash(str(user_data["ph"]))
    hashed_email = None
    if user_data.get("em"):
        em = str(user_data["em"])
        hashed_email = em.lower() if _is_sha256_hex(em) else _sha256(em)

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
