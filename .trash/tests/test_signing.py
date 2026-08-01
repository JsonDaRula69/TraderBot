from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from traderbot.kalshi.signing import (
    _KEY_TTL_SECONDS,
    _hash_pem,
    _key_cache,
    _key_cache_lock,
    clear_key_cache,
    sign_request,
)


_EXAMPLE_PEM = """-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEA0Z3VS5JJcds3xfn/ygWy6X4w66yEmI3hh3WBZvbdK7bFJE6n
y4sN5CEeRqF1dAVHhHPqR1KVD8HKiP9KdVY0e2K7zVE5QZ5E3rM1q1VVqXe1VFV/
w5BqMFZ3fGVfBnNE0KqZnMvDaXpF0HpJHf0eYMKfSLf0c4e0e0e0e0e0e0e0e0e0
e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0
"""


class TestHashPem:
    def test_deterministic(self) -> None:
        result1 = _hash_pem("test-pem-content")
        result2 = _hash_pem("test-pem-content")
        assert result1 == result2

    def test_different_inputs(self) -> None:
        assert _hash_pem("key-a") != _hash_pem("key-b")

    def test_output_is_hex_sha256(self) -> None:
        result = _hash_pem("test")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)


class TestKeyCacheEviction:
    def setup_method(self) -> None:
        clear_key_cache()

    def teardown_method(self) -> None:
        clear_key_cache()

    def test_cache_evicts_expired_entries(self) -> None:
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()

        current_time = 1000.0
        with patch("traderbot.kalshi.signing.time") as mock_time:
            mock_time.time.return_value = current_time
            sign_request(pem, 1700000000000, "GET", "/api/v1/markets")
        assert len(_key_cache) == 1

        expired_time = current_time + _KEY_TTL_SECONDS + 1
        with patch("traderbot.kalshi.signing.time") as mock_time:
            mock_time.time.return_value = expired_time
            clear_key_cache()
            from traderbot.kalshi.signing import _evict_expired_keys
            _evict_expired_keys()
        assert len(_key_cache) == 0

    def test_clear_key_cache_empties(self) -> None:
        _key_cache["test_key"] = (object(), time.time())
        clear_key_cache()
        assert len(_key_cache) == 0

    def test_ttl_is_5_minutes(self) -> None:
        assert _KEY_TTL_SECONDS == 300


class TestSignRequest:
    def setup_method(self) -> None:
        clear_key_cache()

    def teardown_method(self) -> None:
        clear_key_cache()

    def test_signs_with_valid_pem(self) -> None:
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()
        result = sign_request(pem, 1700000000000, "GET", "/api/v1/markets")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_cache_uses_hashed_key(self) -> None:
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()
        sign_request(pem, 1700000000000, "GET", "/api/v1/markets")
        cache_keys = list(_key_cache.keys())
        assert len(cache_keys) == 1
        assert pem not in cache_keys[0]
        assert _hash_pem(pem) in cache_keys[0]