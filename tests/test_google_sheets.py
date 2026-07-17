from app.product_catalog import get_product_sku
from app.phone_utils import format_ksa_phone_international
from app.services.google_sheets import build_sheets_payload


def test_format_ksa_phone_international():
    assert format_ksa_phone_international("0504752330") == "966504752330"
    assert format_ksa_phone_international("+966504752330") == "966504752330"
    assert format_ksa_phone_international("966504752330") == "966504752330"


def test_product_skus():
    assert get_product_sku("sweat-shield") == "LAMA-SWEAT-01"
    assert get_product_sku("nasma-spray") == "LAMA-NASMA-01"
    assert get_product_sku("safaa-patches") == "LAMA-SAFAA-01"


def test_build_sheets_payload_multi_item():
    payload = build_sheets_payload(
        {
            "orderId": "lama-20260601-ABC123",
            "customerName": "أحمد",
            "phone": "0504752330",
            "city": "الرياض",
            "subtotal": 149,
            "shipping": 0,
            "total": 149,
            "status": "confirmed",
            "source": "website",
            "upsellProduct": "safaa-patches",
            "createdAt": "2026-06-01T10:00:00",
            "items": [
                {"productId": "sweat-shield", "nameAr": "درع العرق اليومي", "qty": 2, "price": 89},
                {"productId": "nasma-spray", "nameAr": "نسمة — بخاخ إنعاش الحذاء والقدم", "qty": 1, "price": 99},
            ],
        }
    )

    assert payload["date"] == "01/06/2026"
    assert payload["orderId"] == "lama-20260601-ABC123"
    assert payload["country"] == "KSA"
    assert payload["name"] == "أحمد"
    assert payload["phone"] == "966504752330"
    assert payload["product"] == "درع العرق اليومي/نسمة — بخاخ إنعاش الحذاء والقدم"
    assert payload["sku"] == "LAMA-SWEAT-01/LAMA-NASMA-01"
    assert payload["quantity"] == "2/1"
    assert payload["subtotal"] == 149
    assert payload["shipping"] == 0
    assert payload["totalPrice"] == 149
    assert payload["currency"] == "SAR"
    assert payload["status"] == "confirmed"
    assert payload["city"] == "الرياض"
    assert payload["source"] == "website"
    assert payload["upsell"] == "safaa-patches"
