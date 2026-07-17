"""Shared KSA geo / VPN resolution (Cloudflare header + MaxMind fallback)."""

import logging
import secrets
from fastapi import HTTPException, Request

from app.config import settings
from app.services import maxmind

logger = logging.getLogger(__name__)


def is_trusted_proxy(request: Request) -> bool:
    supplied = request.headers.get("X-Backend-Proxy-Secret", "")
    configured = settings.BACKEND_PROXY_SECRET.strip()
    return bool(configured and supplied and secrets.compare_digest(supplied, configured))


def require_trusted_proxy(request: Request) -> None:
    if settings.BACKEND_PROXY_SECRET.strip() and not is_trusted_proxy(request):
        raise HTTPException(status_code=403, detail="Request must use the trusted storefront.")


def get_client_ip(request: Request) -> str:
    if is_trusted_proxy(request):
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
    cf_country = ""
    if is_trusted_proxy(request):
        cf_country = (
            request.headers.get("X-CF-IPCountry") or request.headers.get("CF-IPCountry", "")
        ).upper().strip()

    if cf_country and cf_country != "SA":
        geo = {
            "ip": ip,
            "country_code": cf_country,
            "city": None,
            "is_vpn": cf_country == "T1",
            "is_proxy": False,
            "is_suspicious": True,
            "is_allowed": False,
        }
        logger.info("Trusted proxy country rejected: country=%s", cf_country)
        return geo

    # A trusted SA header is only a fast country gate; MaxMind must still detect VPNs.
    geo = await maxmind.check_ip(ip)
    geo["ip"] = ip
    return geo
