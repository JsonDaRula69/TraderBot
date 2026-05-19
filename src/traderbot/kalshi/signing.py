"""RSA-PSS request signing for Kalshi API authentication."""

from __future__ import annotations

import base64
import gc
import hashlib
import threading
import time

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

_KEY_TTL_SECONDS = 300  # 5 minutes

_CacheEntry = tuple[object, float]  # (key_object, load_timestamp)

_key_cache: dict[str, _CacheEntry] = {}
_key_cache_lock = threading.Lock()


def _hash_pem(private_key_pem: str) -> str:
    """Hash PEM content to avoid storing the plaintext key as a cache key."""
    return hashlib.sha256(private_key_pem.encode()).hexdigest()


def _evict_expired_keys() -> None:
    """Remove cache entries older than TTL."""
    cutoff = time.time() - _KEY_TTL_SECONDS
    expired = [k for k, (_, ts) in _key_cache.items() if ts < cutoff]
    for k in expired:
        del _key_cache[k]
    if expired:
        gc.collect()


def _load_key(private_key_pem: str) -> object:
    """Load and cache RSA private key objects with TTL-based eviction."""
    with _key_cache_lock:
        _evict_expired_keys()
        cache_key = _hash_pem(private_key_pem)
        if cache_key in _key_cache:
            key, _ = _key_cache[cache_key]
            _key_cache[cache_key] = (key, time.time())
            return key
        key = serialization.load_pem_private_key(
            private_key_pem.encode(), password=None
        )
        _key_cache[cache_key] = (key, time.time())
        return key


def sign_request(private_key_pem: str, timestamp_ms: int, method: str, path: str) -> str:
    """Sign a request string using RSA-PSS/SHA256/MGF1.

    The private key object is cached after first load with a 5-minute TTL.
    PEM content is hashed before use as a cache key.

    Args:
        private_key_pem: PEM-encoded RSA private key
        timestamp_ms: Current timestamp in milliseconds
        method: HTTP method (GET, POST, DELETE)
        path: API path (query params stripped before signing)

    Returns:
        Base64-encoded signature string
    """
    private_key = _load_key(private_key_pem)
    path_only = path.split("?")[0]
    msg_string = f"{timestamp_ms}{method}{path_only}"
    message = msg_string.encode("utf-8")
    signature = private_key.sign(
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.DIGEST_LENGTH,
        ),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("utf-8")


def auth_headers(api_key: str, private_key_pem: str, method: str, path: str) -> dict[str, str]:
    """Generate Kalshi authentication headers for a request.

    Returns dict with KALSHI-ACCESS-KEY, KALSHI-ACCESS-SIGNATURE, KALSHI-ACCESS-TIMESTAMP.
    """
    timestamp_ms = int(time.time() * 1000)
    signature = sign_request(private_key_pem, timestamp_ms, method, path)
    return {
        "KALSHI-ACCESS-KEY": api_key,
        "KALSHI-ACCESS-SIGNATURE": signature,
        "KALSHI-ACCESS-TIMESTAMP": str(timestamp_ms),
    }


def clear_key_cache() -> None:
    """Clear the key cache and force garbage collection. For testing."""
    with _key_cache_lock:
        _key_cache.clear()
    gc.collect()
