"""Authoritative server-side commerce catalog and pricing rules."""

from decimal import Decimal

PRODUCTS: dict[str, dict[str, str | Decimal]] = {
    "sweat-shield": {
        "nameAr": "درع العرق اليومي",
        "sku": "LAMA-SWEAT-01",
        "price": Decimal("89.00"),
    },
    "nasma-spray": {
        "nameAr": "نسمة — بخاخ إنعاش الحذاء والقدم",
        "sku": "LAMA-NASMA-01",
        "price": Decimal("99.00"),
    },
    "safaa-patches": {
        "nameAr": "صفاء — لاصقات حب الشباب الشفافة",
        "sku": "LAMA-SAFAA-01",
        "price": Decimal("79.00"),
    },
}
UPSELL_PRICE = Decimal("59.00")
FREE_SHIPPING_THRESHOLD = Decimal("149.00")
SHIPPING_FEE = Decimal("25.00")


def get_product(product_id: str) -> dict[str, str | Decimal]:
    try:
        return PRODUCTS[product_id]
    except KeyError as exc:
        raise ValueError(f"Unknown product: {product_id}") from exc


def get_product_sku(product_id: str) -> str:
    product = PRODUCTS.get(product_id)
    return str(product["sku"]) if product else product_id.upper()


def price_items(raw_items: list[dict]) -> tuple[list[dict], Decimal, Decimal, Decimal]:
    """Construct trusted line items and apply one bundle unit per unique product."""
    items: list[dict] = []
    normal_total = Decimal("0.00")
    unique_unit_total = Decimal("0.00")
    for raw in raw_items:
        product_id = str(raw["productId"])
        qty = int(raw["qty"])
        product = get_product(product_id)
        price = Decimal(product["price"])
        normal_total += price * qty
        unique_unit_total += price
        items.append(
            {
                "productId": product_id,
                "nameAr": str(product["nameAr"]),
                "sku": str(product["sku"]),
                "qty": qty,
                "price": float(price),
            }
        )

    unique_count = len(items)
    if unique_count == 3:
        subtotal = normal_total - unique_unit_total + Decimal("199.00")
    elif unique_count == 2:
        subtotal = normal_total - unique_unit_total + Decimal("149.00")
    else:
        subtotal = normal_total
    shipping = Decimal("0.00") if subtotal >= FREE_SHIPPING_THRESHOLD else SHIPPING_FEE
    return items, subtotal, shipping, subtotal + shipping
