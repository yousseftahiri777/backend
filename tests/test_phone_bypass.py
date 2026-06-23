"""Tests for test-phone geo bypass matching."""

from app.phone_utils import (
    build_test_phone_locals,
    is_whitelisted_test_phone,
    normalize_ksa_phone_local,
)


def test_normalize_variants():
    assert normalize_ksa_phone_local("0550000000") == "0550000000"
    assert normalize_ksa_phone_local("550000000") == "0550000000"
    assert normalize_ksa_phone_local("+966550000000") == "0550000000"
    assert normalize_ksa_phone_local("966550000000") == "0550000000"


def test_whitelist_matches_all_formats():
    whitelist = build_test_phone_locals("0550000000", "0513194328")
    assert is_whitelisted_test_phone("0550000000", whitelist)
    assert is_whitelisted_test_phone("550000000", whitelist)
    assert is_whitelisted_test_phone("+966550000000", whitelist)
    assert is_whitelisted_test_phone("966550000000", whitelist)
    assert not is_whitelisted_test_phone("0501234567", whitelist)


def test_empty_env_fallback_number():
    whitelist = build_test_phone_locals("", "0513194328")
    assert "0550000000" not in whitelist
    assert is_whitelisted_test_phone("0513194328", whitelist)
