"""
MaxMind GeoIP2 Precision Web Service — Insights endpoint.

Uses the remote API (no local .mmdb file required).
Blocks orders from:
  - Non-KSA IPs (country != SA)
  - VPNs, anonymous proxies, Tor exit nodes, hosting provider IPs

Results are cached in-memory for CACHE_TTL_SECONDS to reduce API costs.

If MAXMIND_ACCOUNT_ID or MAXMIND_LICENSE_KEY are not configured, the service
runs in permissive mode (all requests allowed) — safe for local development.
"""

import base64
import logging
import time
from typing import Optional

import httpx
from app.config import settings

logger = logging.getLogger(__name__)

# ── Cache ──────────────────────────────────────────────────────────────────────
CACHE_TTL_SECONDS = 3600  # re-check each unique IP at most once per hour
_cache: dict[str, tuple[dict, float]] = {}

MAXMIND_INSIGHTS_URL = "https://geoip.maxmind.com/geoip/v2.1/insights/{ip}"


def _build_auth_header() -> Optional[str]:
    account_id = settings.MAXMIND_ACCOUNT_ID.strip()
    license_key = settings.MAXMIND_LICENSE_KEY.strip()
    if not account_id or not license_key:
        return None
    token = base64.b64encode(f"{account_id}:{license_key}".encode()).decode()
    return f"Basic {token}"


def _is_suspicious(traits: dict) -> bool:
    """Return True if any anonymisation or hosting flag is set."""
    flags = [
        "is_anonymous",
        "is_anonymous_vpn",
        "is_anonymous_proxy",
        "is_public_proxy",
        "is_residential_proxy",
        "is_tor_exit_node",
        "is_hosting_provider",
    ]
    return any(traits.get(f) for f in flags)


async def check_ip(ip: str) -> dict:
    """
    Returns a dict:
        country_code  str | None
        city          str | None
        is_vpn        bool
        is_proxy      bool
        is_suspicious bool
        is_allowed    bool   — True only for KSA, non-suspicious IPs
    """
    # ── Cache hit ──────────────────────────────────────────────────────────────
    if ip in _cache:
        result, cached_at = _cache[ip]
        if time.monotonic() - cached_at < CACHE_TTL_SECONDS:
            logger.debug("MaxMind cache hit for %s", ip)
            return result

    # ── Dev / unconfigured mode ────────────────────────────────────────────────
    auth_header = _build_auth_header()
    if auth_header is None:
        logger.warning(
            "MaxMind credentials not configured — geo checks DISABLED, all requests allowed."
        )
        return {
            "country_code": "SA",
            "city": None,
            "is_vpn": False,
            "is_proxy": False,
            "is_suspicious": False,
            "is_allowed": True,
        }

    # ── Skip private / loopback IPs (local dev) ────────────────────────────────
    if ip in ("127.0.0.1", "::1") or ip.startswith(("10.", "192.168.", "172.")):
        logger.debug("Private IP %s — skipping MaxMind lookup, allowing.", ip)
        result = {
            "country_code": "SA",
            "city": None,
            "is_vpn": False,
            "is_proxy": False,
            "is_suspicious": False,
            "is_allowed": True,
        }
        _cache[ip] = (result, time.monotonic())
        return result

    # ── Live API call ──────────────────────────────────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                MAXMIND_INSIGHTS_URL.format(ip=ip),
                headers={
                    "Authorization": auth_header,
                    "Accept": "application/json",
                },
            )

        if resp.status_code == 200:
            data = resp.json()
            traits = data.get("traits", {})
            country_code = data.get("country", {}).get("iso_code") or ""
            city = (
                data.get("city", {}).get("names", {}).get("en")
                or data.get("city", {}).get("names", {}).get("ar")
            )
            is_vpn = bool(traits.get("is_anonymous_vpn"))
            is_proxy = bool(
                traits.get("is_anonymous_proxy") or traits.get("is_public_proxy")
            )
            suspicious = _is_suspicious(traits)
            allowed = country_code == "SA" and not suspicious

            result = {
                "country_code": country_code,
                "city": city,
                "is_vpn": is_vpn,
                "is_proxy": is_proxy,
                "is_suspicious": suspicious,
                "is_allowed": allowed,
            }
            logger.info(
                "MaxMind [%s]: country=%s vpn=%s proxy=%s suspicious=%s allowed=%s",
                ip, country_code, is_vpn, is_proxy, suspicious, allowed,
            )

        elif resp.status_code in (400, 404):
            # Invalid IP format or reserved/bogon — treat as suspicious
            logger.warning("MaxMind returned %s for IP %s — blocking.", resp.status_code, ip)
            result = {
                "country_code": None,
                "city": None,
                "is_vpn": False,
                "is_proxy": False,
                "is_suspicious": True,
                "is_allowed": False,
            }

        else:
            # 5xx or unexpected — fail open (allow) to avoid blocking legit orders
            logger.error(
                "MaxMind API error %s for IP %s — failing open.", resp.status_code, ip
            )
            result = {
                "country_code": None,
                "city": None,
                "is_vpn": False,
                "is_proxy": False,
                "is_suspicious": False,
                "is_allowed": True,
            }

    except httpx.TimeoutException:
        logger.error("MaxMind API timeout for IP %s — failing open.", ip)
        result = {
            "country_code": None,
            "city": None,
            "is_vpn": False,
            "is_proxy": False,
            "is_suspicious": False,
            "is_allowed": True,
        }
    except Exception as exc:
        logger.error("MaxMind unexpected error for IP %s: %s — failing open.", ip, exc)
        result = {
            "country_code": None,
            "city": None,
            "is_vpn": False,
            "is_proxy": False,
            "is_suspicious": False,
            "is_allowed": True,
        }

    _cache[ip] = (result, time.monotonic())
    return result
