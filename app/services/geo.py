"""Shared KSA geo / VPN resolution (Cloudflare header + MaxMind fallback)."""

import logging
from fastapi import Request

from app.services import maxmind

logger = logging.getLogger(__name__)


def get_client_ip(request: Request) -> str:
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "127.0.0.1"


async def resolve_geo(request: Request, ip: str | None = None) -> dict:
    """Return geo dict with is_allowed=True only for valid KSA, non-VPN traffic."""
    ip = ip or get_client_ip(request)
    cf_country = (
        request.headers.get("X-CF-IPCountry") or request.headers.get("CF-IPCountry", "")
    ).upper().strip()

    if cf_country and cf_country not in ("", "XX", "T1"):
        is_allowed = cf_country == "SA"
        geo = {
            "ip": ip,
            "country_code": cf_country,
            "city": None,
            "is_vpn": cf_country == "T1",
            "is_proxy": False,
            "is_suspicious": not is_allowed,
            "is_allowed": is_allowed,
        }
        logger.info("Cloudflare country check: IP=%s country=%s allowed=%s", ip, cf_country, is_allowed)
        return geo

    geo = await maxmind.check_ip(ip)
    geo["ip"] = ip
    return geo
