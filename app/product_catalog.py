"""Product SKU lookup for orders and Google Sheets export."""

PRODUCT_SKUS: dict[str, str] = {
    "sweat-shield": "LAMA-SWEAT-01",
    "nasma-spray": "LAMA-NASMA-01",
    "safaa-patches": "LAMA-SAFAA-01",
}


def get_product_sku(product_id: str) -> str:
    return PRODUCT_SKUS.get(product_id, product_id.upper())
