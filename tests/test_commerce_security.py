import asyncio
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from starlette.requests import Request

from app.config import settings
from app.product_catalog import price_items
from app.routers.orders import _public_token, _token_hash, _token_matches
from app.schemas import CreateOrderSchema, UpsellUpdateSchema
from app.services import geo
from app.services.pixels import _hash_if_needed


def _request(headers: dict[str, str], client: tuple[str, int] = ("10.0.0.8", 1234)) -> Request:
    raw_headers = [(key.lower().encode(), value.encode()) for key, value in headers.items()]
    return Request({"type": "http", "headers": raw_headers, "client": client})


def test_authoritative_bundle_pricing_and_extra_quantities():
    _, subtotal, shipping, total = price_items(
        [
            {"productId": "sweat-shield", "qty": 2},
            {"productId": "nasma-spray", "qty": 1},
        ]
    )
    assert float(subtotal) == 238
    assert float(shipping) == 0
    assert float(total) == 238

    _, subtotal, shipping, total = price_items(
        [
            {"productId": "sweat-shield", "qty": 1},
            {"productId": "nasma-spray", "qty": 1},
            {"productId": "safaa-patches", "qty": 1},
        ]
    )
    assert (float(subtotal), float(shipping), float(total)) == (199, 0, 199)


def test_order_input_rejects_prices_duplicates_and_invalid_quantities():
    valid = {
        "customerName": "أحمد",
        "phone": "0501234567",
        "city": "الرياض",
        "items": [{"productId": "sweat-shield", "qty": 1}],
        "eventId": "event-12345",
    }
    CreateOrderSchema.model_validate(valid)
    with pytest.raises(ValidationError):
        CreateOrderSchema.model_validate({**valid, "subtotal": 1})
    with pytest.raises(ValidationError):
        CreateOrderSchema.model_validate(
            {**valid, "items": [{"productId": "sweat-shield", "qty": 0}]}
        )
    with pytest.raises(ValidationError):
        CreateOrderSchema.model_validate(
            {
                **valid,
                "items": [
                    {"productId": "sweat-shield", "qty": 1},
                    {"productId": "sweat-shield", "qty": 2},
                ],
            }
        )
    with pytest.raises(ValidationError):
        UpsellUpdateSchema.model_validate(
            {"upsellProduct": "nasma-spray", "upsellPrice": 1}
        )


def test_order_token_hash_challenge():
    token = "public-token"
    order = SimpleNamespace(public_token_hash=_token_hash(token))
    assert _token_matches(order, token)
    assert not _token_matches(order, "wrong-token")
    assert not _token_matches(order, None)


def test_public_order_token_is_deterministic(monkeypatch):
    monkeypatch.setattr(settings, "ORDER_TOKEN_SECRET", "order-token-secret")
    first = _public_token("lama-1", "event-12345")
    second = _public_token("lama-1", "event-12345")
    assert first == second
    assert len(first) == 64


def test_pixel_hashing_does_not_double_hash():
    already_hashed = "a" * 64
    assert _hash_if_needed(already_hashed) == already_hashed
    assert _hash_if_needed("+966501234567") != "+966501234567"


def test_production_security_rejects_missing_secrets(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "BACKEND_PROXY_SECRET", "")
    with pytest.raises(RuntimeError, match="Missing required production settings"):
        settings.validate_runtime_security()


def test_forwarded_headers_require_proxy_secret(monkeypatch):
    monkeypatch.setattr(settings, "BACKEND_PROXY_SECRET", "shared-secret")
    spoofed = _request(
        {
            "CF-Connecting-IP": "1.2.3.4",
            "CF-IPCountry": "SA",
            "X-Backend-Proxy-Secret": "wrong",
        }
    )
    assert geo.get_client_ip(spoofed) == "10.0.0.8"

    trusted = _request(
        {
            "CF-Connecting-IP": "1.2.3.4",
            "X-Backend-Proxy-Secret": "shared-secret",
        }
    )
    assert geo.get_client_ip(trusted) == "1.2.3.4"


def test_trusted_sa_header_still_calls_maxmind(monkeypatch):
    monkeypatch.setattr(settings, "BACKEND_PROXY_SECRET", "shared-secret")
    called = []

    async def fake_check(ip):
        called.append(ip)
        return {
            "country_code": "SA",
            "city": "Riyadh",
            "is_vpn": True,
            "is_proxy": False,
            "is_suspicious": True,
            "is_allowed": False,
        }

    monkeypatch.setattr(geo.maxmind, "check_ip", fake_check)
    request = _request(
        {
            "CF-Connecting-IP": "1.2.3.4",
            "CF-IPCountry": "SA",
            "X-Backend-Proxy-Secret": "shared-secret",
        }
    )
    result = asyncio.run(geo.resolve_geo(request))
    assert called == ["1.2.3.4"]
    assert result["is_allowed"] is False
