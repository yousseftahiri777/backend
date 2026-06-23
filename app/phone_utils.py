"""Saudi phone normalization and test-order whitelist."""

import re

_DIGITS_ONLY = re.compile(r"\D")


def normalize_ksa_phone_local(phone: str) -> str:
    """Normalize any Saudi mobile input to 05XXXXXXXX (10 digits)."""
    digits = _DIGITS_ONLY.sub("", phone.strip())
    if digits.startswith("966"):
        digits = digits[3:]
    if len(digits) == 9 and digits.startswith("5"):
        digits = "0" + digits
    if len(digits) == 10 and digits.startswith("05"):
        return digits
    return digits


def build_test_phone_locals(*raw_numbers: str) -> set[str]:
    """Build a set of local-format numbers allowed to bypass geo checks."""
    out: set[str] = set()
    for raw in raw_numbers:
        cleaned = raw.strip()
        if not cleaned:
            continue
        local = normalize_ksa_phone_local(cleaned)
        if local:
            out.add(local)
    return out


def is_whitelisted_test_phone(phone: str, whitelist_locals: set[str]) -> bool:
    local = normalize_ksa_phone_local(phone)
    return bool(local) and local in whitelist_locals
