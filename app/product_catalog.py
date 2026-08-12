"""Product SKU / export catalog for orders, Sheets, and COD network CSV."""

PRODUCT_SKUS: dict[str, str] = {
    "sweat-shield": "LAMA-SWEAT-01",
    "nasma-spray": "LAMA-NASMA-01",
    "safaa-patches": "LAMA-SAFAA-01",
    "stain-hero": "LAMA-STAIN-01",
}

# COD / fulfillment network SKUs (platform product codes — override per product if needed)
COD_NETWORK_SKUS: dict[str, str] = {
    "sweat-shield": "MP-YU0SFE1SC0RH",
    "nasma-spray": "LAMA-NASMA-01",
    "safaa-patches": "LAMA-SAFAA-01",
    "stain-hero": "LAMA-STAIN-01",
}

PRODUCT_EXPORT_NAMES_EN: dict[str, str] = {
    "sweat-shield": "Armpit sweat absorbing pads ( 50 pair )",
    "nasma-spray": "Nasma shoe freshness spray 120ml",
    "safaa-patches": "Safaa acne patches 180 pcs",
    "stain-hero": "Instant stain remover spray 120ml",
}

PRODUCT_URLS: dict[str, str] = {
    "sweat-shield": "https://lamabeauty.shop/products/sweat-shield",
    "nasma-spray": "https://lamabeauty.shop/products/nasma-spray",
    "safaa-patches": "https://lamabeauty.shop/products/safaa-patches",
    "stain-hero": "https://lamabeauty.shop/lp/stain-hero",
}


def get_product_sku(product_id: str) -> str:
    return PRODUCT_SKUS.get(product_id, product_id.upper())


def get_cod_network_sku(product_id: str) -> str:
    return COD_NETWORK_SKUS.get(product_id) or get_product_sku(product_id)


def get_export_product_name(product_id: str, fallback: str = "") -> str:
    return PRODUCT_EXPORT_NAMES_EN.get(product_id) or fallback or product_id


def get_product_url(product_id: str) -> str:
    return PRODUCT_URLS.get(product_id, "https://lamabeauty.shop")
